"""Windowless bootstrap, with visible dependency progress and a persistent error log."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import traceback


def main():
    base = Path(__file__).resolve().parent
    state = Path(os.environ['MOJIAN_STATE_DIR']) if os.environ.get('MOJIAN_STATE_DIR') else Path(os.environ.get('LOCALAPPDATA', Path.home()/'.cache'))/'Mojian'
    state.mkdir(parents=True, exist_ok=True)
    log_path = state/'startup.log'
    log = log_path.open('w', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = log
    try:
        if sys.platform == 'win32':
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        import tkinter as tk
        from tkinter import messagebox, ttk
        if sys.version_info < (3, 10):
            raise RuntimeError('需要 Python 3.10 或更新版本，并包含 tkinter。请安装后重新启动。')
        for filename in ('fonts/LXGWWenKai-Regular.ttf', 'fonts/MaShanZheng-Regular.ttf'):
            if not (base/filename).is_file():
                raise RuntimeError(f'基础字体缺失：{filename}。请完整解压分享包，不要直接在压缩包内启动。')
        missing = [name for name in ('fontTools', 'PIL', 'matplotlib', 'tkinterdnd2')
                   if importlib.util.find_spec(name) is None]
        if missing and os.environ.get('MOJIAN_PORTABLE'):
            raise RuntimeError('离线包缺少运行依赖：'+', '.join(missing)+'。请重新完整解压离线包，不需要安装 Python 或联网补依赖。')
        if missing:
            root = tk.Tk(); root.title('墨笺 · 首次启动')
            root.geometry('520x240'); root.resizable(False, False)
            tk.Label(root, text='首次运行：正在安装依赖，需要联网', font=('Microsoft YaHei UI', 12)).pack(pady=(20, 10))
            tk.Label(root, text='缺少：'+', '.join(missing)+'\n安装失败可查看日志并重试；已安装后可离线转换。', wraplength=480).pack(pady=6)
            bar = ttk.Progressbar(root, mode='indeterminate'); bar.pack(fill='x', padx=28); bar.start()
            process = subprocess.Popen([sys.executable, '-m', 'pip', 'install', '-r', str(base/'requirements.txt')],
                                       stdout=log, stderr=log, cwd=base,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            cancelled = [False]
            def cancel_install():
                cancelled[0] = True
                if process.poll() is None:
                    process.terminate()
            ttk.Button(root, text='取消安装', command=cancel_install).pack(pady=10)
            def finish():
                if process.poll() is None:
                    root.after(200, finish); return
                root.destroy()
            root.after(200, finish)
            root.protocol('WM_DELETE_WINDOW', cancel_install)
            root.mainloop()
            if cancelled[0]:
                print('用户取消了首次依赖安装，可重新启动后重试。')
                return
            if process.returncode:
                raise RuntimeError(f'依赖安装未完成（退出码 {process.returncode}）。请检查网络或 Python 写入权限。\n可手动运行："{sys.executable}" -m pip install -r "{base / "requirements.txt"}"\n详细日志：{log_path}')
        import gui
        gui.main()
    except (Exception, SystemExit) as exc:
        traceback.print_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror('墨笺启动失败', f'{exc}\n\n日志：{log_path}', parent=root)
            root.destroy()
        except Exception:
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, f'{exc}\n{log_path}', 'Mojian', 16)


if __name__ == '__main__':
    main()
