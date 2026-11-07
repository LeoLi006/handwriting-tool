"""Build a base-font source ZIP from an explicit allowlist; no private files."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build(destination=None):
    destination=Path(destination or ROOT/'dist'/'handwriting-tool-base.zip')
    destination.parent.mkdir(parents=True,exist_ok=True)
    files=list(ROOT.glob('*.py'))
    files += [ROOT/name for name in ('requirements.txt','README.md','使用说明书.md','启动GUI.vbs','launch_gui.ps1')]
    files += list((ROOT/'tests').glob('*.py'))+list((ROOT/'tools').glob('*.py'))
    files += list((ROOT/'docs').glob('*.md'))
    files += [p for p in (ROOT/'integrations'/'leo').glob('*') if p.suffix in {'.py','.ps1','.json','.md'}]
    files += [p for p in (ROOT/'tools'/'windows-pins.txt',ROOT/'tools'/'windows-wheels.json') if p.is_file()]
    if (ROOT/'启动GUI.bat').is_file(): files.append(ROOT/'启动GUI.bat')
    files += [p for p in (ROOT/'examples').rglob('*') if p.is_file() and p.suffix in {'.md','.png'}]
    files += [ROOT/'fonts'/name for name in ('LXGWWenKai-Regular.ttf','MaShanZheng-Regular.ttf','catalog.json','fonts.json','README.md')]
    files += [p for p in (ROOT/'fonts').rglob('*') if p.is_file() and p.suffix in {'.txt','.png'}]
    files=sorted(set(files))
    unpacked=0
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            record=zipfile.ZipInfo('handwriting-tool/'+path.relative_to(ROOT).as_posix(),date_time=(2026,1,1,0,0,0))
            record.compress_type=zipfile.ZIP_DEFLATED;record.external_attr=0o100644<<16
            content=path.read_bytes()
            if path.suffix in {'.py','.md','.json','.txt','.ps1','.vbs','.bat'} and not content.startswith((b'\xff\xfe',b'\xfe\xff')):
                content=content.replace(b'\r\n',b'\n')
            archive.writestr(record,content)
            unpacked+=len(content)
    report=dict(archive=destination.name,bytes=destination.stat().st_size,
                unpacked_bytes=unpacked,files=len(files),
                fonts=['WenKai','MaShanZheng'],python_bundled=False,dependencies_bundled=False,
                sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    destination.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    print(json.dumps(build(args.output),ensure_ascii=False,indent=2))
