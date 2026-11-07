"""Register Mojian through Leo's existing data-only local application contract."""
import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
TOOL = HERE.parents[1]
PACKAGE = json.loads((HERE / 'mojian.leoapp.json').read_text(encoding='utf-8-sig'))


def merge_settings(settings, shortcut, tool):
    """Return a detached draft. Unknown/personal fields are preserved, never logged."""
    if not isinstance(settings, dict) or 'PetSize' not in settings:
        raise ValueError('Not a recognized Leo settings file')
    result = copy.deepcopy(settings)
    apps = result.setdefault('ApplicationModules', [])
    packages = result.setdefault('ApplicationPackages', {})
    modes = result.setdefault('EntryDisplayModes', {})
    aliases = result.setdefault('Aliases', {})
    if not isinstance(apps, list) or any(not isinstance(a, dict) for a in apps):
        raise ValueError('Invalid application list')
    if any(not isinstance(v, dict) for v in (packages, modes, aliases)):
        raise ValueError('Invalid module settings')
    ids = [a.get('Id') for a in apps]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate existing application identity')
    matches = [(key, value) for key, value in packages.items()
               if isinstance(value, dict) and value.get('Manifest', {}).get('Id') == PACKAGE['Id']]
    if len(matches) > 1:
        raise ValueError('Duplicate package identity')
    app_id = matches[0][0] if matches else PACKAGE['Id']
    if app_id in packages and not matches:
        raise ValueError('Application identity belongs to another package')
    old = next((a for a in apps if a.get('Id') == app_id), None)
    if old and not matches:
        raise ValueError('Application identity already in use')
    if matches and matches[0][1].get('Manifest', {}).get('Version') != PACKAGE['Version']:
        raise ValueError('A different package version is installed; use Leo package management')
    app = dict(old or (matches[0][1].get('Local') if matches else {}) or {})
    app.update(Id=app_id, Path=str(shortcut), Arguments='', WorkingDirectory=str(tool), Administrator=False)
    app.setdefault('Name', PACKAGE['Name'])
    app.setdefault('Enabled', True)
    app.setdefault('Icon', 'glyph:notes')
    result['ApplicationModules'] = [a for a in apps if a.get('Id') != app_id] + [app]
    packages[app_id] = dict(Manifest=copy.deepcopy(PACKAGE), Local=copy.deepcopy(app), Installed=True)
    modes.setdefault(app_id, 'shortcut')
    values = aliases.setdefault(str(shortcut), [])
    if not isinstance(values, list):
        raise ValueError('Invalid application aliases')
    for alias in ('墨笺', '手写', '手写体', 'mojian', 'shouxie', 'handwriting'):
        if alias not in values:
            values.append(alias)
    return result


def atomic_save(path, original, settings):
    """Save after shutdown, keeping both a private backup and the old file on failure."""
    if path.read_bytes() != original:
        raise RuntimeError('Leo settings changed during installation; retry after exiting Leo')
    backup_dir = path.parent / 'backups' / 'mojian-integration'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    (backup_dir / (stamp + '.json')).write_bytes(original)
    payload = (json.dumps(settings, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.mojian-', delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if path.read_bytes() != original:
            raise RuntimeError('Leo settings changed before commit; original file retained')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def host(mode, **arguments):
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
               '-File', str(HERE / 'host.ps1'), '-Mode', mode]
    for key, value in arguments.items():
        command += ['-' + key, str(value)]
    return subprocess.run(command, check=True, capture_output=True, text=True,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def install(leo_directory, dry_run=False):
    leo = Path(leo_directory).resolve()
    config = leo / 'leo-settings.json'
    if not (leo / 'LeoLauncher.exe').is_file() or not config.is_file():
        raise ValueError('Choose the running Leo folder containing LeoLauncher.exe and leo-settings.json')
    if not (TOOL / '启动GUI.vbs').is_file():
        raise ValueError('Extract the complete handwriting tool first')
    shortcut = TOOL / '.leo-local' / 'Mojian.lnk'
    original = config.read_bytes()
    draft = merge_settings(json.loads(original.decode('utf-8-sig')), shortcut, TOOL)
    if dry_run:
        return 'Preflight OK; no settings changed'
    if os.name != 'nt':
        raise RuntimeError('Local integration requires Windows')
    # Do not kill a busy host or edit a file that its running instance may overwrite.
    stopped = host('Stop', LeoDirectory=leo).stdout.strip() != '0'
    try:
        original = config.read_bytes()
        draft = merge_settings(json.loads(original.decode('utf-8-sig')), shortcut, TOOL)
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        host('Shortcut', ShortcutPath=shortcut, ToolDirectory=TOOL)
        atomic_save(config, original, draft)
    except BaseException:
        if stopped:
            host('Start', LeoDirectory=leo)
        raise
    host('Start', LeoDirectory=leo)
    return 'Mojian added to Leo. Search mojian / shouxie, or use the shortcut bar.'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--leo-dir', required=True, help='Installed Leo folder (not its source repository)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        print(install(args.leo_dir, args.dry_run))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Do not print subprocess output or configuration: those can contain personal data.
        parser.exit(1, 'Integration failed: ' + type(error).__name__ + '. Check paths, exit Leo, and retry.\n')
