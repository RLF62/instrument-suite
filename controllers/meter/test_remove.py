import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from flask import Flask
import activate
import catalog_web
import manager_engine as engine

class RemovalTests(unittest.TestCase):
    def test_explicit_confirmation_and_origin_are_required(self):
        app=Flask('remove-test');catalog_web.install(app);client=app.test_client()
        with patch.object(catalog_web,'helper',return_value={'job':'ok'}) as helper:
            for data in ({'tool':'scope','keep_settings':True,'confirm':False},{'tool':'scope','keep_settings':'true','confirm':True},{'tool':'../other','keep_settings':True,'confirm':True}):
                self.assertEqual(client.post('/api/control/suite/remove',json=data,headers={'Origin':'http://localhost'}).status_code,400)
            self.assertEqual(client.post('/api/control/suite/remove',json={'tool':'scope','keep_settings':True,'confirm':True},headers={'Origin':'http://other'}).status_code,403)
            helper.assert_not_called()
            self.assertEqual(client.post('/api/control/suite/remove',json={'tool':'scope','keep_settings':True,'confirm':True},headers={'Origin':'http://localhost'}).status_code,202)
            helper.assert_called_once_with({'action':'remove','tool':'scope','keep_settings':True,'confirm':True})

    def exercise(self,tool='scope',keep=True,fail=False,polling=False):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);state=home/'state';state.mkdir();units=home/'units';units.mkdir();target=home/engine.APP_DIRS[tool];target.mkdir()
            config=target/('connection.json' if tool=='scope' else 'appearance.json');config.write_text('{"saved":"exact settings"}')
            (target/'venv/bin').mkdir(parents=True);(target/'venv/bin/python').write_text('shared interpreter')
            other=home/'other-controller.json';other.write_text('unchanged')
            if tool=='meter':(units/'fischer-gpib.service').write_text('ExecStart='+str(target/'venv/bin/python'))
            job=state/('a'*32);job.mkdir();(job/'install.log').touch()
            register_effect=[RuntimeError('registry failure'),None] if fail else None
            with patch.multiple(engine,HOME=home,STATE=state,UNITS=units),patch.object(engine,'removal_policy',return_value=(True,'')), \
                 patch.object(engine.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps({'polling':polling,'remote_control_enabled':False}).encode())), \
                 patch.object(engine,'activate',return_value={'removed_service':True,'restored':True,'committed':True}) as action, \
                 patch.object(engine,'register',side_effect=register_effect):
                if polling:
                    with self.assertRaisesRegex(RuntimeError,'Pause'):engine.remove(tool,job,keep,lambda _:None)
                    action.assert_not_called();self.assertTrue(config.exists());return
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'registry failure'):engine.remove(tool,job,keep,lambda _:None)
                    self.assertEqual(config.read_text(),'{"saved":"exact settings"}')
                    self.assertTrue(any(c.args[1]=='restore-remove' for c in action.call_args_list));return
                result=engine.remove(tool,job,keep,lambda _:None)
                self.assertEqual(other.read_text(),'unchanged')
                archive=Path(result['archive']);self.assertEqual((archive/config.name).read_text(),'{"saved":"exact settings"}')
                self.assertFalse(config.exists());self.assertEqual(result['keep_settings'],keep)
                if tool=='meter':
                    self.assertTrue(engine.is_runtime_stub(tool));self.assertEqual((target/'venv/bin/python').read_text(),'shared interpreter')
                    self.assertTrue((units/'fischer-gpib.service').exists())
                else:self.assertFalse(target.exists());target.mkdir()
                config.write_text('{"fresh":true}');engine.restore_settings(tool,target)
                self.assertEqual(config.read_text(),'{"saved":"exact settings"}' if keep else '{"fresh":true}')

    def test_remove_and_restore_scope_settings(self):self.exercise()
    def test_fresh_reinstall_does_not_restore_unselected_settings(self):self.exercise(keep=False)
    def test_primary_broker_runtime_is_retained_without_restarting_bus(self):self.exercise(tool='meter')
    def test_registry_failure_rolls_back_application_and_settings(self):self.exercise(fail=True)
    def test_running_acquisition_is_refused_without_stopping_any_service(self):self.exercise(polling=True)

    def test_root_helper_removes_and_recovers_only_the_selected_service(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);units=home/'units';units.mkdir();records=home/'records'
            text=f'User=pi\nWorkingDirectory={home}/tektronix-controller\nExecStart={home}/tektronix-controller/venv/bin/gunicorn --bind 0.0.0.0:8081 app:app\n'
            unit=units/'tektronix-controller.service';unit.write_text(text)
            other=units/'fischer-gpib.service';other.write_text('preserve broker')
            with patch.multiple(activate,BASE=home,UNITS=units,RECORDS=records),patch.object(activate.os,'geteuid',return_value=0),patch.object(activate,'run') as run,patch.object(activate.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
                activate.perform('scope','remove',{'job':'b'*32});self.assertFalse(unit.exists())
                activate.perform('scope','restore-remove',{'job':'b'*32});self.assertEqual(unit.read_text(),text)
                self.assertFalse(any('fischer-gpib' in str(call) for call in run.call_args_list))
            self.assertEqual(other.read_text(),'preserve broker')

    def test_shared_legacy_controller_removal_is_not_offered(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);units=home/'units';units.mkdir();(units/'hp6033a.service').write_text('ExecStart=legacy shared web host')
            with patch.multiple(engine,HOME=home,UNITS=units):self.assertFalse(engine.removal_policy('supply')[0])

    def test_last_removal_clears_stale_navigation(self):
        with tempfile.TemporaryDirectory() as d,patch.multiple(engine,SUITE=Path(d),REGISTRY=Path(d)/'registry.json'),patch.object(engine,'scan',return_value={}):
            engine.atomic(engine.REGISTRY,{'schema':1,'instruments':{'scope':{}}});engine.register(force=True)
            self.assertEqual(json.loads(engine.REGISTRY.read_text())['instruments'],{})

    def test_recovery_archive_rejects_path_traversal(self):
        with self.assertRaises(ValueError):engine.checked_archive('scope','../../outside')

    def test_integrated_meter_is_not_confused_with_a_second_standalone_host(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);units=home/'units';units.mkdir();registry=home/'registry.json'
            engine.atomic(registry,{'instruments':{'meter':{'folder':str(home/'instrument-suite/hp34401a')}}})
            (units/'hp34401a.service').write_text(f'WorkingDirectory={home}/hp34401a\nExecStart=gunicorn --bind 0.0.0.0:8082 standalone_app:app')
            with patch.multiple(engine,HOME=home,UNITS=units,REGISTRY=registry):self.assertFalse(engine.removal_policy('meter')[0])

    def test_reinstall_reuses_shared_runtime_without_pip_or_venv_changes(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);state=home/'state';state.mkdir();units=home/'units';units.mkdir();target=home/'hp34401a'
            (target/'venv/bin').mkdir(parents=True);python=target/'venv/bin/python';python.write_text('running broker interpreter')
            engine.atomic(target/'.shared-broker-runtime.json',{'tool':'meter','runtime_only':True})
            job=state/('c'*32);job.mkdir();(job/'install.log').touch()
            def package(tool,source):
                for name in ('standalone_app.py','gpib_client.py','suite_navigation.py','navigation.js','catalog_web.py','catalog.html','tool_registration.py','requirements.txt'):(source/name).write_text('fixture')
                (source/'hp34401a').mkdir();return source
            with patch.multiple(engine,HOME=home,STATE=state,UNITS=units),patch.object(engine,'scan',return_value={}),patch.object(engine,'unpack',side_effect=package),patch.object(engine,'command') as command,patch.object(engine,'ensure_broker'),patch.object(engine,'activate'),patch.object(engine,'healthy',return_value=True),patch.object(engine,'register',return_value={'meter':{'port':8082}}):
                engine.provision('meter',job,lambda _:None)
                self.assertFalse(any('pip' in call.args[0] or 'venv' in call.args[0] for call in command.call_args_list))
                self.assertEqual(python.read_text(),'running broker interpreter')
                self.assertFalse((target/'.shared-broker-runtime.json').exists())
