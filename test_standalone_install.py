"""Install/rollback tests with isolated files and fake service/package commands."""
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import standalone_install as installer

class StandaloneInstallTests(unittest.TestCase):
    def exercise(self,fail=False,fresh=False):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);app=home/'hp34401a';suite=home/'instrument-suite';units=home/'units'
            app.mkdir();suite.mkdir();units.mkdir()
            original=b'{"hardware_enabled":false,"private_setting":"retained"}\n'
            if not fresh:(suite/'config.json').write_bytes(original)
            (app/'standalone_app.py').write_text('previous web host')
            web=units/'hp34401a.service';web.write_text('previous web unit')
            broker=units/'fischer-gpib.service'
            if not fresh:broker.write_text('existing owner')
            calls=[]
            def fake_run(*args,**kw):
                calls.append(tuple(map(str,args)))
                if args[:3]==('sudo','tar','-czf'):
                    with tarfile.open(args[3],'w:gz') as archive:
                        for name in args[6:]:archive.add('/'+name,arcname=name)
                elif args[:3]==('sudo','tar','-xzf'):
                    with tarfile.open(args[3]) as archive:
                        for member in archive.getmembers():
                            target=Path('/'+member.name).resolve()
                            self.assertTrue(target==home or home in target.parents)
                            if member.isdir():target.mkdir(parents=True,exist_ok=True)
                            elif member.isfile():target.write_bytes(archive.extractfile(member).read())
                elif args[:2]==('sudo','tee'):Path(args[2]).write_text(kw['input'])
                elif args[0]=='curl' and fail:raise RuntimeError('simulated startup failure')
                return subprocess.CompletedProcess(args,0)
            with patch.multiple(installer,HOME=home,APP=app,SUITE=suite,WEB_UNIT=web,BROKER_UNIT=broker,UDEV_RULE=units/'adapter.rules'), \
                 patch.object(installer,'preflight'),patch.object(installer,'run',side_effect=fake_run), \
                 patch.object(installer.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'startup failure'):installer.main(['--apply'])
                else:installer.main(['--apply'])
            if not fresh:
                self.assertEqual((suite/'config.json').read_bytes(),original)
                self.assertEqual(broker.read_text(),'existing owner')
                self.assertFalse(any('fischer-gpib' in call for call in calls if 'systemctl' in call))
            else:
                config=json.loads((suite/'config.json').read_text())
                self.assertFalse(config['hardware_enabled']);self.assertTrue(config['meter_read_only'])
                self.assertIn('GROUP="www-data"',(units/'adapter.rules').read_text())
                self.assertTrue(any('--attr-match=idVendor=03eb' in call and '--attr-match=idProduct=2065' in call for call in calls))
                self.assertIn(str(app/'venv/bin/python'),broker.read_text())
            if fail:
                self.assertEqual(web.read_text(),'previous web unit')
                self.assertEqual((app/'standalone_app.py').read_text(),'previous web host')
            else:
                self.assertEqual(json.loads((app/'tools.json').read_text()),{'instruments':['meter']})
                self.assertIn('--workers 1 --threads 4',web.read_text())

    def test_existing_broker_is_reused_without_config_or_service_changes(self):self.exercise()
    def test_web_startup_failure_restores_previous_app_and_unit(self):self.exercise(True)
    def test_fresh_broker_installs_targeted_usb_permissions_and_starts_disabled(self):self.exercise(fresh=True)

    def test_selection_requires_meter_and_rejects_unknown_tools(self):
        self.assertEqual(installer.selection('meter,scope,meter'),['meter','scope'])
        for text in ('scope','meter,unknown',''):
            with self.assertRaises(Exception):installer.selection(text)
