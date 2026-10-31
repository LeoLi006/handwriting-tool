"""Small, validated JSON preferences and reusable handwriting presets."""
import json
import os
from pathlib import Path

PRESETS = {
    '工整笔记': dict(font='WenKai', font_size=40, line_spacing_ratio=1.4,
                   word_spacing=0, jitter=0.1, glyph_variation=0.7, ruled=True),
    '自然手写': dict(font='Xiaolai', font_size=40, line_spacing_ratio=1.5,
                   word_spacing=1, jitter=0.7, glyph_variation=1.2, ruled=True),
    '紧凑复习': dict(font='WenKai', font_size=34, line_spacing_ratio=1.15,
                   word_spacing=-1, jitter=0.1, glyph_variation=0.5, ruled=False),
}
LIMITS = dict(font_size=(24, 64), line_spacing_ratio=(0.9, 2.6),
              word_spacing=(-10, 16), jitter=(0, 2.5), glyph_variation=(0, 1.8))


def settings_path():
    base = Path(os.environ.get('APPDATA', Path.home() / '.config'))
    return base / 'Mojian' / 'settings.json'


def validate(data):
    clean = {}
    if not isinstance(data, dict):
        return clean
    for key, (low, high) in LIMITS.items():
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high:
            clean[key] = int(value) if key == 'font_size' else value
    for key in ('font', 'formula_font', 'outdir', 'preset', 'export_format'):
        if isinstance(data.get(key), str):
            clean[key] = data[key]
    for key in ('ruled', 'formula'):
        if isinstance(data.get(key), bool):
            clean[key] = data[key]
    return clean


def load_settings(path=None):
    try:
        return validate(json.loads(Path(path or settings_path()).read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return {}


def save_settings(data, path=None):
    path = Path(path or settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(validate(data), ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)
