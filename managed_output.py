"""Publish complete generations; never mix old pages or same-name sources."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import warnings

import handwriting as hw


class ConversionResult(list):
    """Public output paths with private preview paths for the desktop app."""
    def __init__(self, outputs, preview_paths=None, page_count=None, issues=None):
        super().__init__(outputs)
        self.preview_paths = list(outputs if preview_paths is None else preview_paths)
        self.page_count = page_count if page_count is not None else len(self.preview_paths)
        self.issues = list(issues or [])


def _pdf_destination(source, root):
    """Replace our own result, but never an unrelated same-name PDF."""
    from PIL import PdfParser
    source = Path(source).resolve()
    digest = hashlib.sha256(os.path.normcase(str(source)).encode('utf-8')).hexdigest()
    owner = 'Mojian source ' + digest
    stem = re.sub(r'[<>:"/\\|?*]', '_', source.stem).rstrip('. ')[:100] or 'document'
    base = Path(root) if root else source.parent
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / (stem + '.pdf')
    number = 0
    while candidate.exists():
        try:
            with candidate.open('rb') as stream:
                if stream.read(5) == b'%PDF-':
                    with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
                        with PdfParser.PdfParser(buf=buffer) as pdf:
                            if getattr(pdf.info, 'Subject', '') == owner:
                                break
        except Exception:
            pass
        number += 1
        suffix = '--' + digest[:10] + (f'-{number}' if number > 1 else '')
        candidate = base / (stem + suffix + '.pdf')
    return candidate, owner


def _generate_single_pdf(source, outdir=None, cancel=None, page_progress=None,
                         preview_root=None, **params):
    from pdf_export import write_pdf
    destination, owner = _pdf_destination(source, outdir)
    if preview_root:
        Path(preview_root).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='mojian-pdf-', dir=preview_root))
    succeeded = False
    try:
        with warnings.catch_warnings(record=True) as notes:
            warnings.simplefilter('always', UserWarning)
            pages = hw.convert_file(source, outdir=work, cancel=cancel,
                                    page_progress=page_progress, **params)
        from diagnostics import issue_data
        structured_issues = issue_data(notes)
        issues = list(dict.fromkeys(str(note.message) for note in notes))
        write_pdf(pages, destination, dpi=params.get('dpi', 150), cancel=cancel,
                  subject=owner, keywords='\n'.join(issues))
        succeeded = True
        for issue in issues:
            warnings.warn(issue, UserWarning)
        return ConversionResult([str(destination)], pages if preview_root else [], len(pages), structured_issues)
    finally:
        if not succeeded or not preview_root:
            shutil.rmtree(work)


def document_directory(source, root=None):
    source = Path(source).resolve()
    key = os.path.normcase(str(source))
    suffix = hashlib.sha256(key.encode('utf-8')).hexdigest()[:10]
    stem = re.sub(r'[<>:"/\\|?*]', '_', source.stem)[:60].rstrip('. ') or 'document'
    base = Path(root) if root else source.parent / '手写体'
    return base / f'{stem}--{suffix}'


def _retire_previous(directory, previous, source):
    """Only unlink names recorded by our old manifest; leave user-added files."""
    name = previous.get('generation', '')
    if previous.get('source') != source or not re.fullmatch(r'run-[0-9a-f]{32}', name):
        return
    old = directory / name
    if old.is_symlink() or old.resolve().parent != directory.resolve():
        return
    marker = old / '.generation.json'
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('source') != source:
            return
        for name in data.get('generated', []):
            if isinstance(name, str) and Path(name).name == name and name not in {'.', '..'}:
                path = old / name
                if path.is_file() and not path.is_symlink():
                    path.unlink()
        marker.unlink()
        try:
            old.rmdir()
        except OSError:
            pass  # User-added files remain in the old generation.
    except (OSError, ValueError):
        warnings.warn('新结果已保存，旧结果清理未完成；旧结果位于独立 run 文件夹。', UserWarning)


def generate_document(source, outdir=None, cancel=None, page_progress=None,
                      export_format='png', preview_root=None, **params):
    if export_format == 'pdf':
        return _generate_single_pdf(source, outdir, cancel, page_progress, preview_root, **params)
    if export_format not in {'png', 'both'}:
        raise ValueError('输出格式必须为 png、pdf 或 both')
    directory = document_directory(source, outdir)
    directory.mkdir(parents=True, exist_ok=True)
    source_key = os.path.normcase(str(Path(source).resolve()))
    latest = directory / 'latest.json'
    try:
        previous = json.loads(latest.read_text(encoding='utf-8'))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    stage = Path(tempfile.mkdtemp(prefix='.pending-', dir=directory))
    generation = directory / ('run-' + uuid.uuid4().hex)
    try:
        with warnings.catch_warnings(record=True) as notes:
            warnings.simplefilter('always', UserWarning)
            paths = hw.convert_file(source, outdir=stage, cancel=cancel,
                                    page_progress=page_progress, **params)
        if not paths:
            raise ValueError('所选页码没有可输出的页面，请检查页码范围。')
        from diagnostics import issue_data
        structured_issues = issue_data(notes)
        issues = list(dict.fromkeys(str(note.message) for note in notes))
        (stage / '问题清单.json').write_text(json.dumps(structured_issues, ensure_ascii=False, indent=2), encoding='utf-8')
        (stage / '问题清单.txt').write_text('\n\n'.join(issues) if issues else '未发现已知的转写问题。', encoding='utf-8')
        pdf_name = None
        if export_format == 'both':
            from pdf_export import write_pdf
            pdf_name = 'document.pdf'
            write_pdf(paths, stage / pdf_name, dpi=params.get('dpi', 150), cancel=cancel)
        if cancel and cancel():
            raise hw.ConversionCancelled('已取消转换')
        data = dict(source=source_key, generation=generation.name,
                    generated=[Path(p).name for p in paths] + ['问题清单.txt', '问题清单.json'] + ([pdf_name] if pdf_name else []),
                    pages=[Path(p).name for p in paths], issues=issues, structured_issues=structured_issues, pdf=pdf_name)
        (stage / '.generation.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(stage, generation)
        pointer = directory / ('latest-' + uuid.uuid4().hex + '.tmp')
        try:
            pointer.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(pointer, latest)
        except Exception:
            shutil.rmtree(generation)
            pointer.unlink(missing_ok=True)
            raise
        _retire_previous(directory, previous, source_key)
        for issue in issues:
            warnings.warn(issue, UserWarning)
        return ConversionResult([str(generation / name) for name in data['pages']], issues=structured_issues)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
