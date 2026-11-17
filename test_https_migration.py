"""Isolated Linux migration and real loopback TLS tests; no instrument access."""
from contextlib import ExitStack
import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import ssl
import subprocess
import tarfile
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from maintenance import linux, web_policy, web_updates, cli
from maintenance.security import MaintenanceError


@unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0,
                     'Run the filesystem fixtures as root in their isolated temporary tree')
class HttpsFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fischer-https-fixture-')
        self.root = Path(self.tmp.name)
        for name in ['etc/nginx/sites-available', 'etc/nginx/sites-enabled',
                     'etc/systemd/system', 'etc/fischer-suite', 'etc/ssl/private',
                     'etc/letsencrypt/archive/fixture', 'opt', 'home/pi', 'state']:
            (self.root/name).mkdir(parents=True, exist_ok=True)
        self.stack = ExitStack()
        def rooted(*args):
            p = Path(*args)
            if p.is_absolute() and p.parts[1] in ('etc', 'opt', 'run'):
                return self.root/str(p).lstrip('/')
            return p
        self.stack.enter_context(patch.object(linux, 'Path', rooted))
        self.stack.enter_context(patch.object(linux, 'SYSTEM', tuple(rooted(p) for p in linux.SYSTEM)))
        self.stack.enter_context(patch.object(linux.subprocess, 'run', return_value=SimpleNamespace(returncode=0)))
        self.host = linux.LinuxHost(self.root/'state', self.root/'home/pi')
        self.commands = []
        self.host.run = lambda args, **kw: self.commands.append(list(map(str, args))) or ''
        self.profile = self.root/'etc/fischer-suite/profile.json'
        self.profile.write_text('{"schema":1,"https_gateway":true}')
        self.profile.chmod(0o644)
        self.gateway = self.root/'etc/systemd/system/fischer-suite-web.service'
        self.gateway.write_text('existing gateway service; fixed Unix socket')
        (self.root/'etc/systemd/system/fischer-gpib.service').write_text('existing broker')
        supply = self.host.folder('supply'); supply.mkdir()
        self.host.folder('suite').mkdir()
        for name, text in {
            'app.py': '# previous application\n',
            'supply_standalone.py': '# existing HTTPS/authentication wrapper\n',
            'config.json': '{"output":false,"voltage":0,"current":1}',
            'presets.json': '{"bench":[1,2,3]}',
            '.control_auth_mode': 'protected',
            '.control_htpasswd': 'fixture:existing-private-hash',
        }.items(): (supply/name).write_text(text)
        (self.root/'etc/systemd/system/hp6033a.service').write_text(
            'ExecStart=/existing/gunicorn --bind 127.0.0.1:8083 maintenance_entry:app\n')
        (self.root/'etc/nginx/sites-available/existing').write_text(
            'server { listen 443 ssl; ssl_certificate /etc/ssl/fixture.crt; }\n')
        (self.root/'etc/ssl/private/fixture.key').write_text('private TLS fixture; not a real key')
        (self.root/'etc/letsencrypt/archive/fixture/fixture.pem').write_text('private certificate fixture')
        self.source = self.root/'source'; self.source.mkdir()
        (self.source/'app.py').write_text('# new application\n')
        (self.source/'supply_standalone.py').write_text('# fresh HTTP wrapper must not replace HTTPS\n')
        (self.source/'maintenance').mkdir()
        (self.source/'maintenance/__init__.py').write_text('# inert engine fixture\n')
        self.job = self.root/'state/transaction'; self.job.mkdir()

    def tearDown(self):
        self.stack.close(); self.tmp.cleanup()

    def protected(self):
        paths = [self.profile, self.gateway,
                 self.root/'etc/nginx/sites-available/existing',
                 self.root/'etc/ssl/private/fixture.key',
                 self.root/'etc/letsencrypt/archive/fixture/fixture.pem']
        paths += [self.host.folder('supply')/n for n in
                  ['config.json','presets.json','.control_auth_mode','.control_htpasswd','supply_standalone.py']]
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    def backup(self, name='supply'):
        return self.host.backup(self.job, [name], {name:self.source}, {'schema':1,'components':{}})

    def test_https_activation_and_rollback_preserve_auth_tls_settings_and_units(self):
        before = self.protected(); unit = self.root/'etc/systemd/system/hp6033a.service'
        original_unit = unit.read_bytes()
        backup = self.backup()
        self.host.activate({'supply':self.source}, self.job)
        self.assertEqual((self.host.folder('supply')/'app.py').read_text(), '# new application\n')
        self.assertEqual(self.protected(), before)
        self.assertEqual(unit.read_bytes(), original_unit)
        # Exercise the actual file restore path used after failed activation.
        self.host.restore(backup)
        self.assertEqual((self.host.folder('supply')/'app.py').read_text(), '# previous application\n')
        self.assertEqual(self.protected(), before)
        self.assertEqual(unit.read_bytes(), original_unit)
        self.assertFalse(any('fischer-gpib' in command for command in self.commands))

    def test_rollback_keeps_latest_private_presets(self):
        backup = self.backup(); self.host.activate({'supply':self.source}, self.job)
        presets = self.host.folder('supply')/'presets.json'
        presets.write_text('{"newer_user_preset":[5,6]}')
        self.host.restore(backup)
        self.assertEqual(json.loads(presets.read_text()), {'newer_user_preset':[5,6]})

    def test_backup_includes_standard_tls_locations_and_rejects_corruption(self):
        backup = self.backup()
        with tarfile.open(backup/'private-system.tar.gz') as archive:
            names = archive.getnames()
        self.assertTrue(any(n.endswith('etc/ssl/private/fixture.key') for n in names))
        self.assertTrue(any(n.endswith('etc/letsencrypt/archive/fixture/fixture.pem') for n in names))
        archive = backup/'private-system.tar.gz'; archive.write_bytes(archive.read_bytes()+b'corruption')
        with self.assertRaisesRegex(MaintenanceError, 'integrity'): self.host.verify_backup(backup)

    def test_https_suite_setup_does_not_add_http_listener_or_reload_nginx(self):
        before = self.protected(); backup = self.backup()
        meta = json.loads((backup/'backup.json').read_text())
        self.host.shared_setup(self.source, self.job, meta)
        self.assertFalse((self.root/'etc/nginx/sites-available/fischer-suite-dashboard').exists())
        self.assertEqual(self.protected(), before)
        self.assertFalse(self.commands)
        self.assertTrue((self.root/'opt/fischer-suite-updater/current').is_symlink())

    def test_fresh_http_setup_retains_original_listener_and_sanitized_proxy_headers(self):
        self.profile.unlink(); self.gateway.unlink(); backup = self.backup()
        self.host.shared_setup(self.source, self.job, json.loads((backup/'backup.json').read_text()))
        site = (self.root/'etc/nginx/sites-available/fischer-suite-dashboard').read_text()
        self.assertIn('listen 8080', site)
        self.assertIn('X-Real-IP $remote_addr', site)
        self.assertIn('X-Forwarded-Proto $scheme', site)

    def test_new_controller_on_https_gateway_is_loopback_only(self):
        (self.source/'standalone_app.py').write_text('# inert meter fixture\n')
        self.backup('meter'); self.host.activate({'meter':self.source}, self.job)
        unit = (self.root/'etc/systemd/system/hp34401a.service').read_text()
        self.assertIn('--bind 127.0.0.1:8082', unit)
        self.assertNotIn('0.0.0.0', unit)

    def test_missing_policy_on_existing_gateway_blocks_before_file_changes(self):
        self.profile.unlink()
        with self.assertRaisesRegex(MaintenanceError, 'protected deployment policy'):
            self.host.activate({'supply':self.source}, self.job)
        self.assertEqual((self.host.folder('supply')/'app.py').read_text(), '# previous application\n')
        self.assertFalse(self.commands)

    def test_unsafe_unknown_and_symlink_policies_fail_closed(self):
        self.profile.chmod(0o666)
        with self.assertRaisesRegex(MaintenanceError, 'protected'): self.host.https_gateway()
        self.profile.chmod(0o644); self.profile.write_text('{"schema":1,"https_gateway":false}')
        with self.assertRaisesRegex(MaintenanceError, 'Unrecognized'): self.host.https_gateway()
        self.profile.unlink(); self.profile.symlink_to(self.root/'missing-profile')
        with self.assertRaises(MaintenanceError): self.host.https_gateway()

    def test_audit_reports_unenrolled_software_without_changing_credentials_or_services(self):
        before = self.protected()
        result = self.host.audit({'schema':1,'components':{}}, recovery_pending=True)
        self.assertFalse(result['changes_performed'])
        self.assertEqual(result['deployment'], 'https-gateway')
        self.assertIn('supply', result['requires_attended_enrollment'])
        self.assertTrue(any('unversioned' in s for s in result['blocking_reasons']))
        self.assertTrue(result['recovery_pending'])
        self.assertEqual(self.protected(), before)
        self.assertFalse(self.commands)


