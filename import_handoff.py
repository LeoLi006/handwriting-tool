"""Explicit single-Markdown GUI import; no conversion or dependency installation."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re

PROTOCOL = "LeoFileImport/1"

@dataclass(frozen=True)
class ImportRequest:
    path: str
    request_id: str = ""
    receipt: Path | None = None

    def acknowledge(self, state, code=""):
        if self.receipt is None:
            return
        # Exclusive creation: a request can never overwrite a previous receipt/output.
        try:
            with self.receipt.open("x", encoding="utf-8") as stream:
                json.dump(dict(protocol=PROTOCOL, requestId=self.request_id,
                               input=self.path, state=state, code=code), stream)
        except FileNotFoundError:
            # Host cancelled/timed out and removed its transport directory.
            # Keep the imported GUI document; do not recreate a late receipt directory.
            return


def parse_startup(argv):
    parser = argparse.ArgumentParser(description="Mojian GUI: import, preview, then confirm manually")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--import-file")
    group.add_argument("--import-request")
    parser.add_argument("--no-install", action="store_true")
    args = parser.parse_args(argv)
    request_id = ""
    receipt = None
    raw = args.import_file
    if args.import_request:
        request = Path(args.import_request)
        if not request.is_absolute() or not request.is_file() or request.stat().st_size > 16384:
            raise ValueError("Invalid import request")
        data = json.loads(request.read_text(encoding="utf-8"))
        request_id = data.get("requestId", "")
        if data.get("protocol") != PROTOCOL or not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
            raise ValueError("Invalid import protocol or identity")
        receipt = request.with_suffix(".receipt.json")
        if receipt.exists():
            raise ValueError("Import request already acknowledged")
        raw = data.get("input")
    if raw is None:
        return None, args.no_install
    if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
        raise ValueError("Markdown input must be an absolute file path")
    source = Path(raw)
    if not source.is_file() or source.suffix.lower() not in (".md", ".markdown"):
        raise ValueError("Import requires one existing .md or .markdown file")
    return ImportRequest(str(source), request_id, receipt), True


def import_into(app, request):
    """Use the existing GUI selection and preview path; never call _start/export."""
    try:
        if app.busy or not Path(request.path).is_file():
            raise ValueError("Import unavailable or input removed")
        app.files = [request.path]
        app._file_summary()
    except Exception:
        request.acknowledge("failed", "import_failed")
        raise
    request.acknowledge("imported")
    app._preview_one()
