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

Disable/remove the entry in Leo without uninstalling Mojian or deleting documents. Conversion and export still require Mojian's own preview/confirmation; automatic file hand-off, unattended conversion and export are not implemented.

## Verification

`python -m unittest discover -s tests -p test_leo_integration.py` checks isolated settings merging, preservation of unrelated fields, repeated installation, identity conflicts, concurrent changes and failed saves. These fixtures do not read personal settings or start applications. Manually click the installed entry once to verify the GUI appears; do not label unperformed live checks as passed.