class RealTlsAuthorizationTests(unittest.TestCase):
    """Exercise HTTPS, browser cookie and CSRF behavior without a privileged helper."""
    def setUp(self):
        import bcrypt
        from flask import Flask
        from werkzeug.serving import make_server, WSGIRequestHandler
        self.tmp = tempfile.TemporaryDirectory(prefix='fischer-tls-fixture-')
        self.root = Path(self.tmp.name)
        self.creds = self.root/'dashboard.htpasswd'
        self.creds.write_text('fixture:'+bcrypt.hashpw(b'bench7', bcrypt.gensalt(rounds=4)).decode()+'\n')
        self.before = self.creds.read_bytes()
        cert, key = self.root/'cert.pem', self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1',
                        '-keyout',str(key),'-out',str(cert)], check=True, capture_output=True)
        self.policy = web_policy.disabled()
        self.policy.update(mode='dashboard', credential_file=str(self.creds))
        self.calls = []
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(web_policy, 'CREDENTIAL_FILES', {str(self.creds)}))
        self.stack.enter_context(patch.object(web_updates, 'read_policy', side_effect=lambda:web_policy.validate(self.policy)))
        self.stack.enter_context(patch.object(web_updates, 'helper', side_effect=lambda a:self.calls.append(a) or {'action':a}))
        app = Flask(__name__); web_updates.install(app)
        class QuietHandler(WSGIRequestHandler):
            def log(self, *args, **kwargs): pass
        self.server = make_server('127.0.0.1', 0, app, threaded=True,
                                  ssl_context=(str(cert),str(key)), request_handler=QuietHandler)
        self.origin = 'https://127.0.0.1:'+str(self.server.server_port)
        self.policy['origins'] = [self.origin]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))),
            urllib.request.HTTPCookieProcessor(self.cookies))

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.stack.close()
        self.assertEqual(self.creds.read_bytes(), self.before)
        self.tmp.cleanup()

    def request(self, action=None, password='bench7', origin=None, csrf=None, extra=None):
        headers = {'Authorization':'Basic '+base64.b64encode(('fixture:'+password).encode()).decode()}
        if action is not None:
            headers.update({'Content-Type':'application/json','Origin':origin or self.origin})
        if csrf is not None: headers['X-CSRF-Token'] = csrf
        if extra: headers.update(extra)
        req = urllib.request.Request(self.origin+'/api/software-updates',
            data=None if action is None else json.dumps({'action':action}).encode(), headers=headers)
        try: return self.opener.open(req, timeout=5)
        except urllib.error.HTTPError as error: return error

    def test_existing_short_dashboard_password_and_secure_cookie_work_over_real_https(self):
        with self.request() as response:
            self.assertEqual(response.status, 200); token = json.load(response)['csrf']
            cookie = response.headers.get('Set-Cookie')
            for flag in ['Secure','HttpOnly','SameSite=Strict']: self.assertIn(flag, cookie)
        with self.request('check', csrf=token) as response: self.assertEqual(response.status, 202)
        self.assertEqual(self.calls, ['status','check'])

    def test_wrong_password_wrong_origin_and_missing_csrf_never_reach_helper(self):
        with self.request(password='wrong') as response: self.assertEqual(response.status, 401)
        self.assertEqual(self.calls, [])
        with self.request() as response: token = json.load(response)['csrf']
        self.calls.clear()
        with self.request('update', origin='https://other.invalid', csrf=token) as response:
            self.assertEqual(response.status, 403)
        with self.request('update') as response: self.assertEqual(response.status, 403)
        self.assertEqual(self.calls, [])

    def test_changed_dashboard_credentials_are_reused_without_a_second_password_store(self):
        import bcrypt
        self.creds.write_text('fixture:'+bcrypt.hashpw(b'newpass', bcrypt.gensalt(rounds=4)).decode()+'\n')
        self.before = self.creds.read_bytes()
        with self.request(password='bench7') as response: self.assertEqual(response.status, 401)
        with self.request(password='newpass') as response: self.assertEqual(response.status, 200)


class AuditCliTests(unittest.TestCase):
    def test_audit_needs_no_release_download_or_new_credentials(self):
        from unittest.mock import MagicMock
        host = MagicMock(); engine = MagicMock()
        engine.state.return_value = {'schema':1,'components':{}}
        engine.pending.exists.return_value = False
        host.audit.return_value = {'changes_performed':False}
        with patch.object(cli, 'LinuxHost', return_value=host), patch.object(cli, 'Engine', return_value=engine), \
             patch.object(cli, 'latest_url') as discovery, patch.object(cli, 'config') as config:
            self.assertEqual(cli.execute('audit'), {'changes_performed':False})
        discovery.assert_not_called(); config.assert_not_called(); engine.apply.assert_not_called()
        host.audit.assert_called_once_with({'schema':1,'components':{}}, False)


if __name__ == '__main__': unittest.main()
