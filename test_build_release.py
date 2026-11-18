"""Real Git/OpenSSL release builds in isolated fixtures; no controller imports."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools import build_release as release
from maintenance.security import verify_manifest, extract, MaintenanceError

class ReleaseBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='release-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.sources={}
        for name,repo in release.REPOS.items():
            source=self.root/name;source.mkdir();self.sources[name]=source
            self.command('git','init','-q',str(source))
            self.command('git','-C',str(source),'remote','add','origin','https://github.com/RLF62/'+repo+'.git')
            if name=='suite':
                (source/'patch_hp.py').write_text('from pathlib import Path\nimport sys\np=Path(sys.argv[1]);p.write_text(p.read_text()+"\\n# FISCHER_SHARED_ADAPTER_V1\\n")\n')
                templates=source/'integration/templates';templates.mkdir(parents=True)
                (source/'hp33120a').mkdir();(source/'hp33120a/protocol.py').write_text('# suite development copy')
                (source/'integration/supply_standalone.py').write_text('# inert fixture entry wrapper\n')
                (templates/'index.html').write_text('reviewed modern chart')
                (templates/'classic_dual_preview.html').write_text('reviewed classic mobile proportions')
            elif name=='supply':
                (source/'app.py').write_text('# inert supply fixture\n')
                (source/'templates').mkdir()
                (source/'templates/index.html').write_text('old view')
            elif name=='meter':(source/'standalone_app.py').write_text('# inert meter fixture\n')
            elif name=='generator':
                (source/'generator_app.py').write_text('# inert generator fixture\n')
                (source/'hp33120a').mkdir()
            else:(source/'app.py').write_text('# inert scope fixture\n')
            self.commit(source)
        self.locks=self.root/'locks';self.locks.mkdir()
        self.lock=b'fixture==1.0.0 --hash=sha256:'+b'a'*64+b'\n'
        for name in release.REPOS:(self.locks/(name+'.lock')).write_bytes(self.lock)
        self.key=self.root/'test-signing.key';self.public=self.root/'test-signing.pub'
        self.command('openssl','genpkey','-algorithm','ED25519','-out',str(self.key))
        self.command('openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.public))
        self.versions={n:'v1.0.0' for n in release.REPOS}
        self.output=self.root/'output'

    def command(self,*args):
        return subprocess.run(args,check=True,capture_output=True).stdout

    def commit(self,source):
        self.command('git','-C',str(source),'add','.')
        self.command('git','-C',str(source),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')

    def build(self,**overrides):
        args=dict(sources=self.sources,locks=self.locks,versions=self.versions,release='v1.0.0',
                  sequence=1,key=self.key,public_key=self.public,output=self.output)
        args.update(overrides)
        return release.build(**args)

    def test_signed_build_tracks_real_commits_locks_and_preserved_ui(self):
        # Input mapping order must not affect suite-before-supply staging.
        sources=dict(reversed(list(self.sources.items())))
        result=self.build(sources=sources)
        checked=verify_manifest((self.output/'manifest.json').read_bytes(),
                                (self.output/'manifest.json.sig').read_bytes(),self.public)
        self.assertEqual(result,checked)
        for name,source in self.sources.items():
            item=result['components'][name];archive=self.output/(name+'.tar.gz')
            self.assertEqual(item['commit'],self.command('git','-C',str(source),'rev-parse','HEAD').decode().strip())
            self.assertEqual(item['sha256'],hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(result['build_inputs'][name]['dependency_lock_sha256'],hashlib.sha256(self.lock).hexdigest())
        suite_payload=extract(self.output/'suite.tar.gz',self.root/'suite-extracted')
        self.assertFalse((suite_payload/'hp33120a').exists())
        payload=extract(self.output/'supply.tar.gz',self.root/'extracted')
        self.assertEqual((payload/'templates/index.html').read_text(),'reviewed modern chart')
        self.assertEqual((payload/'templates/classic_dual_preview.html').read_text(),'reviewed classic mobile proportions')
        self.assertTrue((payload/'supply_standalone.py').is_file())
        self.assertIn('FISCHER_SHARED_ADAPTER_V1',(payload/'app.py').read_text())
        self.assertEqual(result['build_inputs']['supply']['suite_overlay_commit'],result['components']['suite']['commit'])

    def test_dirty_or_untracked_sources_are_rejected_without_output(self):
        for filename in ('app.py','untracked.txt'):
            with self.subTest(filename=filename):
                path=self.sources['scope']/filename
                previous=path.read_bytes() if path.exists() else None
                path.write_text('changed')
                with self.assertRaisesRegex(MaintenanceError,'clean'):self.build()
                self.assertFalse(self.output.exists())
                if previous is None:path.unlink()
                else:path.write_bytes(previous)

    def test_wrong_repository_identity_is_rejected(self):
        self.command('git','-C',str(self.sources['meter']),'remote','set-url','origin','https://github.com/other/project.git')
        with self.assertRaisesRegex(MaintenanceError,'repository'):self.build()
        self.assertFalse(self.output.exists())

    def test_ignored_managed_file_is_not_silently_packaged(self):
        source=self.sources['scope']
        (source/'.gitignore').write_text('setup.html\n');self.commit(source)
        (source/'setup.html').write_text('untracked ignored managed file')
        with self.assertRaisesRegex(MaintenanceError,'tracked'):self.build()
        self.assertFalse(self.output.exists())

    def test_lock_directives_urls_empty_and_duplicates_are_rejected(self):
        invalid=[b'',b'--extra-index-url https://example.invalid\n',b'fixture @ https://example.invalid/file.whl\n',
                 b'fixture==1.0.0\n',self.lock+self.lock]
        for data in invalid:
            with self.subTest(data=data):
                (self.locks/'scope.lock').write_bytes(data)
                with self.assertRaises(MaintenanceError):self.build()
                self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.mkdir();(self.output/'keep').write_text('previous release')
        with self.assertRaisesRegex(MaintenanceError,'exists'):self.build()
        self.assertEqual((self.output/'keep').read_text(),'previous release')

    def test_mismatched_signing_key_leaves_no_completed_output(self):
        second=self.root/'second.key';public=self.root/'second.pub'
        self.command('openssl','genpkey','-algorithm','ED25519','-out',str(second))
        self.command('openssl','pkey','-in',str(second),'-pubout','-out',str(public))
        with self.assertRaisesRegex(MaintenanceError,'signature'):self.build(public_key=public)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('fischer-release-*')))

    def test_keys_or_output_inside_source_repository_are_rejected(self):
        with self.assertRaisesRegex(MaintenanceError,'outside'):self.build(output=self.sources['suite']/'release')
        with self.assertRaisesRegex(MaintenanceError,'outside'):self.build(key=self.sources['suite']/'signing.key')

    def test_invalid_release_version_or_sequence_is_rejected(self):
        for args in ({'release':'main'},{'sequence':0},{'versions':{'suite':'v1.0.0'}}):
            with self.subTest(args=args),self.assertRaises(MaintenanceError):self.build(**args)
        self.assertFalse(self.output.exists())

    def test_source_change_during_build_is_rejected(self):
        original=release.archive_payload
        def altered(payload,archive):
            original(payload,archive)
            if payload.name=='scope':(self.sources['scope']/'app.py').write_text('changed mid-build')
        with patch.object(release,'archive_payload',side_effect=altered):
            with self.assertRaisesRegex(MaintenanceError,'clean|changed'):self.build()
        self.assertFalse(self.output.exists())
