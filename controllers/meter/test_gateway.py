import unittest,tempfile,json,base64
from pathlib import Path
from unittest.mock import patch,MagicMock
import bcrypt
import suite_gateway as gateway
import deployment_profile as profile

class GatewayTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  (self.root/'hp6033a').mkdir()
  self.security=self.root/'security';self.security.mkdir()
  (self.security/'.control_auth_mode').write_text('password-free')
  (self.security/'.control_htpasswd').write_text('user:'+bcrypt.hashpw(b'test-only-password',bcrypt.gensalt(rounds=4)).decode())
  self.a=patch.object(gateway,'HOME',self.root);self.b=patch.object(gateway,'SECURITY',self.security)
  self.a.start();self.b.start();self.client=gateway.app.test_client()
 def tearDown(self):self.a.stop();self.b.stop();self.tmp.cleanup()
 def headers(self,origin='https://bench',auth=False):
  result={'Origin':origin}
  if auth:result['Authorization']='Basic '+base64.b64encode(b'user:test-only-password').decode()
  return result
 def test_wrong_origin_blocks_before_proxy_or_manager(self):
  with patch.object(gateway,'forward') as f:
   r=self.client.post('/api/control/meter/sample',base_url='https://bench',json={},headers=self.headers('https://wrong'))
   self.assertEqual(r.status_code,403);f.assert_not_called()
 def test_password_free_control_retains_origin_guard(self):
  with patch.object(gateway,'forward',return_value=gateway.jsonify if False else ('ok',200)) as f:
   r=self.client.post('/api/control/meter/pause',base_url='https://bench',json={},headers=self.headers())
   self.assertEqual(r.status_code,200);self.assertEqual(f.call_args.args[0],'meter')
 def test_protected_control_requires_credentials(self):
  (self.security/'.control_auth_mode').write_text('protected')
  with patch.object(gateway,'forward') as f:
   r=self.client.post('/api/control/meter/sample',base_url='https://bench',json={},headers=self.headers())
   self.assertEqual(r.status_code,401);f.assert_not_called()
 def test_credentials_survive_supply_removal(self):
  (self.security/'.control_auth_mode').write_text('protected')
  with patch.object(gateway,'forward',return_value=('ok',200)):
   r=self.client.post('/api/control/meter/pause',base_url='https://bench',json={},headers=self.headers(auth=True))
   self.assertEqual(r.status_code,200)
 def test_invalid_credentials_fail_closed(self):
  (self.security/'.control_auth_mode').write_text('protected')
  with patch.object(gateway,'forward') as f:
   h=self.headers();h['Authorization']='Basic '+base64.b64encode(b'user:wrong').decode()
   r=self.client.post('/api/control/meter/sample',base_url='https://bench',json={},headers=h)
   self.assertEqual(r.status_code,401);f.assert_not_called()
 def test_live_auth_mode_takes_precedence(self):
  (self.root/'hp6033a/.control_auth_mode').write_text('protected')
  with gateway.app.test_request_context('/'):self.assertTrue(gateway.password_required())
 def test_missing_auth_files_require_password(self):
  (self.security/'.control_auth_mode').unlink()
  with gateway.app.test_request_context('/'):self.assertTrue(gateway.password_required())
 def test_backend_mapping(self):
  for p in ['multimeter/classic','multimeter/assets/meter.js','api/multimeter/status','api/control/meter/pause']:
   self.assertEqual(gateway.target_for(p),'meter')
  self.assertEqual(gateway.target_for('api/status'),'supply')
 def test_removed_supply_leaves_menu_page(self):
  with patch.object(gateway.urllib.request,'urlopen',side_effect=OSError('not running')):
   r=self.client.get('/',base_url='https://bench')
   self.assertEqual(r.status_code,200);self.assertIn(b'Manage instruments',r.data)
 def test_removed_meter_is_unavailable_without_affecting_gateway(self):
  with patch.object(gateway.urllib.request,'urlopen',side_effect=OSError('not running')):
   self.assertEqual(self.client.get('/multimeter/classic',base_url='https://bench').status_code,503)
 def test_proxy_preserves_secure_host_and_query(self):
  upstream=MagicMock();upstream.__enter__.return_value=upstream;upstream.status=200;upstream.read.return_value=b'{}';upstream.headers={}
  with patch.object(gateway.urllib.request,'urlopen',return_value=upstream) as open_url:
   self.client.get('/api/multimeter/status?x=1',base_url='https://bench')
   req=open_url.call_args.args[0];self.assertEqual(req.full_url,'http://127.0.0.1:8082/api/multimeter/status?x=1')
   self.assertEqual(req.get_header('Host'),'bench');self.assertEqual(req.get_header('X-forwarded-proto'),'https')
 def test_gateway_has_no_controller_import_or_hardware_entrypoint(self):
  t=Path(gateway.__file__).read_text();self.assertNotIn('from gpib_client',t);self.assertNotIn('import app as controller',t)

class ProfileTests(unittest.TestCase):
 def test_loopback_only_for_proxied_instruments(self):
  with patch.object(profile,'secure_gateway',return_value=True):
   self.assertEqual(profile.bind_host('meter'),'127.0.0.1');self.assertEqual(profile.bind_host('supply'),'127.0.0.1')
   self.assertEqual(profile.bind_host('scope'),'0.0.0.0')
 def test_public_menu_retains_https_paths(self):
  with patch.object(profile,'secure_gateway',return_value=True):
   r=profile.public_records({'meter':{'port':8082,'scheme':'http'},'supply':{'port':8083,'scheme':'http'},'scope':{'port':8081,'scheme':'http'}})
   self.assertEqual(r['meter']['scheme'],'https');self.assertIsNone(r['meter']['port']);self.assertEqual(r['scope']['port'],8081)
 def test_profile_defaults_do_not_change_standard_installations(self):
  with patch.object(profile,'secure_gateway',return_value=False):
   self.assertEqual(profile.bind_host('meter'),'0.0.0.0')
 def test_meter_app_gets_proxy_fix_once(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(profile,'secure_gateway',return_value=True):
   p=Path(folder);(p/'standalone_app.py').write_text('app=None\n')
   profile.configure_app('meter',p);once=(p/'standalone_app.py').read_text();profile.configure_app('meter',p)
   self.assertEqual((p/'standalone_app.py').read_text(),once)
if __name__=='__main__':unittest.main()
