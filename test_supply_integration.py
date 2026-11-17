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
        module.controller=SimpleNamespace(remote_control_enabled=remote,read_gpib=lambda:{'OUT':output})
        module.control_password_required=lambda:True
        spec=importlib.util.spec_from_file_location('fixture_supply_standalone',self.suite/'integration/supply_standalone.py')
        wrapper=importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules',{'app':module}):spec.loader.exec_module(wrapper)
        return wrapper,module

    def test_actual_wrapper_exports_the_concrete_controller_for_existing_entry_protocol(self):
        wrapper,module=self.load_wrapper()
        self.assertIs(wrapper.controller,module.controller)
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
        host=LinuxHost(self.root/'state',self.root/'home')
        actual=host.refine_affected({'suite':source},['suite','meter','scope'])
        self.assertEqual(actual,['suite'])
        self.assertFalse(host.restart_broker)
