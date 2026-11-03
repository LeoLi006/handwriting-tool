"""Windowless bootstrap, with visible dependency progress and a persistent error log."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import traceback


def main():
    base = Path(__file__).resolve().parent
    state = Path(os.environ.get('LOCALAPPDATA', Path.home()/'.cache'))/'Mojian'
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
        missing = [name for name in ('handright', 'fontTools', 'PIL', 'matplotlib', 'tkinterdnd2')
                   if importlib.util.find_spec(name) is None]
        if missing:
            root = tk.Tk(); root.title('墨笺 · 首次启动')
            root.geometry('460x150'); root.resizable(False, False)
            tk.Label(root, text='正在安装运行依赖，请稍候…', font=('Microsoft YaHei UI', 12)).pack(pady=(24, 10))
            bar = ttk.Progressbar(root, mode='indeterminate'); bar.pack(fill='x', padx=28); bar.start()
            process = subprocess.Popen([sys.executable, '-m', 'pip', 'install', '-r', str(base/'requirements.txt')],
                                       stdout=log, stderr=log, cwd=base,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def finish():
                if process.poll() is None:
                    root.after(200, finish); return
                root.destroy()
            root.after(200, finish)
            root.protocol('WM_DELETE_WINDOW', lambda: None)
            root.mainloop()
            if process.returncode:
                raise RuntimeError(f'依赖安装未完成，请检查网络。详细日志：{log_path}')
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
