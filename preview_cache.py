"""Bounded disk-backed page cache; cache misses stop at the requested page."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import warnings
import handwriting as hw


def fingerprint(path, params):
    path = Path(path).resolve()
    content = path.read_bytes()
    dependencies = [Path(hw.FALLBACK)]
    if path.suffix.lower() != '.docx':
        for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)', content.decode('utf-8')):
            from urllib.parse import unquote
            dependencies.append(path.parent/unquote(target))
    for name in ('font', 'formula_font'):
        value = params.get(name)
        if value:
            candidate = Path(value)
            if candidate.is_file(): dependencies.append(candidate)
            elif name == 'font':
                from font_manager import font_path
                if value in hw.load_registry(): dependencies.append(font_path(value))
    digest = hashlib.sha256(content)
    digest.update(str(path).encode('utf-8'))
    digest.update(json.dumps(params, sort_keys=True, ensure_ascii=False).encode('utf-8'))
    for dependency in dependencies:
        digest.update(str(dependency).encode('utf-8'))
        try:
            digest.update(hashlib.sha256(dependency.read_bytes()).digest())
        except OSError:
            digest.update(b'missing')
    return digest.hexdigest()


class PreviewCache:
    def __init__(self, directory, capacity=3):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        self.capacity = capacity
        self.entries = {}

    def get(self, source, params, page=1, force=False, cancel=None):
        if not 1 <= page <= 9999:
            raise ValueError('页码必须在 1—9999 之间')
        key = fingerprint(source, params)
        old = self.entries.get(key)
        if old and not force and (len(old['paths']) >= page or old['complete']):
            self.entries.pop(key); self.entries[key] = old
            return old, True
        target = self.directory/key
        target.mkdir(exist_ok=True)
        paths=[]
        def save(image, number):
            path = target/f'{number}.png'; image.save(path); paths.append(str(path))
        with warnings.catch_warnings(record=True) as notes:
            warnings.simplefilter('always', UserWarning)
            _, renderer = hw.render_markdown(hw.read_input(source, cancel=cancel), source_path=source,
                page_limit=page, page_sink=save, cancel=cancel, **params)
        entry = dict(paths=paths, issues=[i.to_dict() for i in renderer.issues],
                     notices=list(dict.fromkeys(str(n.message) for n in notes)),
                     complete=not renderer.limit_reached, blocks=renderer.block_map, key=key)
        self.entries.pop(key, None); self.entries[key]=entry
        while len(self.entries)>self.capacity:
            retired = next(iter(self.entries)); self.entries.pop(retired)
            shutil.rmtree(self.directory/retired)
        return entry, False
