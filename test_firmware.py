"""Firmware workflow tests; no real hardware or services are touched."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask
from maintenance import firmware as fw
from maintenance import firmware_web as web
from maintenance import helper
from maintenance.security import MaintenanceError, atomic_json
from maintenance.web_policy import disabled
from maintenance.engine import exclusive

class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.host=MagicMock()
        self.host.lock_path=self.root/'lock'
        self.f=fw.Firmware(self.root,self.host)
        self.f.directory.mkdir()
        self.disk=self.root/'disk';self.disk.mkdir()
        (self.disk/'FLASH.BIN').write_bytes(b'O'*24576)
        (self.disk/'EEPROM.BIN').write_bytes(b'E'*1023)
        (self.f.directory/'FLASH.BIN').write_bytes(b'N'*1024)
        self.device={'usb':'/sys/bus/usb/devices/1-1','device':'/dev/sdz'}
        self.f.selected=MagicMock(return_value=self.device)
        self.f.mounted=lambda d,mode,callback:callback(self.disk)
        self.valid=patch.object(fw,'validate_image',side_effect=lambda d:d);self.valid.start();self.addCleanup(self.valid.stop)
        self.s={'id':'session','phase':'awaiting_bootloader','units':['fischer-gpib','hp34401a'],'usb_port':'1-1'}
        self.f.save(self.s);atomic_json(self.root/'pending.flag',{'components':['meter'],'firmware':'session'})
        self.host.service.side_effect=lambda n:{'meter':'hp34401a','supply':'hp6033a'}[n]
        self.host.run.side_effect=self.run_command
    def run_command(self,args,**kwargs):
        if args[0]=='dd':
            old=(self.disk/'FLASH.BIN').read_bytes()
            image=(self.f.directory/'FLASH.BIN').read_bytes()
            (self.disk/'FLASH.BIN').write_bytes(image+old[len(image):])
        return ''
    def test_verified_write_backs_up_application_and_eeprom(self):
        result=self.f.flash();self.assertEqual(result['phase'],'awaiting_power_cycle')
        self.assertEqual((Path(result['backup'])/'EEPROM.BIN').read_bytes(),b'E'*1023)
        self.assertEqual((Path(result['backup'])/'FLASH.BIN').read_bytes(),b'O'*24576)
        self.assertTrue(result['eeprom_unchanged']);self.assertTrue((self.root/'pending.flag').exists())
        dd=[c.args[0] for c in self.host.run.call_args_list if c.args[0][0]=='dd'][0]
        self.assertIn('conv=notrunc',dd);self.assertIn('oflag=direct,sync',dd)
    def test_wrong_usb_port_prevents_write(self):
        self.device['usb']='/sys/devices/1-2'
        with self.assertRaises(MaintenanceError):self.f.flash()
        self.host.run.assert_not_called()
    def test_unexpected_file_geometry_prevents_write(self):
        (self.disk/'EEPROM.BIN').write_bytes(b'E')
        with self.assertRaises(MaintenanceError):self.f.flash()
        self.host.run.assert_not_called()
    def test_readback_failure_keeps_recovery_gate(self):
        self.host.run.side_effect=lambda *a,**k:''
        with self.assertRaises(MaintenanceError):self.f.flash()
        self.assertEqual(self.f.state()['phase'],'write_failed')
        self.assertTrue((self.root/'pending.flag').exists())
    def test_eeprom_change_is_detected(self):
        def corrupt(args,**kwargs):
            self.run_command(args,**kwargs)
            if args[0]=='dd':(self.disk/'EEPROM.BIN').write_bytes(b'X'*1023)
            return ''
        self.host.run.side_effect=corrupt
        with self.assertRaises(MaintenanceError):self.f.flash()
        self.assertEqual(self.f.state()['phase'],'write_failed')
    def test_tail_corruption_is_detected(self):
        def corrupt(args,**kwargs):
            self.run_command(args,**kwargs)
            if args[0]=='dd':
                p=self.disk/'FLASH.BIN';data=p.read_bytes();p.write_bytes(data[:-1]+b'X')
            return ''
        self.host.run.side_effect=corrupt
        with self.assertRaises(MaintenanceError):self.f.flash()
    def test_interrupted_write_can_retry_using_original_backup(self):
        result=self.f.flash();original=result['backup']
        result['phase']='writing';self.f.save(result)
        result=self.f.flash();self.assertEqual(result['backup'],original)
        self.assertEqual((Path(original)/'FLASH.BIN').read_bytes(),b'O'*24576)
    def test_retry_rejects_changed_eeprom_against_original_backup(self):
        result=self.f.flash();result['phase']='write_failed';self.f.save(result)
        (self.disk/'EEPROM.BIN').write_bytes(b'X'*1023);self.host.run.reset_mock()
        with self.assertRaises(MaintenanceError):self.f.flash()
        self.host.run.assert_not_called()
    def test_cancel_after_attempted_write_is_blocked(self):
        self.f.flash()
        with self.assertRaises(MaintenanceError):self.f.cancel()
    def test_wrong_running_version_keeps_controllers_paused(self):
        self.f.flash()
        with patch.object(self.f,'runtime_version',return_value='V2.4'):
            with self.assertRaises(MaintenanceError):self.f.resume()
        self.host.health.assert_not_called();self.assertTrue(self.f.pending.exists())
    def test_resume_checks_version_then_restores_prior_units(self):
        self.f.flash()
        with patch.object(self.f,'runtime_version',return_value='V2.5'):result=self.f.resume()
        self.assertEqual(result['phase'],'completed');self.assertFalse(self.f.pending.exists())
        self.assertFalse((self.root/'pending.flag').exists());self.host.health.assert_called_once()
        self.assertEqual(self.f.status()['last_session']['runtime_version'],'V2.5')
    def test_failed_service_health_keeps_gate_for_retry(self):
        self.f.flash();self.host.health.side_effect=MaintenanceError('unhealthy')
        with patch.object(self.f,'runtime_version',return_value='V2.5'):
            with self.assertRaises(MaintenanceError):self.f.resume()
        self.assertTrue(self.f.pending.exists());self.assertTrue((self.root/'pending.flag').exists())
    def test_cancel_requires_verified_original_runtime(self):
        with patch.object(self.f,'runtime_version',side_effect=MaintenanceError('missing')):
            with self.assertRaises(MaintenanceError):self.f.cancel()
        self.assertTrue(self.f.pending.exists())
    def test_other_software_recovery_blocks_firmware(self):
        (self.root/'pending.json').write_text('{}')
        with self.assertRaises(MaintenanceError):self.f.execute('flash')
        self.host.run.assert_not_called()
    def test_pending_firmware_blocks_software_under_shared_lock(self):
        import maintenance.engine as engine
        actual=Path
        with patch.object(engine,'Path',side_effect=lambda value: self.f.pending if str(value)=='/var/lib/fischer-suite-updater/firmware-pending.json' else actual(value)):
            with self.assertRaises(MaintenanceError):
                with exclusive(self.host.lock_path):pass
            with exclusive(self.host.lock_path,allow_firmware=True):pass
    def test_invalid_firmware_is_rejected_before_service_stop(self):
        self.valid.stop();self.f.pending.unlink()
        with patch.object(fw,'normal_usb',return_value=['1-1']),patch.object(fw,'devices',return_value=[]),patch.object(fw.urllib.request,'urlopen') as download:
            download.return_value.__enter__.return_value.geturl.return_value=fw.IMAGE['url']
            download.return_value.__enter__.return_value.read.return_value=b'invalid'
            with self.assertRaises(MaintenanceError):self.f.prepare()
        self.host.quiesce.assert_not_called();self.host.run.assert_not_called()
    def test_multiple_adapters_prevents_preparation(self):
        self.f.pending.unlink()
        with patch.object(fw,'normal_usb',return_value=['1-1','1-2']),patch.object(fw,'devices',return_value=[]):
            with self.assertRaises(MaintenanceError):self.f.prepare()
        self.host.quiesce.assert_not_called()

class WebTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);web.install(self.app);self.client=self.app.test_client()
        self.policy=disabled();self.policy.update(mode='trusted-lan',origins=['http://bench:8080'],trusted_lans=['192.168.1.0/24'])
        self.p=patch.object(web,'read_policy',return_value=self.policy);self.p.start();self.addCleanup(self.p.stop)
        self.h=patch.object(web,'helper',return_value={'firmware':{},'job':None});self.h.start();self.addCleanup(self.h.stop)
    def get(self):
        return self.client.get('/api/gpib-firmware',base_url='http://bench:8080',environ_overrides={'REMOTE_ADDR':'192.168.1.22'})
    def post(self,action,token=None,origin='http://bench:8080'):
        headers={'Origin':origin}
        if token:headers['X-CSRF-Token']=token
        return self.client.post('/api/gpib-firmware',base_url='http://bench:8080',environ_overrides={'REMOTE_ADDR':'192.168.1.22'},headers=headers,json={'action':action})
    def test_status_issues_scoped_csrf_cookie(self):
        r=self.get();self.assertEqual(r.status_code,200)
        self.assertIn('Path=/api/gpib-firmware',r.headers['Set-Cookie'])
    def test_write_requires_csrf(self):self.assertEqual(self.post('flash').status_code,403)
    def test_cross_origin_write_rejected(self):
        token=self.get().json['csrf'];self.assertEqual(self.post('flash',token,'http://other').status_code,403)
    def test_arbitrary_actions_and_arguments_rejected(self):
        token=self.get().json['csrf']
        for action in ('shell','firmware-flash',[],None):self.assertEqual(self.post(action,token).status_code,400)
    def test_prepare_queues_only_fixed_action(self):
        token=self.get().json['csrf'];self.assertEqual(self.post('prepare',token).status_code,202)
        web.helper.assert_called_with('firmware-prepare')
    def test_disabled_policy_denies_status(self):
        self.policy['mode']='disabled';self.assertEqual(self.get().status_code,403)
    def test_root_protocol_rejects_arbitrary_payload(self):
        for data in ({'schema':1,'action':[]},{'schema':1,'action':'firmware-flash','device':'/dev/sda'}):
            with self.assertRaises(ValueError):helper.validate(data)

if __name__=='__main__':unittest.main()

