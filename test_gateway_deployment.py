"""Exercise catalog deployment and failed gateway activation in a temporary filesystem."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import deploy_manager as installer

class GatewayDeploymentTests(unittest.TestCase):
 def exercise(self,fail=False):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);source=base/'source';home=base/'home';root=base/'manager';units=base/'units'
   source.mkdir();home.mkdir();root.mkdir();units.mkdir()
   unit=units/'manager.service';sudoers=base/'sudoers';backups=base/'backups'
   unit.write_text('previous service');sudoers.write_text('previous restricted commands')
   for name in installer.FILES:(source/name).write_text('new '+name)
   for name in installer.WEB:(source/name).write_text('new '+name)
   (source/'approved/packages').mkdir(parents=True)
   tools={}
   for key in ('meter','supply','scope','generator','counter'):
    data=('fixture archive '+key).encode();(source/'approved/packages'/(key+'.zip')).write_bytes(data);tools[key]={'sha256':hashlib.sha256(data).hexdigest()}
   (source/'approved/catalog.json').write_text(json.dumps({'tools':tools}))
   (root/'manager_engine.py').write_text('previous manager')
   suite=home/'instrument-suite';suite.mkdir();(suite/'suite_gateway.py').write_text('previous gateway')
   protected=suite/'config.json';protected.write_text('private fixture configuration')
   profile=base/'profile.json';profile.write_text('existing root-owned deployment policy')
   calls=[];failed=[False]
   def run(*args,**kw):
    calls.append((args,kw))
    if fail and args==('systemctl','restart','fischer-suite-web') and not failed[0]:
     failed[0]=True
     # Emulate root's ability to restore a read-only sudoers file in this unprivileged fixture.
     sudoers.chmod(0o600)
     raise subprocess.CalledProcessError(1,args)
    return subprocess.CompletedProcess(args,0)
   def probe(args,**kw):
    # Only the supply and stable gateway are already running.
    running='--user' not in args and args[-1] in ('hp6033a','fischer-suite-web')
    return subprocess.CompletedProcess(args,0 if running else 3)
   with patch.multiple(installer,SOURCE=source,ROOT=root,HOME=home,UNIT=unit,SUDOERS=sudoers,SYSTEMD=units,BACKUPS=backups),patch.object(installer.os,'geteuid',return_value=0),patch.object(installer.os,'chown'),patch.object(installer.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000,pw_gid=1000)),patch.object(installer,'run',side_effect=run),patch.object(installer.subprocess,'run',side_effect=probe),patch('builtins.print'):
    if fail:
     with self.assertRaises(subprocess.CalledProcessError):installer.main()
    else:installer.main()
   self.assertEqual(protected.read_text(),'private fixture configuration')
   self.assertEqual(profile.read_text(),'existing root-owned deployment policy')
   self.assertFalse(any('fischer-gpib' in args for args,kw in calls))
   if fail:
    self.assertEqual((root/'manager_engine.py').read_text(),'previous manager')
    self.assertEqual((suite/'suite_gateway.py').read_text(),'previous gateway')
    self.assertTrue(any(args==('systemctl','restart','fischer-suite-web') and kw.get('check') is False for args,kw in calls))
   else:
    self.assertEqual((root/'deployment_profile.py').read_text(),'new deployment_profile.py')
    self.assertEqual((suite/'suite_gateway.py').read_text(),'new suite_gateway.py')
    self.assertTrue(any(args==('systemctl','restart','fischer-suite-web') for args,kw in calls))
    self.assertFalse(any(args==('systemctl','restart','hp34401a') for args,kw in calls))
 def test_existing_gateway_and_policy_survive_catalog_refresh(self):self.exercise()
 def test_failed_gateway_restart_restores_previous_web_and_manager(self):self.exercise(True)

if __name__=='__main__':unittest.main()
