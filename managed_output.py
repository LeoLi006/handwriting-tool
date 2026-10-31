"""Publish complete generations; never mix old pages or same-name sources."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import warnings

import handwriting as hw


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
                      export_format='png', **params):
    if export_format not in {'png', 'both'}:
        raise ValueError('输出格式必须为 png 或 both')
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
        issues = list(dict.fromkeys(str(note.message) for note in notes))
        (stage / '问题清单.txt').write_text('\n\n'.join(issues) if issues else '未发现已知的转写问题。', encoding='utf-8')
        pdf_name = None
        if export_format == 'both':
            from pdf_export import write_pdf
            pdf_name = 'document.pdf'
            write_pdf(paths, stage / pdf_name, dpi=params.get('dpi', 150), cancel=cancel)
        if cancel and cancel():
            raise hw.ConversionCancelled('已取消转换')
        data = dict(source=source_key, generation=generation.name,
                    generated=[Path(p).name for p in paths] + ['问题清单.txt'] + ([pdf_name] if pdf_name else []),
                    pages=[Path(p).name for p in paths], issues=issues, pdf=pdf_name)
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
        return [str(generation / name) for name in data['pages']]
    finally:
        if stage.exists():
            shutil.rmtree(stage)
