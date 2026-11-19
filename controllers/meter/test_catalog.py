import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from flask import Flask
import catalog_web
import manager_engine as engine
import catalog_service
import activate

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask('catalog-test');catalog_web.install(self.app);self.client=self.app.test_client()

    def test_catalog_page_is_local_and_does_not_open_hardware(self):
        with patch.object(catalog_web,'helper') as helper:
            self.assertEqual(self.client.get('/api/suite/manager').status_code,200)
            helper.assert_not_called()

    def test_install_rejects_cross_origin_and_arbitrary_commands(self):
        with patch.object(catalog_web,'helper') as helper:
            for body in ({'tool':'../../bin/sh'},{'tool':'meter','command':'anything'},{'tool':'unknown'}):
                self.assertEqual(self.client.post('/api/control/suite/install',json=body,headers={'Origin':'http://localhost'}).status_code,400)
            self.assertEqual(self.client.post('/api/control/suite/install',json={'tool':'meter'},headers={'Origin':'http://other'}).status_code,403)
            helper.assert_not_called()

    def test_installs_pass_only_a_fixed_catalog_id(self):
        with patch.object(catalog_web,'helper',return_value={'job':'abc'}) as helper:
            self.assertEqual(self.client.post('/api/control/suite/install',json={'tool':'scope'},headers={'Origin':'http://localhost'}).status_code,202)
            helper.assert_called_once_with({'action':'install','tool':'scope'})

    def test_package_tampering_and_path_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'packages').mkdir();archive=root/'packages/meter.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside','bad')
            metadata={'tools':{'meter':{'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}}}
            with patch.object(engine,'ROOT',root),patch.object(engine,'catalog',return_value=metadata):
                with self.assertRaisesRegex(RuntimeError,'Unsafe'):engine.unpack('meter',root/'stage')
                metadata['tools']['meter']['sha256']='0'*64
                with self.assertRaisesRegex(RuntimeError,'checksum'):engine.unpack('meter',root/'stage')
            self.assertFalse((root.parent/'outside').exists())

    def test_single_job_admission_and_approved_ids(self):
        with tempfile.TemporaryDirectory() as d,patch.object(engine,'STATE',Path(d)),patch.object(catalog_service.threading.Thread,'start'):
            manager=catalog_service.Manager();manager.execute({'action':'install','tool':'meter'})
            with self.assertRaisesRegex(RuntimeError,'Another'):manager.execute({'action':'install','tool':'scope'})
            with self.assertRaises(ValueError):manager.execute({'action':'install','tool':'shell'})

    def test_existing_application_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);target=home/'hp6033a';target.mkdir();(target/'config.json').write_text('preserve')
            with patch.object(engine,'HOME',home),patch.object(engine,'UNITS',home/'units'),patch.object(engine,'scan',return_value={}):
                with self.assertRaisesRegex(RuntimeError,'Existing files'):engine.provision('supply',home/'job',lambda _:None)
            self.assertEqual((target/'config.json').read_text(),'preserve')

    def test_service_helper_validates_job_and_tool_before_any_command(self):
        with patch.object(activate.os,'geteuid',return_value=0),patch.object(activate,'run') as run:
            for tool,action,data in [('shell','start',{'job':'a'*32}),('meter','exec',{'job':'a'*32}),('meter','start',{'job':'../../etc'})]:
                with self.assertRaises(ValueError):activate.perform(tool,action,data)
            run.assert_not_called()

    def test_registration_records_only_verified_installed_tools(self):
        with tempfile.TemporaryDirectory() as d,patch.object(engine,'SUITE',Path(d)),patch.object(engine,'REGISTRY',Path(d)/'registry.json'),patch.object(engine,'scan',return_value={'meter':{'port':8082,'scheme':'http','path':'/multimeter/classic'}}):
            engine.register()
            self.assertEqual(json.loads((Path(d)/'tools.json').read_text()),{'instruments':['meter']})
            self.assertEqual(list(json.loads((Path(d)/'registry.json').read_text())['instruments']),['meter'])

    def test_activation_and_rollback_manage_only_the_new_fixed_service(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);units=home/'units';units.mkdir();records=home/'records'
            other=units/'hp6033a.service';other.write_text('preserve supply')
            with patch.multiple(activate,BASE=home,UNITS=units,RECORDS=records),patch.object(activate.os,'geteuid',return_value=0),patch.object(activate,'run') as run:
                activate.perform('scope','start',{'job':'a'*32})
                text=(units/'tektronix-controller.service').read_text()
                self.assertEqual((units/'tektronix-controller.service').stat().st_mode & 0o777,0o644)
                self.assertIn('User=pi',text);self.assertIn('--bind 0.0.0.0:8081',text)
                activate.perform('scope','rollback',{'job':'a'*32})
                self.assertFalse((units/'tektronix-controller.service').exists())
                self.assertEqual(other.read_text(),'preserve supply')
                self.assertFalse(any('hp6033a' in str(c) for c in run.call_args_list))

    def test_activation_preserves_existing_service_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            units=Path(d);existing=units/'hp34401a.service';existing.write_text('existing service')
            with patch.multiple(activate,UNITS=units,RECORDS=units/'records'),patch.object(activate.os,'geteuid',return_value=0),patch.object(activate,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'Existing service'):activate.perform('meter','start',{'job':'b'*32})
                run.assert_not_called()
            self.assertEqual(existing.read_text(),'existing service')
