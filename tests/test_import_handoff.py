import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from import_handoff import parse_startup, import_into, PROTOCOL

class HandoffTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[1] / "tmp"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "中文 & spaces.md"
        self.source.write_text("# Original", encoding="utf-8")
    def request(self):
        file = self.root / "request.json"
        file.write_text(json.dumps(dict(protocol=PROTOCOL, requestId="a"*32, input=str(self.source))), encoding="utf-8")
        return parse_startup(["--import-request", str(file)])
    def test_normal_launch_unchanged(self):
        self.assertEqual(parse_startup([]), (None, False))
    def test_direct_import_disables_installer(self):
        request, blocked = parse_startup(["--import-file", str(self.source)])
        self.assertTrue(blocked)
        self.assertEqual(request.path, str(self.source))
    def test_receipt_only_after_import_without_export(self):
        request, blocked = self.request()
        app = Mock(busy=False)
        app._file_summary.side_effect = lambda: self.assertFalse(request.receipt.exists())
        import_into(app, request)
        self.assertEqual(app.files, [str(self.source)])
        self.assertEqual(json.loads(request.receipt.read_text())["state"], "imported")
        app._preview_one.assert_called_once()
        app._start.assert_not_called()
        self.assertEqual(self.source.read_text(), "# Original")
        self.assertTrue(blocked)
    def test_failure_not_imported(self):
        request, _ = self.request()
        app = Mock(busy=False)
        app._file_summary.side_effect = RuntimeError("fixture")
        with self.assertRaises(RuntimeError): import_into(app, request)
        self.assertEqual(json.loads(request.receipt.read_text())["state"], "failed")
        app._preview_one.assert_not_called()
    def test_no_overwrite_or_replay(self):
        request, _ = self.request()
        request.acknowledge("imported")
        with self.assertRaises(ValueError): self.request()
        with self.assertRaises(FileExistsError): request.acknowledge("failed")
    def test_missing_file_and_other_types_rejected(self):
        for file in (self.root / "gone.md", self.root):
            with self.assertRaises(ValueError): parse_startup(["--import-file", str(file)])
        self.source.rename(self.source.with_suffix(".py"))
        with self.assertRaises(ValueError): parse_startup(["--import-file", str(self.source.with_suffix(".py"))])
    def test_multi_input_rejected(self):
        with self.assertRaises(SystemExit): parse_startup(["--import-file", str(self.source), str(self.source)])
    def test_bad_identity_rejected(self):
        file = self.root / "bad.json"
        file.write_text(json.dumps(dict(protocol=PROTOCOL, requestId="bad", input=str(self.source))))
        with self.assertRaises(ValueError): parse_startup(["--import-request", str(file)])

    def test_expired_host_does_not_recreate_transport(self):
        from import_handoff import ImportRequest
        folder = self.root / "expired"
        request = ImportRequest(str(self.source), "c"*32, folder / "request.receipt.json")
        app = Mock(busy=False)
        import_into(app, request)
        self.assertEqual(app.files, [str(self.source)])
        self.assertFalse(folder.exists())
        app._start.assert_not_called()
