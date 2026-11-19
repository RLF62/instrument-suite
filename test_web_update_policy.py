"""No live services or credentials: web maintenance authorization regression."""
import base64
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch,MagicMock
from flask import Flask
from maintenance import web_policy as policy
from maintenance.web_updates import install
from maintenance.linux import LinuxHost
from maintenance import cli
from maintenance import helper as root_helper

def lan():
    value=policy.disabled();value.update(mode='trusted-lan',origins=['http://bench:8080'],trusted_lans=['192.168.1.0/24'],trusted_proxies=['127.0.0.1/32']);return policy.validate(value)

class PolicyTests(unittest.TestCase):
    def test_fresh_lan_origin_selects_only_a_trusted_ipv4_address(self):
        self.assertEqual(policy.fresh_lan_origin(['192.168.1.0/24'],
                         ['fdca::1','192.168.2.9','192.168.1.178']),
                         'http://192.168.1.178:8080')
        with self.assertRaisesRegex(Exception,'--update-origin'):
            policy.fresh_lan_origin(['192.168.1.0/24'],['192.168.2.9'])

    def test_real_unix_socket_accepts_pathlib_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'helper.sock'
            with root_helper.bind_socket(path) as server:self.assertEqual(server.getsockname(),str(path))
    def test_no_policy_defaults_to_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:self.assertEqual(policy.read_policy(Path(tmp)/'absent')['mode'],'disabled')
    def test_password_free_requires_explicit_cidr(self):
        value=lan();value['trusted_lans']=[]
        with self.assertRaises(Exception):policy.validate(value)
    def test_public_and_default_route_ranges_are_rejected(self):
        for cidr in ('0.0.0.0/0','8.8.8.0/24','::/0','192.168.1.10/24'):
            value=lan();value['trusted_lans']=[cidr]
            with self.assertRaises(Exception):policy.validate(value)
    def test_https_requires_existing_dashboard_mode(self):
        value=lan();value['origins']=['https://bench']
        with self.assertRaises(Exception):policy.validate(value)
    def test_dashboard_mode_rejects_new_or_arbitrary_password_store(self):
        value=lan();value.update(mode='dashboard',origins=['https://bench'],credential_file='/tmp/new-update-password')
        with self.assertRaises(Exception):policy.validate(value)
    def test_only_local_trusted_proxies_accepted(self):
        value=lan();value['trusted_proxies']=['192.168.1.0/24']
        with self.assertRaises(Exception):policy.validate(value)
    def test_existing_policy_is_preserved_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'policy';path.write_text('existing-authenticated-settings')
            with patch.object(policy.os,'geteuid',return_value=0),patch.object(policy,'read_policy',return_value={'mode':'dashboard'}):
                result=policy.configure('trusted-lan',['http://bench'],['192.168.1.0/24'],path=path)
            self.assertTrue(result['preserved_existing_policy']);self.assertEqual(path.read_text(),'existing-authenticated-settings')
    def test_short_existing_dashboard_password_is_reused(self):
        import bcrypt
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'dashboard';p.write_text('rick:'+bcrypt.hashpw(b'short',bcrypt.gensalt(rounds=4)).decode())
            before=p.read_bytes();self.assertTrue(policy.verify_dashboard('rick','short',p));self.assertFalse(policy.verify_dashboard('rick','wrong',p));self.assertEqual(before,p.read_bytes())
    def test_csrf_requires_matching_random_token(self):
        self.assertTrue(policy.csrf_valid('a'*64,'a'*64))
        for cookie,header in [(None,None),('a'*64,None),('a'*64,'b'*64),('short','short')]:self.assertFalse(policy.csrf_valid(cookie,header))
    def test_terminal_update_does_not_use_web_policy(self):
        with patch.object(cli,'config',return_value={'key':'pinned-key'}),patch.object(cli,'latest_url',return_value='https://approved'),patch.object(cli,'Engine') as engine,patch.object(cli.os,'geteuid',return_value=0),patch.object(policy,'read_policy',side_effect=AssertionError('Terminal must not request web auth')):
            engine.return_value.release.return_value={'release':'v1.0.0'};engine.return_value.describe.return_value={'installed':{},'changes':[]};engine.return_value.apply.return_value={'ok':True}
            self.assertEqual(cli.execute('update'),{'ok':True})
    def test_configuration_dry_run_never_writes_or_enables_helper(self):
        with patch.object(policy,'configure') as configure,patch.object(policy,'install_helper') as helper:
            result=cli.main(['configure-web-updates','--mode','trusted-lan','--trusted-lan','192.168.1.0/24','--origin','http://bench:8080','--dry-run'])
            self.assertEqual(result,0);configure.assert_not_called();helper.assert_not_called()

class WebTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);install(self.app);self.client=self.app.test_client();self.value=lan()
        self.a=patch('maintenance.web_updates.read_policy',side_effect=lambda:self.value);self.a.start()
        self.b=patch('maintenance.web_updates.helper',return_value={'job':None});self.helper=self.b.start()
    def tearDown(self):self.a.stop();self.b.stop()
    def get(self,ip='192.168.1.22',headers=None):
        return self.client.get('/api/software-updates',base_url='http://bench:8080',environ_overrides={'REMOTE_ADDR':ip},headers=headers or {})
    def post(self,token,origin='http://bench:8080',ip='192.168.1.22',payload=None):
        headers={'X-CSRF-Token':token}
        if origin is not None:headers['Origin']=origin
        return self.client.post('/api/software-updates',base_url='http://bench:8080',environ_overrides={'REMOTE_ADDR':ip},headers=headers,json=payload or {'action':'update'})
    def test_trusted_lan_get_requires_no_password(self):
        r=self.get();self.assertEqual(r.status_code,200);self.assertEqual(r.json['mode'],'trusted-lan');self.assertEqual(len(r.json['csrf']),64)
    def test_trusted_lan_post_with_csrf_is_allowed_without_password(self):
        token=self.get().json['csrf'];self.assertEqual(self.post(token).status_code,202);self.helper.assert_called_with('update')
    def test_outside_lan_is_blocked(self):self.assertEqual(self.get('203.0.113.5').status_code,403)
    def test_untrusted_forwarded_ip_is_ignored(self):self.assertEqual(self.get('203.0.113.5',{'X-Real-IP':'192.168.1.22','X-Forwarded-Proto':'http'}).status_code,403)
    def test_sanitized_local_proxy_is_accepted(self):self.assertEqual(self.get('127.0.0.1',{'X-Real-IP':'192.168.1.22','X-Forwarded-Proto':'http'}).status_code,200)
    def test_proxy_missing_client_ip_is_blocked(self):self.assertEqual(self.get('127.0.0.1').status_code,403)
    def test_proxy_spoofed_chain_is_blocked(self):self.assertEqual(self.get('127.0.0.1',{'X-Real-IP':'192.168.1.22,8.8.8.8','X-Forwarded-Proto':'http'}).status_code,403)
    def test_wrong_origin_is_blocked(self):
        token=self.get().json['csrf'];self.assertEqual(self.post(token,'http://evil.example').status_code,403)
    def test_missing_origin_is_blocked(self):
        token=self.get().json['csrf'];self.assertEqual(self.post(token,None).status_code,403)
    def test_missing_csrf_is_blocked(self):self.assertEqual(self.post('').status_code,403)
    def test_wrong_csrf_is_blocked(self):
        self.get();self.assertEqual(self.post('f'*64).status_code,403)
    def test_cross_site_fetch_metadata_is_blocked(self):self.assertEqual(self.get(headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
    def test_arbitrary_helper_arguments_are_rejected(self):
        token=self.get().json['csrf'];self.assertEqual(self.post(token,payload={'action':'update','command':'whoami'}).status_code,400)
    def test_disabled_mode_blocks_access(self):
        self.value=policy.disabled();self.assertEqual(self.get().status_code,403)
    def test_https_uses_same_dashboard_credentials(self):
        self.value.update(mode='dashboard',origins=['https://bench'],credential_file='/home/pi/hp6033a/.control_htpasswd')
        headers={'Authorization':'Basic '+base64.b64encode(b'rick:short').decode()}
        with patch.object(policy,'verify_dashboard',return_value=True) as verify:
            r=self.client.get('/api/software-updates',base_url='https://bench',environ_overrides={'REMOTE_ADDR':'192.168.1.22'},headers=headers)
            self.assertEqual(r.status_code,200);verify.assert_called_once_with('rick','short','/home/pi/hp6033a/.control_htpasswd')
    def test_https_missing_dashboard_login_is_denied(self):
        self.value.update(mode='dashboard',origins=['https://bench'],credential_file='/home/pi/hp6033a/.control_htpasswd')
        self.assertEqual(self.client.get('/api/software-updates',base_url='https://bench',environ_overrides={'REMOTE_ADDR':'192.168.1.22'}).status_code,401)

class RestartScopeTests(unittest.TestCase):
    def check_scope(self,path):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'home';source=Path(tmp)/'source';source.mkdir();target=home/'instrument-suite';target.mkdir(parents=True)
            p=source/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('new')
            previous=target/path;previous.parent.mkdir(parents=True,exist_ok=True);previous.write_text('old')
            host=LinuxHost(Path(tmp)/'state',home)
            return host.refine_affected({'suite':source},['suite','meter','supply','scope']),host.restart_broker
    def test_web_only_change_does_not_restart_instruments(self):self.assertEqual(self.check_scope('maintenance/web_policy.py'),(['suite'],False))
    def test_guard_change_retains_all_safety_interlocks(self):self.assertEqual(self.check_scope('maintenance/guard.py'),(['suite','meter','supply','scope'],True))
    def test_broker_change_retains_all_safety_interlocks(self):self.assertEqual(self.check_scope('adapter_broker.py'),(['suite','meter','supply','scope'],True))
    def test_dependency_change_retains_all_safety_interlocks(self):self.assertEqual(self.check_scope('requirements.lock'),(['suite','meter','supply','scope'],True))
    def test_dashboard_only_rollback_does_not_restart_broker(self):
        with tempfile.TemporaryDirectory() as tmp:
            host=LinuxHost(Path(tmp)/'state',Path(tmp)/'home');host.set_recovery_scope({'affected':['suite'],'restart_broker':False});self.assertFalse(host.restart_broker)

if __name__=='__main__':unittest.main()
