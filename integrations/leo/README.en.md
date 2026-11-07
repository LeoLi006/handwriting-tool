# Open Mojian from Leo

[简体中文](README.md) | **English**

[Leo desktop companion](https://github.com/LeoLi006/leo-desktop) · [Mojian handwriting tool](https://github.com/LeoLi006/handwriting-tool)

This integration uses Leo's existing local-application module contract, not an embedded converter. Open Mojian's independent GUI from Leo's shortcut bar/menu or search `mojian`, `shouxie`, `handwriting`, `墨笺` or `手写`. Documents, fonts, preview and conversion stay local to Mojian. No model API or background conversion is added.

## Connect this computer

Fully extract and run both products once. With Python 3.10+, from the Mojian directory:

```powershell
python integrations/leo/install.py --leo-dir "YOUR_INSTALLED_LEO_FOLDER" --dry-run
python integrations/leo/install.py --leo-dir "YOUR_INSTALLED_LEO_FOLDER"
```

The self-contained Windows ZIP can use `runtime\python.exe` instead of `python`. Choose the actual installation containing both `LeoLauncher.exe` and `leo-settings.json`, not Leo's source directory. The data-package contract targets Leo 1.04.x–1.x; compatibility is based on the source schema, not a claim that every historical release was tested.

The script attempts a graceful shutdown of that specific Leo installation, reads its latest settings, creates a local `.leo-local/Mojian.lnk`, atomically saves registration and starts Leo. If Leo does not exit cleanly, exit it manually and retry; the script does not force-kill it. Original settings are backed up in Leo's `backups/mojian-integration/`. These backups contain private configuration: never publish them.

Repeated setup avoids duplicate entries and preserves custom names, icons, disabled state and entry visibility. Move either folder? Run setup again with the new Leo location. Saving failures preserve the original settings and attempt to restart an instance that was previously running. Setup does not download dependencies or upload configuration. Mojian's existing launcher still handles its own first-run dependency requirements.

## Manual setup or data package

1. Create a Windows `.lnk` shortcut to Mojian's `启动GUI.vbs`.
2. Leo → Settings → Features → Application modules → New application: select that shortcut and choose a name/icon. Save both the application and Leo settings.
3. Alternatively import `mojian.leoapp.json` in that window and choose your shortcut in the configuration preview. The package contains only identity, version and dependency declarations, not programs, scripts or paths.
4. The shortcut appears at the top of Leo's application search window (or More); menu/search access remains available according to entry visibility settings.

Disable/remove the entry in Leo without uninstalling Mojian or deleting documents. Conversion and export still require Mojian's own preview/confirmation; the original shortcut remains launch-only. The explicit import interface below now supports one Markdown file; unattended conversion/export remain unsupported.

## Verification

`python -m unittest discover -s tests -p test_leo_integration.py` checks isolated settings merging, preservation of unrelated fields, repeated installation, identity conflicts, concurrent changes and failed saves. These fixtures do not read personal settings or start applications. Manually click the installed entry once to verify the GUI appears; do not label unperformed live checks as passed.

## Explicit Markdown handoff

Use an already provisioned local Python environment:

```powershell
python gui_launcher.py --no-install --import-file "absolute path to document.md"
```

Only one existing `.md` or `.markdown` file is accepted. Mojian uses its existing document list and preview workflow; it never calls final generation. Check/select template, font and output location in Mojian, then explicitly generate. Input is preserved. Original VBS/shortcut launching is unchanged and does not forward arguments. Import mode always prohibits dependency installation.

In Leo's existing Open capabilities, select the local pythonw.exe, set Mojian as working directory, and optionally set arguments to the quoted absolute gui_launcher.py path plus --no-install. Choose File import handoff, set the same GUI launcher as import script, declare .md .markdown, and disable folders/batches. Paths stay local and must not be distributed in module packages.

### Local receipt protocol: LeoFileImport/1

The host creates a UTF-8 request JSON in a per-request private temporary directory and passes --import-request with its absolute path. Fields: protocol (LeoFileImport/1), requestId (32 lowercase hex characters), input (absolute existing Markdown path). Maximum 16KB, one input, no commands or output settings.

After GUI list import, Mojian exclusively creates a sibling receipt by replacing the request extension with .receipt.json. It echoes protocol/requestId/input and returns state imported or failed, optionally a short failure code. Imported proves neither preview success nor completed conversion. Existing receipts cannot be overwritten/replayed. Hosts validate identity/input, report unconfirmed timeouts and never automatically retry generation. Cancelling a wait cannot recall an import already received.

### Targeted verification

Run python -B -m unittest discover -s tests -p test_import_handoff.py. An explicit MOJIAN_GUI_TEST=1 enables test_import_handoff_gui.py in an environment with GUI dependencies: it verifies the real GUI with isolated settings/input, without final generation or personal documents.
