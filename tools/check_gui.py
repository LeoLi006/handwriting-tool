"""Opt-in local Tk smoke: real preview worker, jump, refresh, zoom and issue UI."""
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tkinter as tk
import gui


def main():
    base=Path('tmp/gui-smoke').resolve();base.mkdir(parents=True,exist_ok=True)
    tempfile.tempdir=str(base)
    root=gui.TkinterDnD.Tk() if gui.DND_OK else tk.Tk()
    root.withdraw()
    app=gui.App(root,settings_file=base/'preferences.json')
    source=base/'preview.md';source.write_text('# GUI 检查\n\n'+'正文用于分页。'*500,encoding='utf-8')
    app.files=[str(source)];app._file_summary()
    def wait():
        deadline=time.monotonic()+45
        while app.busy and time.monotonic()<deadline:
            root.update();time.sleep(.02)
        root.update()
        assert not app.busy, 'GUI worker timeout'
        assert app.output_paths, app.status.cget('text')
    try:
        app._preview_one();wait()
        assert len(app.output_paths)==1
        app.page_var.set('2');app._goto_page();wait()
        assert app.preview_index==1 and len(app.output_paths)==2
        with patch.object(gui.hw,'render_markdown',side_effect=AssertionError('cached page re-rendered')):
            app._refresh_current();root.update()
            app.page_var.set('1');app._goto_page();root.update()
        assert app.preview_index==0
        app._zoom_preview();root.update()
        app.jobs[0]['issues']=[dict(severity='警告',line=3,section='GUI 检查',object='测试',page=2,reason='可定位问题')]
        app._job_detail();root.update()
        assert len([w for w in root.winfo_children() if isinstance(w,tk.Toplevel)])==2
        app.table_variation_var.set(.4)
        assert app._approved_snapshot is None
        print('GUI worker / page jump / cache refresh / zoom / issues / invalidation OK')
    finally:
        for window in root.winfo_children():
            if isinstance(window,tk.Toplevel):window.destroy()
        root.destroy();app._preview_dir.cleanup()


if __name__=='__main__': main()
