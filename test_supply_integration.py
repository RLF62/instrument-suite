"""Fresh supply payload imports and exposes the actual guarded controller."""
import importlib.util
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from flask import Flask
from maintenance.guard import Guard
from maintenance.linux import LinuxHost
from tools.build_candidate import apply_supply_wrapper

class SupplyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.suite=Path(__file__).resolve().parent
        self.payload=self.root/'payload';self.payload.mkdir()

    def test_wrapper_is_included_from_reviewed_suite_source(self):
        apply_supply_wrapper(self.suite,self.payload)
        self.assertEqual((self.payload/'supply_standalone.py').read_bytes(),
                         (self.suite/'integration/supply_standalone.py').read_bytes())

    def test_missing_or_symlinked_wrapper_blocks_build(self):
        suite=self.root/'suite';(suite/'integration').mkdir(parents=True)
        with self.assertRaisesRegex(SystemExit,'wrapper'):
            apply_supply_wrapper(suite,self.payload)
        (suite/'integration/supply_standalone.py').symlink_to(self.suite/'integration/supply_standalone.py')
        with self.assertRaisesRegex(SystemExit,'wrapper'):
            apply_supply_wrapper(suite,self.payload)

    def load_wrapper(self,output=0,remote=False):
        module=ModuleType('app');module.app=Flask('inert-supply-fixture')
        module.remote_control_enabled=remote
        module.read_gpib=lambda:{'OUT':output}
        module.control_password_required=lambda:True
        spec=importlib.util.spec_from_file_location('fixture_supply_standalone',self.suite/'integration/supply_standalone.py')
        wrapper=importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules',{'app':module}):spec.loader.exec_module(wrapper)
        return wrapper,module

    def test_actual_wrapper_exports_the_supply_module_for_existing_entry_protocol(self):
        wrapper,module=self.load_wrapper()
        self.assertIs(wrapper.controller,module)
        self.assertEqual(Guard('supply',wrapper.controller).check()['output'],False)

    def test_wrapper_does_not_bypass_output_or_remote_safety_interlocks(self):
        for output,remote in ((1,False),(0,True)):
            wrapper,_=self.load_wrapper(output,remote)
            with self.subTest(output=output,remote=remote),self.assertRaisesRegex(RuntimeError,'OUTPUT OFF'):
                Guard('supply',wrapper.controller).check()

    def test_http_wrapper_still_rejects_foreign_control_origins(self):
        wrapper,module=self.load_wrapper()
        wrapper.app.add_url_rule('/api/control/fixture','fixture',lambda:'ok')
        client=wrapper.app.test_client()
        self.assertEqual(client.get('/api/control/fixture',headers={'Origin':'http://foreign.invalid'}).status_code,403)
        self.assertEqual(client.get('/api/control/fixture',headers={'Origin':'http://localhost'}).status_code,200)

    def test_build_only_wrapper_asset_does_not_restart_existing_controllers(self):
        source=self.root/'source';(source/'integration').mkdir(parents=True)
        (source/'integration/supply_standalone.py').write_text('reviewed build asset')
        (source/'test_build_release.py').write_text('# build-time tests only')
        (source/'test_supply_integration.py').write_text('# build-time tests only')
        host=LinuxHost(self.root/'state',self.root/'home')
        actual=host.refine_affected({'suite':source},['suite','meter','scope'])
        self.assertEqual(actual,['suite'])
        self.assertFalse(host.restart_broker)

    def test_new_controller_has_no_existing_service_to_quiesce(self):
        source=self.root/'new-suite';(source/'integration').mkdir(parents=True)
        (source/'integration/supply_standalone.py').write_text('reviewed build asset')
        host=LinuxHost(self.root/'state',self.root/'home')
        affected=host.refine_affected({'suite':source,'supply':self.payload},['suite','meter','scope'])
        self.assertEqual(affected,['suite'])
        self.assertFalse(host.restart_broker)

    def test_existing_changed_controller_still_requires_its_safety_lease(self):
        source=self.root/'existing-suite';(source/'integration').mkdir(parents=True)
        (source/'integration/supply_standalone.py').write_text('reviewed build asset')
        host=LinuxHost(self.root/'state',self.root/'home')
        affected=host.refine_affected({'suite':source,'supply':self.payload},['suite','meter','scope','supply'])
        self.assertEqual(affected,['suite','supply'])
        self.assertFalse(host.restart_broker)

    def run_real_app_smoke(self,payload):
        import subprocess,sys,json
        script = r'''
import importlib.util,json,socket,sys,types
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from flask import Flask
from maintenance.guard import Guard
payload=Path(sys.argv[1]);calls=[]
client=types.ModuleType('gpib_client')
def execute(tool,action,**data):
    calls.append([tool,action])
    if tool!='supply' or action!='snapshot' or data:raise RuntimeError('Instrument write blocked by fixture')
    return {'OUT':0,'VSET':0,'ISET':1,'VOUT':0,'IOUT':0,'STS':0}
client.execute=execute;sys.modules['gpib_client']=client
def blocked(*args,**kwargs):raise RuntimeError('All network and Unix socket access blocked by fixture')
socket.socket=blocked
spec=importlib.util.spec_from_file_location('app',payload/'app.py')
module=importlib.util.module_from_spec(spec);sys.modules['app']=module
spec.loader.exec_module(module)
spec=importlib.util.spec_from_file_location('supply_standalone',payload/'supply_standalone.py')
wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
assert wrapper.controller is module
assert module.remote_control_enabled is False
assert callable(module.read_gpib)
assert calls==[], 'Application import attempted instrument I/O'
web=wrapper.app.test_client()
for path in ('/','/classic-dual'):assert web.get(path).status_code==200
assert calls==[], 'Page rendering attempted instrument I/O'
assert Guard('supply',wrapper.controller).check()['verified'] is True
assert calls==[['supply','snapshot']]
print(json.dumps({'real_app_imported':True,'dashboards_http':200,'socket_access_blocked':True,'only_simulated_readback':True}))
'''
        result=subprocess.run([sys.executable,'-I','-c',script,str(payload),str(self.suite)],
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr[-2000:])
        return json.loads(result.stdout)

    def test_reviewed_real_supply_app_boots_and_renders_with_all_instrument_io_blocked(self):
        import hashlib,json,subprocess,sys,zipfile
        from maintenance.security import safe_member
        from tools.build_candidate import apply_suite_templates
        archive=self.suite/'approved/packages/supply.zip'
        expected=json.loads((self.suite/'approved/catalog.json').read_text())['tools']['supply']['sha256']
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),expected)
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                if member.is_dir() or member.filename.startswith('.'):continue
                rel=safe_member(member.filename)
                self.assertNotEqual((member.external_attr>>16)&0o170000,0o120000)
                target=self.payload.joinpath(*rel.parts)
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(source.read(member))
        subprocess.run([sys.executable,str(self.suite/'patch_hp.py'),str(self.payload/'app.py')],check=True,capture_output=True)
        app=self.payload/'app.py'
        text=app.read_text().replace('from hp34401a import install as install_meter\\ninstall_meter(app)\\n\\n','')
        # The string above represents real newlines after decoding.
        text=text.replace('from hp34401a import install as install_meter\ninstall_meter(app)\n\n','')
        app.write_text(text)
        self.assertNotIn('ResourceManager',text)
        apply_suite_templates(self.suite,self.payload);apply_supply_wrapper(self.suite,self.payload)
        result=self.run_real_app_smoke(self.payload)
        self.assertTrue(result['real_app_imported'])
        self.assertTrue(result['socket_access_blocked'])
