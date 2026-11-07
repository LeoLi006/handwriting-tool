"""Extract a Windows ZIP into a new path; test only its own interpreter offline."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from build_windows import extract, ROOT


def windowless_launch(app,env):
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.windll.kernel32;user=ctypes.windll.user32
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    expected=(app/'runtime'/'pythonw.exe').resolve()
    binary=expected.read_bytes();offset=int.from_bytes(binary[60:64],'little')
    assert int.from_bytes(binary[offset+24+68:offset+24+70],'little')==2, 'pythonw must use GUI subsystem'
    subprocess.run([str(Path(env['SystemRoot'])/'System32'/'wscript.exe'),str(app/'启动GUI.vbs')],env=env,cwd=app,check=True,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    found=[]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def inspect(hwnd,unused):
        title=ctypes.create_unicode_buffer(256);user.GetWindowTextW(hwnd,title,256)
        if title.value!='墨笺 · 手写体转换器':return True
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        handle=kernel.OpenProcess(0x1000,False,pid.value)
        if handle:
            path=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(path))
            if kernel.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)) and Path(path.value).resolve()==expected:
                found.append((hwnd,pid.value))
            kernel.CloseHandle(handle)
        return True
    callback=callback_type(inspect);deadline=time.monotonic()+30
    while not found and time.monotonic()<deadline:
        user.EnumWindows(callback,0);time.sleep(.1)
    if not found:raise RuntimeError('Bundled VBS did not open the expected GUI; inspect isolated-state/startup.log')
    for hwnd,pid in found:
        handle=kernel.OpenProcess(0x100000,False,pid)
        user.PostMessageW(hwnd,0x0010,0,0)
        if handle:
            kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            assert kernel.WaitForSingleObject(handle,10000)==0,'GUI did not exit'
            kernel.CloseHandle(handle)
    return True


def verify(archive,output=None):
    output=Path(output or ROOT/'tmp'/'windows-verification'/uuid.uuid4().hex).resolve()
    extract(archive,output/'unpacked')
    app=output/'unpacked'/'handwriting-tool'
    state=output/'isolated-state';state.mkdir(parents=True,exist_ok=True)
    # Do not inherit developer Python, user site, font or app configuration.
    env={key:os.environ[key] for key in ('SystemRoot','WINDIR','COMSPEC','SYSTEMDRIVE') if key in os.environ}
    env.update(PATH=str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'),
               MOJIAN_ISOLATED_STATE=str(state),USERPROFILE=str(state),HOME=str(state),
               APPDATA=str(state/'roaming'),LOCALAPPDATA=str(state/'local'),
               PYTHONPATH=str(output/'forbidden-host-modules'),PYTHONHOME=str(output/'forbidden-python'))
    command=[str(app/'runtime'/'python.exe'),'-I','-B',str(app/'portable_start.py'),'--verify',str(output/'results')]
    subprocess.run(command,cwd=output,env=env,check=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    report=json.loads((output/'results'/'verification.json').read_text(encoding='utf-8'))
    report['vbs_windowless_launch']=windowless_launch(app,env)
    (output/'results'/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Verification complete:',json.dumps(report,ensure_ascii=True))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',nargs='?',default='dist/handwriting-tool-windows-x64.zip')
    parser.add_argument('--output');args=parser.parse_args();verify(args.archive,args.output)
