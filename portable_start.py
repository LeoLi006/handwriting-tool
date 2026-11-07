"""Entry for the self-contained Windows ZIP, always using its own state/runtime."""
import os
from pathlib import Path
import sys


def configure(base=None):
    base=Path(base or __file__).resolve()
    if base.is_file():base=base.parent
    state=Path(os.environ.get('MOJIAN_ISOLATED_STATE',base/'data')).resolve()
    state.mkdir(parents=True,exist_ok=True)
    os.environ['MOJIAN_STATE_DIR']=str(state)
    os.environ['MOJIAN_PORTABLE']='1'
    os.environ['MPLCONFIGDIR']=str(state/'matplotlib')
    os.environ['PYTHONNOUSERSITE']='1'
    os.environ['PATH']=str(base/'runtime')+os.pathsep+str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32')
    for key in ('PYTHONPATH','PYTHONHOME','TCL_LIBRARY','TK_LIBRARY'):
        os.environ.pop(key,None)
    os.environ['TCL_LIBRARY']=str(base/'runtime'/'tcl'/'tcl8.6')
    os.environ['TK_LIBRARY']=str(base/'runtime'/'tcl'/'tk8.6')
    os.environ['TEMP']=os.environ['TMP']=str(state/'temp')
    (state/'temp').mkdir(exist_ok=True)
    sys.path.insert(0,str(base))
    return base,state


def main():
    try:
        base,state=configure()
        if '--verify' in sys.argv:
            from portable_verification import verify
            verify(base,Path(sys.argv[sys.argv.index('--verify')+1]))
        else:
            import gui_launcher
            gui_launcher.main()
    except BaseException as exc:
        import traceback
        try:
            log=Path(os.environ.get('MOJIAN_STATE_DIR',Path(__file__).resolve().parent))/'portable-error.log'
            log.write_text(traceback.format_exc(),encoding='utf-8')
            message=f'工具未能启动：{exc}\n请完整解压到可写目录。日志：{log}'
        except OSError:
            message=f'工具未能启动：{exc}\n请完整解压到可写目录，当前目录无法写入日志。'
        if '--verify' in sys.argv:raise
        import ctypes
        ctypes.windll.user32.MessageBoxW(0,message,'墨笺 · 启动失败',16)


if __name__=='__main__':main()
