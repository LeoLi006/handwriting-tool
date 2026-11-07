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
        app._save_document_settings()
        saved_size=app.size_var.get();app.size_var.set(32);app._restore_document_settings()
        assert app.size_var.get()==saved_size
        global_size=app._global_preferences['font_size']
        app.size_var.set(30);app._save_preferences()
        from app_settings import load_settings
        assert load_settings(app.settings_file)['font_size']==global_size
        original_profile=app._settings_payload()
        app.document_settings.save(source,dict(original_profile,font='missing-test-font'))
        app._restore_document_settings()
        assert app.style_keys[app.font_combo.current()]=='WenKai'
        assert '缺失' in app.settings_source.cget('text')
        assert app.document_settings.load(source)[0]['font']=='missing-test-font'
        app.document_settings.save(source,original_profile);app._restore_document_settings()
        app._open_comparison();view=app.compare_view
        def wait_comparison():
            deadline=time.monotonic()+45
            while (view.busy or not all(view.paths)) and time.monotonic()<deadline:
                root.update();time.sleep(.02)
            root.update();assert all(view.paths),view.status.cget('text')
        wait_comparison();baseline=dict(view.baseline)
        app.glyph_variation_var.set(.3);app.glyph_variation_var.set(0 if baseline['glyph_variation']>.5 else 1.5)
        wait_comparison();assert view.baseline==baseline
        assert 'glyph_variation' in view.changed.cget('text')
        view.set_baseline();wait_comparison();assert '无；' in view.changed.cget('text')
        view.close()
        print('GUI preview / comparison debounce-cache-baseline / profiles / zoom / diagnostics OK')
    finally:
        if app.compare_view and not app.compare_view.closed:app.compare_view.close()
        while app.compare_view and app.compare_view.busy:
            root.update();time.sleep(.02)
        for window in root.winfo_children():
            if isinstance(window,tk.Toplevel):window.destroy()
        root.destroy();app._preview_dir.cleanup()


if __name__=='__main__': main()
