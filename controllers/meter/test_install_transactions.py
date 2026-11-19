"""Exercise installation/rollback in a temporary filesystem with all service I/O faked."""
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import install

class InstallTransactionTests(unittest.TestCase):
    def exercise(self, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory); hp=home/'hp6033a'; suite=home/'instrument-suite'
            (hp/'venv/bin').mkdir(parents=True);(hp/'venv/bin/python').touch();(hp/'templates').mkdir()
            (hp/'app.py').write_text('original application');(hp/'config.json').write_text('{"private":"preserve"}')
            suite.mkdir();original=b'{"hardware_enabled":false,"meter_read_only":true,"custom":123}\n'
            (suite/'config.json').write_bytes(original)
            unit=home/'systemd/broker.service';unit.parent.mkdir();unit.write_text('original unit')
            drop=home/'systemd/drop.conf';drop.write_text('original drop')
            candidate=home/'candidate.py';candidate.write_text('new coordinated app')
            calls=[]
            def fake_run(*args,**kwargs):
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
                elif args[:3]==('sudo','mkdir','-p'):Path(args[3]).mkdir(parents=True,exist_ok=True)
                elif args[:2]==('sudo','tee'):Path(args[2]).write_text(kwargs['input'])
                elif args[0]=='curl' and fail:raise RuntimeError('simulated failed activation')
                return subprocess.CompletedProcess(args,0)
            def fake_process(args,**kwargs):
                calls.append(tuple(args));return subprocess.CompletedProcess(args,0)
            with patch.multiple(install,HOME=home,HP=hp,SUITE=suite,UNIT=unit,DROP=drop,NGINX=()), \
                 patch.object(Path,'home',return_value=home),patch.object(install.os,'getuid',return_value=1000), \
                 patch.object(install,'stage',return_value=candidate),patch.object(install,'run',side_effect=fake_run), \
                 patch.object(install.subprocess,'run',side_effect=fake_process),patch.object(sys,'argv',['install','--apply']):
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'failed activation'):install.main()
                else:install.main()
            self.assertEqual((suite/'config.json').read_bytes(),original)
            self.assertEqual((hp/'config.json').read_text(),'{"private":"preserve"}')
            if fail:
                self.assertEqual((hp/'app.py').read_text(),'original application')
                self.assertEqual(unit.read_text(),'original unit');self.assertEqual(drop.read_text(),'original drop')
            else:self.assertEqual((hp/'app.py').read_text(),'new coordinated app')
            self.assertTrue(any(c[:4]==('sudo','systemctl','stop','hp6033a') for c in calls))
            self.assertTrue(any(c[:4]==('sudo','systemctl','start','hp34401a') for c in calls))
    def test_success_preserves_runtime_configuration(self):self.exercise()
    def test_failed_activation_restores_application_and_units(self):self.exercise(fail=True)
