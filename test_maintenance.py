"""Isolated maintenance tests: no real services, network or instruments."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock
from maintenance.engine import Engine, plan, exclusive
from maintenance.security import MaintenanceError, canonical, extract, verify_manifest, github_url, safe_member
from maintenance.guard import Guard
from maintenance.helper import validate

def manifest(tools=('suite','meter','supply','scope'), release='v1.0.0', sequence=1):
    now=dt.datetime.now(dt.timezone.utc)
    repos={'suite':'instrument-suite','meter':'hp34401a-web-controller','supply':'hp6033a-web-controller','scope':'tektronix-ethernet-controller'}
    return {'schema':1,'engine_api':1,'release':release,'sequence':sequence,
            'issued':(now-dt.timedelta(minutes=1)).isoformat(),'expires':(now+dt.timedelta(days=7)).isoformat(),
            'components':{n:{'version':release,'commit':'a'*40,'sha256':hashlib.sha256(n.encode()).hexdigest(),
                         'size':1,'url':f'https://github.com/RLF62/{repos[n]}/releases/download/{release}/{n}.tar.gz',
                         'requires':{} if n=='suite' else {'suite':'v1.0.0'}} for n in tools}}

class FakeHost:
    def __init__(self, root):
        self.root=Path(root);self.lock_path=self.root/'lock';self.tools=set();self.events=[]
        self.fail=None;self.safe=True;self.data={};self.leases=False;self.low_disk=False
    def temporary(self):return tempfile.TemporaryDirectory(dir=self.root)
    def discover(self):return self.tools.copy()
    def publish(self,state):pass
    def affected(self,changes,actual):return sorted(actual if 'suite' in changes else set(changes)&actual)
    def preflight(self,size):
        self.events.append('preflight')
        if self.low_disk:raise MaintenanceError('Low disk')
    def validate_payload(self,name,stage):self.events.append(('validate',name))
    def prepare_runtimes(self,stages,job):self.events.append('prepare')
    @contextmanager
    def quiesce(self,affected):
        self.events.append(('quiesce',tuple(affected)))
        if not self.safe:raise MaintenanceError('Output must be OFF')
        self.leases=True
        try:yield
        finally:self.leases=False
    def backup(self,job,changes,stages,state):
        self.events.append('backup');p=job/'backup';p.mkdir()
        meta={'affected':self.affected(changes,self.tools),'state':state,'data':self.data.copy(),'tools':sorted(self.tools)}
        (p/'backup.json').write_text(json.dumps(meta));return p
    def verify_backup(self,p):return json.loads((p/'backup.json').read_text())
    def stop(self,names):self.events.append(('stop',tuple(names)))
    def activate(self,stages,job):
        assert self.leases
        self.events.append(('activate',tuple(stages)))
        for n in stages:self.data[n]='new';self.tools.add(n)
        if self.fail=='activate':raise RuntimeError('Injected activation failure')
    def start(self,affected,changes):self.events.append(('start',tuple(affected),tuple(changes)))
    def health(self,affected,changes):
        self.events.append('health')
        if self.fail=='health':self.fail=None;raise RuntimeError('Injected health failure')
    def restore(self,p):
        self.events.append('restore');m=self.verify_backup(p);self.data=m['data'];self.tools=set(m['tools'])

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.host=FakeHost(self.root);self.downloaded=[]
        self.engine=Engine(self.root/'state',self.host,fetch=self.fetch)
        self.m=manifest()
    def tearDown(self):self.tmp.cleanup()
    def fetch(self,url,path,**kwargs):
        self.downloaded.append(url)
        with tarfile.open(path,'w:gz') as t:
            item=tarfile.TarInfo('app.py');data=b'# harmless test source\n';item.size=len(data);t.addfile(item,io.BytesIO(data))
        return Path(path)
    def enroll(self,tools):
        self.host.tools=set(tools);self.host.data={n:'old' for n in tools}
        state={'schema':1,'sequence':1,'components':{n:{k:self.m['components'][n][k] for k in ('version','sha256','commit')} for n in tools}}
        self.engine.root.mkdir();self.engine.state_path.write_text(json.dumps(state));return state
    def bump(self,name):
        self.m['components'][name]['version']='v1.0.1';self.m['components'][name]['sha256']='f'*64;self.m['sequence']=2
    def test_fresh_one_controller(self):
        result=self.engine.apply(self.m,['meter']);self.assertEqual(self.host.tools,{'suite','meter'});self.assertEqual(len(self.downloaded),2)
    def test_fresh_two_controllers(self):
        self.engine.apply(self.m,['meter','scope']);self.assertEqual(self.host.tools,{'suite','meter','scope'})
    def test_fresh_three_controllers(self):
        self.engine.apply(self.m,['meter','scope','supply']);self.assertEqual(len(self.host.tools),4)
    def test_no_change_downloads_and_restarts_nothing(self):
        self.enroll(['suite','meter']);result=self.engine.apply(self.m);self.assertFalse(self.downloaded);self.assertFalse(self.host.events);self.assertIn('Already',result['result'])
    def test_meter_update_preserves_unrelated_controllers(self):
        self.enroll(['suite','meter','supply','scope']);self.bump('meter');self.engine.apply(self.m)
        self.assertEqual(len(self.downloaded),1);self.assertEqual(self.host.data['supply'],'old');self.assertEqual(self.host.data['scope'],'old')
        self.assertIn(('stop',('meter',)),self.host.events)
    def test_suite_update_quiesces_all(self):
        self.enroll(['suite','meter','supply','scope']);self.bump('suite');self.engine.apply(self.m)
        self.assertIn(('quiesce',('meter','scope','suite','supply')),self.host.events)
    def test_add_scope_does_not_restart_meter(self):
        self.enroll(['suite','meter']);self.engine.apply(self.m,['scope']);self.assertIn('scope',self.host.tools);self.assertNotIn(('stop',('meter',)),self.host.events)
    def test_unsafe_state_blocks_all_activation(self):
        self.enroll(['suite','supply']);self.bump('supply');self.host.safe=False
        with self.assertRaises(MaintenanceError):self.engine.apply(self.m)
        self.assertEqual(self.host.data['supply'],'old');self.assertNotIn('backup',self.host.events);self.assertFalse(self.engine.pending.exists())
    def test_unmanaged_legacy_installation_is_preserved(self):
        self.host.tools={'suite','supply'}
        with self.assertRaisesRegex(MaintenanceError,'legacy'):self.engine.apply(self.m)
        self.assertFalse(self.downloaded)
    def test_low_disk_blocks_download(self):
        self.host.low_disk=True
        with self.assertRaises(MaintenanceError):self.engine.apply(self.m,['meter'])
        self.assertFalse(self.downloaded)
    def test_dry_run_changes_no_files_or_services(self):
        self.engine.apply(self.m,['meter'],dry_run=True);self.assertFalse(self.engine.root.exists());self.assertFalse(self.host.events);self.assertFalse(self.downloaded)
    def test_activation_failure_restores_old_code_and_state(self):
        state=self.enroll(['suite','meter']);self.bump('meter');self.host.fail='activate'
        with self.assertRaisesRegex(MaintenanceError,'restored'):self.engine.apply(self.m)
        self.assertEqual(self.host.data['meter'],'old');self.assertEqual(self.engine.state(),state);self.assertFalse(self.engine.pending.exists())
    def test_failed_health_rolls_back(self):
        self.enroll(['suite','meter']);self.bump('meter');self.host.fail='health'
        with self.assertRaisesRegex(MaintenanceError,'restored'):self.engine.apply(self.m)
        self.assertEqual(self.host.data['meter'],'old')
    def test_network_failure_never_stops_services(self):
        self.engine.fetch=MagicMock(side_effect=OSError('connection interrupted'))
        with self.assertRaises(OSError):self.engine.apply(self.m,['meter'])
        self.assertFalse(any(isinstance(x,tuple) and x[0]=='stop' for x in self.host.events))
    def test_pending_journal_blocks_new_update(self):
        self.engine.root.mkdir();self.engine.pending.write_text('{}')
        with self.assertRaisesRegex(MaintenanceError,'Interrupted'):self.engine.apply(self.m,['meter'])
    def test_failed_recovery_keeps_gate_and_journal(self):
        self.enroll(['suite','meter']);self.bump('meter');self.host.fail='activate';self.host.restore=MagicMock(side_effect=RuntimeError('disk failure'))
        with self.assertRaisesRegex(MaintenanceError,'recovery could not'):self.engine.apply(self.m)
        self.assertTrue(self.engine.pending.exists());self.assertTrue(self.engine.flag.exists())
    def test_manual_rollback_restores_software(self):
        self.enroll(['suite','meter']);self.bump('meter');self.engine.apply(self.m);self.engine.rollback();self.assertEqual(self.host.data['meter'],'old');self.assertEqual(self.engine.state()['sequence'],2)
    def test_recovery_after_power_failure(self):
        self.enroll(['suite','meter']);self.bump('meter');self.host.fail='activate';restore=self.host.restore;self.host.restore=MagicMock(side_effect=RuntimeError())
        with self.assertRaises(MaintenanceError):self.engine.apply(self.m)
        self.host.restore=restore;self.host.fail=None;self.engine.rollback();self.assertEqual(self.host.data['meter'],'old');self.assertFalse(self.engine.flag.exists())
    def test_incompatible_component_is_blocked(self):
        self.m['components']['meter']['requires']={'suite':'v9.0.0'}
        with self.assertRaises(MaintenanceError):self.engine.apply(self.m,['meter'])
    def test_newer_local_version_is_not_downgraded(self):
        state=self.enroll(['suite','meter']);state['components']['meter']['version']='v9.0.0';self.engine.state_path.write_text(json.dumps(state));self.bump('meter')
        with self.assertRaises(MaintenanceError):self.engine.apply(self.m)
    def test_lock_blocks_simultaneous_mutation(self):
        with exclusive(self.host.lock_path):
            with self.assertRaisesRegex(MaintenanceError,'Another'):self.engine.apply(self.m,['meter'])
    def test_web_helper_umask_does_not_expose_backup_parent(self):
        self.enroll(['suite','meter']);old=os.umask(0o007)
        try:self.engine.backup()
        finally:os.umask(old)
        self.assertEqual((self.engine.root/'backups').stat().st_mode&0o077,0)

class SafetyTests(unittest.TestCase):
    def test_supply_requires_explicit_remote_disabled(self):
        for value in (True,None,0):
            g=Guard('supply',types.SimpleNamespace(remote_control_enabled=value))
            with self.assertRaises(RuntimeError):g.check()
    def test_supply_requires_fresh_output_off(self):
        for value in (1,True,None,'0'):
            c=types.SimpleNamespace(remote_control_enabled=False,read_gpib=lambda:{'OUT':value})
            with self.assertRaises(RuntimeError):Guard('supply',c).check()
    def test_supply_read_only_verification(self):
        c=types.SimpleNamespace(remote_control_enabled=False,read_gpib=MagicMock(return_value={'OUT':0.0}))
        self.assertTrue(Guard('supply',c).check()['verified']);c.read_gpib.assert_called_once_with()
    def test_disconnected_supply_blocks(self):
        c=types.SimpleNamespace(remote_control_enabled=False,read_gpib=MagicMock(side_effect=OSError()))
        with self.assertRaises(OSError):Guard('supply',c).check()
    def test_meter_polling_and_queued_operations_block(self):
        for state in ({'polling':True,'pending_controls':0},{'polling':False,'pending_controls':1},{'polling':False}):
            meter=types.SimpleNamespace(snapshot=lambda:state)
            with self.assertRaises(RuntimeError):Guard('meter',None,meter=meter).check()
    def test_generator_quiesce_never_sends_instrument_commands(self):
        controller=MagicMock()
        self.assertEqual(Guard('generator',controller).check(),{'requests':0,'verified':True})
        controller.assert_not_called()
    def test_scope_running_or_busy_blocks(self):
        for running,busy in [('1','0'),('0','1'),('UNKNOWN','0')]:
            @contextmanager
            def scope():yield MagicMock(),{}
            io=types.SimpleNamespace(scope=scope,ask=MagicMock(side_effect=[running,busy]))
            with self.assertRaises(RuntimeError):Guard('scope',None,scope_io=io).check()
            self.assertEqual([c.args[1] for c in io.ask.call_args_list],['ACQUIRE:STATE?','BUSY?'])
    def test_missing_or_invalid_gate_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'gate';g=Guard('meter',None,gate=p);self.assertFalse(g.gated());p.write_text('broken');self.assertTrue(g.gated())
    def test_pending_gate_blocks_requests_before_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'gate';p.write_text('{"components":["supply"]}');g=Guard('supply',None,gate=p)
            app=MagicMock();response=MagicMock();self.assertIn(b'maintenance',b''.join(g.wrap(app)({},response)));app.assert_not_called()
    def test_helper_rejects_commands_urls_paths_and_extra_keys(self):
        for data in ({'schema':1,'action':'shell'},{'schema':1,'action':'update','url':'https://evil'}, {'schema':1,'action':'rollback','path':'/'},[]):
            with self.assertRaises((ValueError,TypeError)):validate(data)

class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(cls.root/'private.pem')],check=True,capture_output=True)
        subprocess.run(['openssl','pkey','-in',str(cls.root/'private.pem'),'-pubout','-out',str(cls.root/'public.pem')],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def sign(self,m):
        raw=canonical(m);(self.root/'manifest').write_bytes(raw)
        subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(self.root/'private.pem'),'-rawin','-in',str(self.root/'manifest'),'-out',str(self.root/'sig')],check=True,capture_output=True)
        return raw,(self.root/'sig').read_bytes()
    def test_real_ed25519_signature_accepts(self):
        raw,sig=self.sign(manifest());self.assertEqual(verify_manifest(raw,sig,self.root/'public.pem')['schema'],1)
    def test_changed_manifest_is_rejected(self):
        raw,sig=self.sign(manifest())
        with self.assertRaisesRegex(MaintenanceError,'signature'):verify_manifest(raw+b' ',sig,self.root/'public.pem')
    def test_changed_signature_is_rejected(self):
        raw,sig=self.sign(manifest())
        with self.assertRaises(MaintenanceError):verify_manifest(raw,b'x'*64,self.root/'public.pem')
    def test_expired_signed_manifest_is_rejected(self):
        m=manifest();m['expires']='2020-01-01T00:00:00+00:00';raw,sig=self.sign(m)
        with self.assertRaises(MaintenanceError):verify_manifest(raw,sig,self.root/'public.pem')
    def test_signed_replay_is_rejected(self):
        raw,sig=self.sign(manifest())
        with self.assertRaises(MaintenanceError):verify_manifest(raw,sig,self.root/'public.pem',minimum=2)
    def test_future_signed_manifest_is_rejected(self):
        m=manifest();m['issued']='2099-01-01T00:00:00+00:00';raw,sig=self.sign(m)
        with self.assertRaises(MaintenanceError):verify_manifest(raw,sig,self.root/'public.pem')
    def test_unknown_component_is_rejected(self):
        m=manifest();m['components']['evil']=m['components']['meter'];raw,sig=self.sign(m)
        with self.assertRaises(MaintenanceError):verify_manifest(raw,sig,self.root/'public.pem')
    def test_untrusted_artifact_origin_is_rejected(self):
        m=manifest();m['components']['meter']['url']='https://evil.example/meter.tar.gz';raw,sig=self.sign(m)
        with self.assertRaises(MaintenanceError):verify_manifest(raw,sig,self.root/'public.pem')
    def test_mutable_and_cleartext_urls_are_rejected(self):
        for url in ['http://github.com/RLF62/instrument-suite/releases/download/v1.0.0/a','https://raw.githubusercontent.com/RLF62/instrument-suite/main/a','https://github.com/RLF62/instrument-suite/releases/latest/download/a','https://x:y@github.com/RLF62/instrument-suite/releases/download/v1.0.0/a']:
            with self.assertRaises(MaintenanceError):github_url(url)
    def test_runtime_and_traversal_paths_are_rejected(self):
        for name in ('../app.py','/etc/passwd','a\\b','a/config.json','secrets.key','.git/config','venv/bin/python','security/a','C:/evil'):
            with self.assertRaises(MaintenanceError):safe_member(name)
    def test_symlink_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.tar.gz'
            with tarfile.open(p,'w:gz') as tar:
                item=tarfile.TarInfo('evil');item.type=tarfile.SYMTYPE;item.linkname='/etc/passwd';tar.addfile(item)
            with self.assertRaises(MaintenanceError):extract(p,Path(tmp)/'out')
    def test_duplicate_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.tar.gz'
            with tarfile.open(p,'w:gz') as tar:
                for _ in range(2):item=tarfile.TarInfo('app.py');item.size=0;tar.addfile(item,io.BytesIO())
            with self.assertRaises(MaintenanceError):extract(p,Path(tmp)/'out')

if __name__=='__main__':unittest.main()
