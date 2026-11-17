"""Signed catalog integration, using temporary files and mocked service/instrument I/O."""
from contextlib import contextmanager
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import activate
import manager_engine as manager
from deployment_profile import guarded_entry

class SignedCatalogTests(unittest.TestCase):
 def test_all_guarded_independent_services_are_removable(self):
  for tool,(folder,service,port,module) in activate.APPS.items():
   with self.subTest(tool=tool),tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);target=base/folder;target.mkdir();units=base/'units';units.mkdir()
    (target/'maintenance_entry.py').write_text(guarded_entry(tool))
    (units/(service+'.service')).write_text(f'User=pi\nWorkingDirectory={target}\nExecStart={target}/venv/bin/gunicorn --bind 127.0.0.1:{port} maintenance_entry:app\n')
    with patch.multiple(manager,HOME=base,UNITS=units,REGISTRY=base/'registry.json'):
     self.assertEqual(manager.removal_policy(tool),(True,''))

 def test_unknown_guard_or_shared_host_stays_protected(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);target=base/'hp34401a';target.mkdir();units=base/'units';units.mkdir()
   unit=units/'hp34401a.service'
   unit.write_text(f'User=pi\nWorkingDirectory={target}\nExecStart={target}/venv/bin/gunicorn --bind 127.0.0.1:8082 maintenance_entry:app\n')
   for text in ('import arbitrary_module\n',guarded_entry('supply')):
    (target/'maintenance_entry.py').write_text(text)
    with patch.multiple(manager,HOME=base,UNITS=units,REGISTRY=base/'registry.json'):
     self.assertFalse(manager.removal_policy('meter')[0])
   (target/'maintenance_entry.py').write_text(guarded_entry('meter'))
   unit.write_text(unit.read_text().replace(str(target)+'\n',str(base/'shared')+'\n'))
   with patch.multiple(manager,HOME=base,UNITS=units,REGISTRY=base/'registry.json'):
    self.assertFalse(manager.removal_policy('meter')[0])

 def test_signed_remove_and_reinstall_delegate_to_fixed_root_operations(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);cfg=base/'updater.json';cfg.write_text('{}');job=base/('a'*32);job.mkdir()
   with patch.object(manager,'UPDATER_CONFIG',cfg),patch.object(manager,'activate',return_value={'ok':True}) as action,patch.object(manager,'scan',return_value={}),patch.object(manager,'register'),patch.object(manager,'unpack') as unpack:
    manager.remove('meter',job,True,lambda _:None)
    action.assert_called_once_with('meter','remove-signed',job,job/'install.log',True)
    action.reset_mock();manager.provision('meter',job,lambda _:None)
    action.assert_called_once_with('meter','install-signed',job,job/'install.log')
    unpack.assert_not_called()

 def test_root_helper_wont_bypass_guarded_instrument_check(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);target=base/'tektronix-controller';target.mkdir();units=base/'units';units.mkdir()
   (target/'maintenance_entry.py').write_text(guarded_entry('scope'))
   unit=units/'tektronix-controller.service'
   text=f'User=pi\nWorkingDirectory={target}\nExecStart={target}/venv/bin/gunicorn --bind 0.0.0.0:8081 maintenance_entry:app\n'
   unit.write_text(text)
   with patch.multiple(activate,BASE=base,UNITS=units,RECORDS=base/'records',SIGNED_ACTIVE=base/'absent'),patch.object(activate.os,'geteuid',return_value=0),patch.object(activate,'run') as run:
    with self.assertRaisesRegex(RuntimeError,'signed removal'):activate.perform('scope','remove',{'job':'b'*32})
    self.assertEqual(unit.read_text(),text);run.assert_not_called()

 @unittest.skipUnless(os.geteuid()==0,'Root-owned private-state fixture')
 def test_signed_safety_refusal_does_not_remove_or_change_enrollment(self):
  from maintenance import cli
  from maintenance.linux import LinuxHost
  from maintenance.engine import Engine
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);state={'schema':1,'sequence':2,'components':{'meter':{'version':'v1.0.0'}}}
   (root/'installed.json').write_text(json.dumps(state))
   @contextmanager
   def refuse(host,tools):raise RuntimeError('output not verified');yield
   with patch.object(cli,'ROOT',root),patch.object(cli,'config',return_value={'key':'fixture'}),patch.object(LinuxHost,'quiesce',refuse),patch.object(manager,'_remove') as remove,patch.object(manager,'STATE',root/'old'),patch.object(activate,'SIGNED_ACTIVE',root/'active'):
    with self.assertRaisesRegex(RuntimeError,'not verified'):activate.signed_operation('meter','remove-signed',{'job':'c'*32,'keep_settings':True})
    remove.assert_not_called();self.assertEqual(json.loads((root/'installed.json').read_text()),state)
    self.assertFalse((root/'active').exists())

 @unittest.skipUnless(os.geteuid()==0,'Root-owned private-state fixture')
 def test_signed_removal_updates_only_selected_enrollment_and_keeps_sequence(self):
  from maintenance import cli
  from maintenance.linux import LinuxHost
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);home=root/'home';home.mkdir()
   (home/'meter').mkdir();(home/'supply').mkdir();(home/'supply/app.py').write_text('other controller')
   state={'schema':1,'sequence':2,'components':{'meter':{'version':'v1.0.0'},'supply':{'version':'v1.0.3'}}}
   (root/'installed.json').write_text(json.dumps(state))
   @contextmanager
   def safe(host,tools):self.assertEqual(tools,['meter']);yield
   def remove(tool,job,keep,notify,verified=False):
    self.assertTrue(verified);self.assertTrue(keep);self.assertTrue((root/'active').exists())
    return {'archive':'fixture'}
   with patch.object(cli,'ROOT',root),patch.object(cli,'config',return_value={'key':'fixture'}),patch.object(LinuxHost,'quiesce',safe),patch.object(LinuxHost,'folder',lambda host,n:home/n),patch.object(manager,'_remove',side_effect=remove),patch.object(manager,'STATE',root/'old'),patch.object(activate,'SIGNED_ACTIVE',root/'active'),patch('deployment_profile.SECURITY',root/'absent'):
    activate.signed_operation('meter','remove-signed',{'job':'d'*32,'keep_settings':True})
   updated=json.loads((root/'installed.json').read_text())
   self.assertEqual(updated['sequence'],2);self.assertEqual(updated['components'],{'supply':{'version':'v1.0.3'}})
   self.assertEqual((home/'supply/app.py').read_text(),'other controller');self.assertFalse((root/'active').exists())

 @unittest.skipUnless(os.geteuid()==0,'Root-owned private-state fixture')
 def test_signed_reinstall_restores_settings_before_start_without_zip_unpack(self):
  from maintenance import cli
  from maintenance.engine import Engine
  from maintenance.linux import LinuxHost
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);home=root/'home';target=home/'hp34401a';target.mkdir(parents=True)
   (target/'standalone_app.py').write_text('fixture application')
   archive=root/'catalog/removed/meter'/('e'*32)/'app';archive.mkdir(parents=True)
   (root/'catalog').chmod(0o700)
   (archive/'appearance.json').write_text('{"saved":"exact"}')
   retained=root/'catalog/retained';retained.mkdir()
   (retained/'meter.json').write_text(json.dumps({'job':'e'*32,'keep_settings':True}))
   def apply(engine,manifest,requested):
    self.assertEqual(requested,['meter']);engine.host.start(['meter'],['meter']);return {'installed':True}
   def start(host,affected,changes):
    self.assertEqual((target/'appearance.json').read_text(),'{"saved":"exact"}')
   with patch.object(cli,'ROOT',root),patch.object(cli,'config',return_value={'key':'fixture'}),patch.object(cli,'latest_url',return_value='fixture'),patch.object(Engine,'release',return_value={'signed':'fixture'}),patch.object(Engine,'apply',apply),patch.object(LinuxHost,'folder',lambda host,n:home/manager.APP_DIRS[n]),patch.object(LinuxHost,'start',start),patch.object(manager,'STATE',root/'old'),patch('deployment_profile.secure_gateway',return_value=False),patch.object(manager,'unpack') as unpack:
    self.assertEqual(activate.signed_operation('meter','install-signed',{'job':'f'*32}),{'installed':True});unpack.assert_not_called()

if __name__=='__main__':unittest.main()
