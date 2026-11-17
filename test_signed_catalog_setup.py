"""Signed catalog setup ships without legacy ZIP assets and preserves web services."""
import json,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import deploy_manager as deploy

class SignedCatalogSetupTests(unittest.TestCase):
 def exercise(self,existing=True,fail=False):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);source=base/'source';source.mkdir();root=base/'manager'
   home=base/'home';home.mkdir();units=base/'units';units.mkdir()
   suite=home/'instrument-suite';suite.mkdir()
   web=suite/'suite_gateway.py';web.write_text('preserved gateway')
   cfg=suite/'config.json';cfg.write_text('private configuration')
   policy=base/'updater.json';policy.write_text('{}')
   unit=units/'manager.service';sudoers=base/'sudoers'
   for name in deploy.FILES:(source/name).write_text('# signed fixture '+name+'\n')
   if existing:
    root.mkdir();(root/'manager_engine.py').write_text('previous manager')
    (root/'catalog.json').write_text('{"version":"previous","tools":{}}')
    unit.write_text('previous unit');sudoers.write_text('previous sudoers')
   calls=[];failed=[False]
   def run(*args,**kwargs):
    calls.append(args)
    if args==('systemctl','stop','fischer-suite-manager') and not unit.exists() and kwargs.get('check',True):
     raise subprocess.CalledProcessError(5,args)
    if fail and args==('systemctl','restart','fischer-suite-manager') and not failed[0]:
     failed[0]=True;sudoers.chmod(0o600);raise subprocess.CalledProcessError(1,args)
    return subprocess.CompletedProcess(args,0)
   with patch.multiple(deploy,SOURCE=source,ROOT=root,HOME=home,UNIT=unit,SUDOERS=sudoers,SYSTEMD=units,BACKUPS=base/'backups',UPDATER_CONFIG=policy,MANAGER_SOCKET=base/'absent.sock'),patch.object(deploy.os,'geteuid',return_value=0),patch.object(deploy.os,'chown'),patch.object(deploy.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000,pw_gid=1000)),patch.object(deploy,'run',side_effect=run),patch.object(deploy.subprocess,'run') as probe,patch('builtins.print'):
    if fail:
     with self.assertRaises(subprocess.CalledProcessError):deploy.main(signed_only=True)
    else:deploy.main(signed_only=True)
    probe.assert_not_called()
   self.assertEqual(web.read_text(),'preserved gateway');self.assertEqual(cfg.read_text(),'private configuration')
   self.assertFalse(any(any(x in str(args) for x in ('fischer-suite-web','hp6033a','hp34401a','tektronix-controller','fischer-gpib')) for args in calls))
   if fail:
    if existing:
     self.assertEqual((root/'manager_engine.py').read_text(),'previous manager')
     self.assertEqual(unit.read_text(),'previous unit');self.assertEqual(sudoers.read_text(),'previous sudoers')
     self.assertFalse((root/'activate.py').exists())
    else:self.assertFalse(root.exists());self.assertFalse(unit.exists());self.assertFalse(sudoers.exists())
   else:
    if not existing:self.assertNotIn(('systemctl','stop','fischer-suite-manager'),calls)
    self.assertEqual((root/'activate.py').read_text(),'# signed fixture activate.py\n')
    self.assertIn('install-signed',sudoers.read_text());self.assertIn('remove-signed',sudoers.read_text())
    if existing:self.assertEqual(json.loads((root/'catalog.json').read_text())['version'],'previous')
    else:self.assertEqual(set(json.loads((root/'catalog.json').read_text())['tools']),{'meter','supply','scope'})
 def test_fresh_setup_needs_no_legacy_zip_assets(self):self.exercise(existing=False)
 def test_existing_gateway_and_controllers_are_not_restarted(self):self.exercise()
 def test_failed_refresh_restores_helper_unit_and_authorization(self):self.exercise(fail=True)
 def test_failed_fresh_setup_removes_new_privileged_files(self):self.exercise(existing=False,fail=True)

if __name__=='__main__':unittest.main()
