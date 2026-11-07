import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
(ROOT/'tmp').mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('mojian_leo', ROOT/'integrations/leo/install.py')
integration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integration)


class LeoIntegrationTests(unittest.TestCase):
    def settings(self):
        return dict(PetSize=130, DisplayName='My pet', ApiPrivateFixture={'Key':'fixture-only'},
                    ApplicationModules=[dict(Id='existing', Name='Other')],
                    ApplicationPackages={}, EntryDisplayModes={}, Aliases={}, Unknown={'keep':[1,2]})

    def test_preserves_unrelated_fields_and_input(self):
        original=self.settings(); snapshot=copy.deepcopy(original)
        result=integration.merge_settings(original, 'fixture/Mojian.lnk', 'fixture/tool')
        self.assertEqual(original,snapshot)
        for key in ('ApiPrivateFixture','Unknown','DisplayName','PetSize'):
            self.assertEqual(result[key],original[key])
        self.assertEqual(result['ApplicationModules'][0],original['ApplicationModules'][0])
        self.assertFalse(result['ApplicationModules'][-1]['Administrator'])
        self.assertEqual(result['ApplicationModules'][-1]['Arguments'],'')

    def test_idempotence_and_customization(self):
        first=integration.merge_settings(self.settings(),'old/Mojian.lnk','old/tool')
        app=first['ApplicationModules'][-1];app.update(Name='My custom name',Enabled=False,Icon='glyph:image')
        first['EntryDisplayModes'][app['Id']]='search'
        second=integration.merge_settings(first,'new/Mojian.lnk','new/tool')
        third=integration.merge_settings(second,'new/Mojian.lnk','new/tool')
        self.assertEqual(second,third)
        self.assertEqual(len(second['ApplicationModules']),2)
        self.assertFalse(second['ApplicationModules'][-1]['Enabled'])
        self.assertEqual(second['ApplicationModules'][-1]['Name'],'My custom name')
        self.assertEqual(second['EntryDisplayModes'][app['Id']],'search')

    def test_package_has_no_local_paths_or_code(self):
        package=integration.PACKAGE
        self.assertEqual(set(package),{'Format','Protocol','Id','Version','Name','HostMin','HostMax','Dependencies'})
        self.assertEqual(len(package['Id']),32)
        self.assertEqual(package['Dependencies'],['windows','local-application/v1'])

    def test_rejects_conflicts_and_invalid_shapes(self):
        bad=self.settings();bad['ApplicationModules'].append(dict(Id=integration.PACKAGE['Id']))
        with self.assertRaises(ValueError):integration.merge_settings(bad,'a','b')
        bad=self.settings();bad['ApplicationModules']=None
        with self.assertRaises(ValueError):integration.merge_settings(bad,'a','b')
        with self.assertRaises(ValueError):integration.merge_settings({},'a','b')

    def test_failed_save_keeps_original_and_private_backup(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            file=Path(directory)/'leo-settings.json';original=json.dumps(self.settings()).encode()
            file.write_bytes(original)
            with patch.object(integration.os,'replace',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):integration.atomic_save(file,original,self.settings())
            self.assertEqual(file.read_bytes(),original)
            self.assertEqual(len(list((file.parent/'backups/mojian-integration').glob('*.json'))),1)
            self.assertFalse(list(file.parent.glob('.mojian-*')))

    def test_concurrent_change_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            file=Path(directory)/'leo-settings.json';file.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):integration.atomic_save(file,b'old',self.settings())
            self.assertEqual(file.read_bytes(),b'changed')


if __name__=='__main__':unittest.main()
