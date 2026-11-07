"""Reproducible Windows x64 distribution using verified official Python ZIP/wheels.

No Python installation or MSI execution. Builds use Python.org + PyPI only.
Run --resolve-lock once to explicitly refresh pinned wheel artifact hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import uuid
import zipfile
from build_portable import build as build_source

ROOT=Path(__file__).resolve().parents[1]
PYTHON=dict(version='3.13.17',url='https://www.python.org/ftp/python/3.13.17/python-3.13.17-amd64.zip',
            sha256='b26ca4b4ee51e157836049934d2b8eabd55939be296f3130254251b6df96ec2f')
LOCK=ROOT/'tools'/'windows-wheels.json'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download(url,target,digest=None):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        partial=target.with_suffix(target.suffix+'.partial')
        urllib.request.urlretrieve(url,partial);os.replace(partial,target)
    if digest and sha(target)!=digest:raise ValueError(f'SHA-256 mismatch: {target.name}')
    return target


def extract(archive,directory):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            if not (directory/item.filename).resolve().is_relative_to(directory):raise ValueError('ZIP path escapes destination')
            if item.filename.endswith('.pyc') or '__pycache__/' in item.filename:continue
            source.extract(item,directory)


def resolve_lock(cache,python):
    wheels=cache/'resolve';wheels.mkdir(exist_ok=True)
    subprocess.run([str(python),'-I','-B','-m','pip','--isolated','--disable-pip-version-check','--no-cache-dir','download','--only-binary=:all:','--no-deps',
                    '--index-url','https://pypi.org/simple','--dest',str(wheels),'-r',str(ROOT/'tools'/'windows-pins.txt')],check=True)
    records=[]
    for pin in (ROOT/'tools'/'windows-pins.txt').read_text().splitlines():
        if not pin.strip():continue
        name,version=pin.split('==')
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:data=json.load(response)
        selected=[item for item in data['urls'] if (wheels/item['filename']).is_file()]
        if len(selected)!=1:raise ValueError(f'Expected one pinned wheel for {name}')
        item=selected[0]
        if sha(wheels/item['filename'])!=item['digests']['sha256']:raise ValueError('PyPI hash mismatch')
        records.append(dict(name=name,version=version,filename=item['filename'],url=item['url'],sha256=item['digests']['sha256']))
    LOCK.write_text(json.dumps(dict(python=PYTHON,platform='windows-x86_64',wheels=records),indent=2)+'\n',encoding='utf-8')


def include_runtime(path):
    parts=path.parts
    if '__pycache__' in parts or path.suffix in {'.pyc','.pdb','.lib','.h'}:return False
    if path.name in {'direct_url.json','RECORD'}:return False
    if any(x in parts for x in ('test','tests','idlelib','ensurepip','demos')):return False
    if 'site-packages' in parts and any(x=='pip' or x.startswith('pip-') for x in parts):return False
    if parts and parts[0] in {'Include','libs','Scripts'}:return False
    return True


def build(resolve=False):
    if os.name!='nt':raise RuntimeError('Windows x64 build host required')
    cache=ROOT/'tmp'/'windows-build'/'cache';cache.mkdir(parents=True,exist_ok=True)
    runtime_zip=download(PYTHON['url'],cache/Path(PYTHON['url']).name,PYTHON['sha256'])
    work=ROOT/'tmp'/'windows-build'/('stage-'+uuid.uuid4().hex)
    runtime=work/'runtime';extract(runtime_zip,runtime)
    python=runtime/'python.exe'
    if resolve:resolve_lock(cache,python)
    lock=json.loads(LOCK.read_text(encoding='utf-8'))
    if lock['python']!=PYTHON:raise ValueError('Runtime lock mismatch')
    wheel_paths=[download(item['url'],cache/'wheels'/item['filename'],item['sha256']) for item in lock['wheels']]
    subprocess.run([str(python),'-I','-B','-m','pip','--isolated','--disable-pip-version-check','--no-cache-dir','install','--no-warn-script-location','--no-index','--no-deps','--no-compile',*[str(p) for p in wheel_paths]],check=True)
    subprocess.run([str(python),'-I','-B','-c','import tkinter, PIL, fontTools, matplotlib, numpy, tkinterdnd2; print("Bundled imports OK")'],check=True)
    build_source()
    extract(ROOT/'dist'/'handwriting-tool-base.zip',work/'source')
    app=work/'source'/'handwriting-tool'
    # Copy only distributable runtime files; no pip, test suites or bytecode.
    for path in runtime.rglob('*'):
        relative=path.relative_to(runtime)
        if path.is_file() and include_runtime(relative):
            target=app/'runtime'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    (app/'THIRD-PARTY').mkdir()
    for path in runtime.rglob('*'):
        if path.is_file() and ('license' in path.name.lower() or path.name in {'COPYING','NOTICE','license.terms'}):
            target=app/'THIRD-PARTY'/path.relative_to(runtime);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    (app/'portable.json').write_text(json.dumps(dict(platform='Windows x64',python=PYTHON['version'],offline=True)),encoding='utf-8')
    vbs='''Option Explicit
Dim fso, shell, base, python, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
python = fso.BuildPath(base, "runtime\\pythonw.exe")
If Not fso.FileExists(python) Then
    MsgBox "运行时缺失，请完整解压 Windows 离线包；无需另装 Python。", 16, "墨笺启动失败"
    WScript.Quit 1
End If
shell.CurrentDirectory = base
command = Chr(34) & python & Chr(34) & " -I -B " & Chr(34) & fso.BuildPath(base, "portable_start.py") & Chr(34)
shell.Run command, 0, False
'''
    (app/'启动GUI.vbs').write_text(vbs,encoding='utf-16')
    (app/'离线版说明.txt').write_text('Windows x64 解压即用。双击启动GUI.vbs。无需预装 Python、Office、LaTeX，基础字体及依赖已齐全。\n配置、字体缓存、日志在包内 data/；请解压到可写目录。可选字体另行联网下载。\n仅同一 Windows 主机隔离验证，未在干净虚拟机验证；不承诺 Windows ARM/32位兼容。\n授权见 THIRD-PARTY/、runtime/LICENSE.txt 和 fonts/licenses/。\n',encoding='utf-8')
    files=sorted(p for p in app.rglob('*') if p.is_file())
    private=str(ROOT).encode('utf-8')
    for path in files:
        if path.suffix.lower() in {'.py','.json','.txt','.md','.ps1'} and private in path.read_bytes():
            raise ValueError('Private build path found in '+str(path.relative_to(app)))
    manifest='\n'.join(f'{sha(p)}  {p.relative_to(app).as_posix()}' for p in files)+'\n'
    (app/'FILES.sha256').write_text(manifest,encoding='utf-8')
    info=dict(python=PYTHON,platform='Windows x64',wheels=lock['wheels'],source_payload_sha256=sha(ROOT/'dist'/'handwriting-tool-base.zip'),
              verification='Requires tools/verify_windows.py; same-host isolation is not a clean Windows VM')
    (app/'BUILD-INFO.json').write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
    output=ROOT/'dist'/'handwriting-tool-windows-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(p for p in app.rglob('*') if p.is_file()):
            record=zipfile.ZipInfo('handwriting-tool/'+path.relative_to(app).as_posix(),date_time=(2026,1,1,0,0,0))
            record.compress_type=zipfile.ZIP_DEFLATED;record.external_attr=0o100644<<16
            archive.writestr(record,path.read_bytes())
    report=dict(archive=output.name,bytes=output.stat().st_size,unpacked_bytes=sum(p.stat().st_size for p in app.rglob('*') if p.is_file()),
                sha256=sha(output),python=PYTHON['version'],python_bundled=True,dependencies_bundled=True,files=len(files)+2)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2));return output,app


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--resolve-lock',action='store_true');args=parser.parse_args();build(args.resolve_lock)
