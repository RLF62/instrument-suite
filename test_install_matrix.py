"""Real file transactions in a temporary root; services and runtimes are inert."""
from contextlib import contextmanager
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import shutil
import tarfile
import unittest

from maintenance.engine import Engine
from maintenance.linux import SPECS
from maintenance.security import MaintenanceError
import test_https_migration
from test_maintenance import manifest


@unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0,
                     'Linux root required for the isolated filesystem fixture')
class InstallMatrixTests(unittest.TestCase):
    @contextmanager
    def isolated_case(self):
        try:
            yield self.fixture()
        finally:
            self.doCleanups()

    def fixture(self):
        f = test_https_migration.HttpsFilesystemTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        (f.root/'etc/udev/rules.d').mkdir(parents=True)
        # Delete only synthetic fixture applications, never a real server path.
        for name in ('supply', 'suite'):
            folder = f.host.folder(name)
            self.assertTrue(folder.resolve().is_relative_to(f.root.resolve()))
            shutil.rmtree(folder)
        f.profile.unlink()
        f.gateway.unlink()
        for name in ('hp6033a', 'fischer-gpib'):
            (f.root/'etc/systemd/system'/ (name+'.service')).unlink()
        f.host.lock_path = f.root/'maintenance.lock'
        f.host.preflight = lambda size: None
        events = []

        @contextmanager
        def inert_leases(affected):
            events.append(('lease', tuple(affected)))
            yield

        def inert_runtimes(stages, job):
            for name in stages:
                runtime = f.root/'opt/test-runtimes'/job.name/name
                (runtime/'bin').mkdir(parents=True)
                (runtime/'bin/python').write_text('# inert runtime; never executed\n')
                f.host.runtimes[name] = runtime

        def file_health(affected, changes):
            for name in set(affected) | set(changes):
                if not (f.root/'etc/systemd/system'/(SPECS[name][1]+'.service')).exists():
                    continue
                self.assertTrue(f.host.folder(name).is_dir())
                self.assertTrue((f.host.folder(name)/'venv/bin/python').is_file())
            events.append(('health', tuple(changes)))

        f.host.quiesce = inert_leases
        f.host.prepare_runtimes = inert_runtimes
        f.host.health = file_health
        downloads = []
        payloads = {}
        m = manifest()
        for name in m['components']:
            files = {'requirements.lock': b'# inert dependency fixture\n'}
            if name == 'suite':
                files.update({'maintenance/__init__.py': b'# inert updater fixture\n',
                              'config.example.json': b'{"hardware_enabled":false}'})
            elif name == 'supply':
                files.update({'app.py': b'# FISCHER_SHARED_ADAPTER_V1\n',
                              'supply_standalone.py': b'# inert supply fixture\n',
                              'config.example.json': b'{"output":false}'})
            elif name == 'meter':
                files['standalone_app.py'] = b'# inert meter fixture\n'
            else:
                files['app.py'] = b'# inert scope fixture\n'
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
                for rel, data in files.items():
                    item = tarfile.TarInfo(rel)
                    item.size = len(data)
                    item.mode = 0o644
                    archive.addfile(item, io.BytesIO(data))
            payloads[name] = buffer.getvalue()
            m['components'][name].update(size=len(payloads[name]),
                sha256=hashlib.sha256(payloads[name]).hexdigest())

        def fetch(url, destination, expected=None, size=None):
            name = url.rsplit('/', 1)[-1].split('.')[0]
            data = payloads[name]
            if hashlib.sha256(data).hexdigest() != expected or len(data) != size:
                raise MaintenanceError('Fixture integrity check failed')
            downloads.append(name)
            Path(destination).write_bytes(data)
            return Path(destination)

        engine = Engine(f.root/'state', f.host, fetch=fetch)
        return f, engine, m, events, downloads

    def test_all_seven_fresh_controller_selections_use_real_file_activation(self):
        names = ('meter', 'supply', 'scope')
        for count in (1, 2, 3):
            for selected in itertools.combinations(names, count):
                with self.subTest(selected=selected), self.isolated_case() as case:
                    f, engine, m, events, downloads = case
                    result = engine.apply(m, list(selected))
                    expected = {'suite', *selected}
                    self.assertEqual(set(engine.state()['components']), expected)
                    self.assertEqual(f.host.discover(), expected)
                    self.assertEqual(set(downloads), expected)
                    self.assertEqual(result['result'], 'Updated and health checked')
                    registry = json.loads((f.host.folder('suite')/'registry.json').read_text())
                    self.assertEqual(set(registry['instruments']), set(selected))
                    self.assertFalse(engine.pending.exists())
                    self.assertFalse(engine.flag.exists())
                    before = list(f.commands)
                    engine.apply(m, list(selected))
                    self.assertEqual(f.commands, before)
                    self.assertEqual(len(downloads), len(expected))
                    if 'supply' in selected:
                        self.assertFalse(json.loads((f.host.folder('supply')/'config.json').read_text())['output'])
                    if 'scope' in selected:
                        self.assertEqual(json.loads((f.host.folder('scope')/'connection.json').read_text())['address'],
                                         'scope-not-configured.invalid')

    def test_add_scope_and_rollback_preserve_meter_files_and_private_settings(self):
        f, engine, m, events, downloads = self.fixture()
        engine.apply(m, ['meter'])
        meter = f.host.folder('meter')
        (meter/'presets.json').write_text('{"private":"retained"}')
        before = {str(p.relative_to(meter)): p.read_bytes() for p in meter.rglob('*') if p.is_file()}
        commands_at = len(f.commands)
        engine.apply(m, ['meter', 'scope'])
        self.assertEqual(downloads, ['meter', 'suite', 'scope'])
        self.assertEqual(events[-2:], [('lease', ()), ('health', ('scope',))])
        self.assertFalse(any('hp34401a' in cmd for cmd in f.commands[commands_at:]))
        backup = Path(json.loads((engine.root/'last-backup.json').read_text())['path'])
        self.assertEqual(f.host.verify_backup(backup)['changes'], ['scope'])
        engine.rollback()
        self.assertFalse(f.host.folder('scope').exists())
        self.assertEqual(set(engine.state()['components']), {'suite', 'meter'})
        after = {str(p.relative_to(meter)): p.read_bytes() for p in meter.rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        self.assertFalse(engine.pending.exists())

    def test_failed_add_restores_existing_installation_and_registry(self):
        f, engine, m, events, downloads = self.fixture()
        engine.apply(m, ['meter'])
        registry = f.host.folder('suite')/'registry.json'
        before = registry.read_bytes()
        original = f.host.health

        def fail_once(affected, changes):
            if changes == ['scope']:
                raise MaintenanceError('Synthetic activation health failure')
            return original(affected, changes)

        f.host.health = fail_once
        with self.assertRaisesRegex(MaintenanceError, 'previous software restored and health checked'):
            engine.apply(m, ['meter', 'scope'])
        self.assertEqual(registry.read_bytes(), before)
        self.assertFalse(f.host.folder('scope').exists())
        self.assertFalse(engine.pending.exists())
        self.assertFalse(engine.flag.exists())
