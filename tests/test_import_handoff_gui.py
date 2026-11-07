"""Opt-in GUI import check, using only an isolated document and settings."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

@unittest.skipUnless(os.environ.get("MOJIAN_GUI_TEST") == "1", "explicit GUI verification only")
class GuiImportTests(unittest.TestCase):
    def test_existing_gui_imports_without_export(self):
        parent = Path(__file__).resolve().parents[1] / "tmp"
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            base = Path(folder)
            source = base / "中文 & test.md"
            source.write_text("# Test\n\nOriginal document.", encoding="utf-8")
            request = base / "request.json"
            request.write_text(json.dumps(dict(protocol="LeoFileImport/1", requestId="b"*32, input=str(source))), encoding="utf-8")
            with patch.dict(os.environ, {"MOJIAN_STATE_DIR": folder, "MPLCONFIGDIR": str(base / "mpl")}), patch("tempfile.tempdir", folder):
                import gui
                from import_handoff import parse_startup, import_into
                root = gui.TkinterDnD.Tk() if gui.DND_OK else gui.tk.Tk()
                root.withdraw()
                app = gui.App(root, settings_file=base / "settings.json")
                actual, blocked = parse_startup(["--import-request", str(request)])
                with patch.object(app, "_start", side_effect=AssertionError("must not export")) as export:
                    import_into(app, actual)
                    root.update()
                    self.assertEqual(app.files, [str(source)])
                    self.assertEqual(app.jobs[0]["status"], "待确认")
                    self.assertEqual(json.loads(actual.receipt.read_text())["state"], "imported")
                    self.assertEqual(app.output_paths, [])
                    self.assertTrue(blocked)
                    export.assert_not_called()
                    app._close()
                    # _close waits for the preview worker before releasing its temp files.
                    try:
                        root.mainloop()
                    except gui.tk.TclError:
                        pass
            self.assertEqual(source.read_text(encoding="utf-8"), "# Test\n\nOriginal document.")
            self.assertFalse((base / "手写体").exists())
