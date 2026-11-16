"""Small transactional engine shared by CLI and future restricted web helper."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid
from .security import MaintenanceError, atomic_json, download, extract, verify_manifest

def version(value):
    return tuple(map(int, value.lstrip('v').split('.')))

def private_directory(path):
    if path.is_symlink():raise MaintenanceError('Private maintenance directory must not be a symlink')
    path.mkdir(parents=True,exist_ok=True,mode=0o700);path.chmod(0o700)

def plan(manifest, installed, requested=None, installing=False):
    desired = set(requested or installed)
    desired.add('suite')
    if not desired <= set(manifest['components']):
        raise MaintenanceError('Selected component is not approved in this release')
    for name in desired:
        for dependency, minimum in manifest['components'][name].get('requires', {}).items():
            if dependency not in desired or version(manifest['components'][dependency]['version']) < version(minimum):
                raise MaintenanceError(f'{name} requires {dependency} {minimum} or later')
    result = []
    for name in sorted(desired):
        old, new = installed.get(name), manifest['components'][name]
        if old and old.get('sha256') == new['sha256']: continue
        if old and old.get('version') and version(new['version']) < version(old['version']):
            raise MaintenanceError(f'{name} downgrade blocked; use a verified backup for rollback')
        if old and old.get('version') == new['version']:
            raise MaintenanceError(f'{name}: published version content changed; publish a new version instead of replacing its artifact')
        result.append(name)
    return result

@contextmanager
def exclusive(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise MaintenanceError('Another install, update or removal is running') from None
        yield
    finally: os.close(fd)

class Engine:
    def __init__(self, root, host, fetch=download):
        self.root, self.host, self.fetch = Path(root), host, fetch
        self.state_path = self.root/'installed.json'
        self.pending = self.root/'pending.json'
        self.flag = self.root/'pending.flag'
        self.lock = self.host.lock_path

    def state(self):
        if not self.state_path.exists(): return {'schema': 1, 'sequence': 0, 'components': {}}
        state = json.loads(self.state_path.read_text())
        if state.get('schema') != 1: raise MaintenanceError('Unknown installed-state schema')
        return state

    def release(self, url, key):
        # Discovery is HTTPS, but only the pinned offline signature authorizes content.
        from .security import github_url
        github_url(url)
        with self.host.temporary() as directory:
            manifest = self.fetch(url, Path(directory)/'manifest.json', maximum=1024*1024)
            signature = self.fetch(url+'.sig', Path(directory)/'manifest.json.sig', maximum=1024)
            raw = manifest.read_bytes()
            return verify_manifest(raw, signature.read_bytes(), key, minimum=self.state()['sequence'])

    def describe(self, manifest, requested=None):
        state = self.state(); actual = self.host.discover()
        unmanaged = actual - set(state['components'])
        changes = plan(manifest, {k:v for k,v in state['components'].items() if k in actual}, requested or actual or {'suite'})
        return {'installed': state['components'], 'discovered': sorted(actual),
                'unmanaged': sorted(unmanaged), 'available': manifest['release'],
                'changes': changes, 'restart': self.host.affected(changes, actual),
                'recovery_pending': self.pending.exists()}

    def prepare(self, manifest, changes, job):
        stages = {}
        for name in changes:
            item = manifest['components'][name]
            archive = self.fetch(item['url'], job/(name+'.tar.gz'), expected=item['sha256'], size=item['size'])
            stages[name] = extract(archive, job/name)
            self.host.validate_payload(name, stages[name])
        return stages

    def apply(self, manifest, requested=None, dry_run=False):
        with exclusive(self.lock):
            if self.pending.exists(): raise MaintenanceError('Interrupted update found. Run instrument-suite rollback before another update')
            report = self.describe(manifest, requested)
            if dry_run: return report
            changes = report['changes']
            if not changes: return {**report, 'result': 'Already up to date; no services restarted'}
            # An unknown existing installation is preserved, never silently adopted.
            touched_unmanaged = set(report['unmanaged']) & (set(changes) | set(report['restart']))
            if touched_unmanaged:
                raise MaintenanceError('Existing unversioned/legacy installation preserved: '+', '.join(sorted(touched_unmanaged))+'. Review and enroll it using the attended migration guide; no automatic adoption')
            self.host.preflight(sum(manifest['components'][n]['size'] for n in changes))
            private_directory(self.root/'transactions')
            job = self.root/'transactions'/uuid.uuid4().hex
            job.mkdir(mode=0o700)
            stages = self.prepare(manifest, changes, job)
            if hasattr(self.host,'refine_affected'):
                report['restart']=self.host.refine_affected(stages,report['restart'])
            self.host.prepare_runtimes(stages, job)
            previous = self.state()
            affected = report['restart']
            # Quiescence leases hold gates closed through activation and validation.
            with self.host.quiesce(affected):
                backup = self.host.backup(job, changes, stages, previous)
                intent = {'schema': 1, 'job': str(job), 'backup': str(backup),
                          'changes': changes, 'affected': affected, 'phase': 'prepared', 'previous': previous}
                atomic_json(self.pending, intent)
                atomic_json(self.flag, {'components': sorted(set(affected) | (set(changes)-{'suite'}))}); self.flag.chmod(0o644)
                stopped = False
                try:
                    self.host.stop(affected); stopped = True
                    intent['phase'] = 'stopped'; atomic_json(self.pending, intent)
                    self.host.activate(stages, job)
                    intent['phase'] = 'activated'; atomic_json(self.pending, intent)
                    self.host.start(affected, changes)
                    self.host.health(affected, changes)
                    # Fresh workers remain gated by pending.flag until commit.
                    next_state = json.loads(json.dumps(previous))
                    for name in changes:
                        item = manifest['components'][name]
                        next_state['components'][name] = {k: item[k] for k in ('version', 'sha256', 'commit')}
                    next_state.update(sequence=manifest['sequence'], release=manifest['release'], updated=time.time())
                    atomic_json(self.state_path, next_state)
                    self.host.publish(next_state)
                    atomic_json(self.root/'public-status.json', {'components':next_state['components'],'release':manifest['release']})
                    (self.root/'public-status.json').chmod(0o644)
                    intent['phase'] = 'committed'; atomic_json(self.pending, intent)
                    atomic_json(self.root/'last-backup.json', {'path': str(backup)})
                    self.flag.unlink(); self.pending.unlink()
                    return {**report, 'result': 'Updated and health checked', 'backup': str(backup)}
                except BaseException as error:
                    # Even a partially completed stop must be recovered.
                    try:
                        self.host.stop(sorted(set(affected)|set(changes)))
                        self.host.restore(backup)
                        atomic_json(self.state_path, previous)
                        self.host.publish(previous)
                        atomic_json(self.root/'public-status.json', {'components':previous['components']});(self.root/'public-status.json').chmod(0o644)
                        self.host.start(affected, [])
                        self.host.health(affected, [])
                        self.flag.unlink(missing_ok=True); self.pending.unlink()
                    except BaseException as recovery:
                        raise MaintenanceError('Activation failed; recovery could not be verified. Controllers remain gated. Run instrument-suite rollback; keep '+str(job)) from recovery
                    raise MaintenanceError('Activation failed; previous software restored and health checked. Backup: '+str(backup)) from error

    def backup(self, dry_run=False):
        with exclusive(self.lock):
            if self.pending.exists(): raise MaintenanceError('Recovery is pending; preserve its backup first')
            if dry_run: return {'action': 'backup', 'components': sorted(self.host.discover())}
            self.root.mkdir(parents=True,exist_ok=True,mode=0o755)
            private_directory(self.root/'backups')
            job = self.root/'backups'/uuid.uuid4().hex; job.mkdir(mode=0o700)
            result = self.host.backup(job, list(self.host.discover()), {}, self.state())
            atomic_json(self.root/'last-backup.json', {'path': str(result)})
            return {'backup': str(result)}

    def rollback(self, dry_run=False):
        with exclusive(self.lock):
            pending = json.loads(self.pending.read_text()) if self.pending.exists() else None
            backup = Path(pending['backup'] if pending else json.loads((self.root/'last-backup.json').read_text())['path'])
            self.host.verify_backup(backup)
            meta = json.loads((backup/'backup.json').read_text())
            if hasattr(self.host,'set_recovery_scope'):self.host.set_recovery_scope(meta)
            affected = meta['affected']
            if dry_run: return {'backup': str(backup), 'restart': affected}
            # On restart after power loss, recover old code with its maintenance gate
            # closed, then require live safe-state verification before releasing it.
            if pending:
                self.host.stop(affected); self.host.restore(backup)
                self.host.start(affected, [])
            with self.host.quiesce(affected):
                if not pending:
                    atomic_json(self.flag, {'components': affected}); self.flag.chmod(0o644)
                    atomic_json(self.pending, {'schema': 1, 'backup': str(backup), 'phase': 'rollback'})
                    self.host.stop(affected); self.host.restore(backup); self.host.start(affected, [])
                self.host.health(affected, [])
                # Rollback does not lower the anti-replay watermark.
                previous = meta['state']; previous['sequence'] = max(previous['sequence'], self.state()['sequence'])
                atomic_json(self.state_path, previous)
                self.host.publish(previous)
                atomic_json(self.root/'public-status.json', {'components':previous['components']});(self.root/'public-status.json').chmod(0o644)
                self.flag.unlink(missing_ok=True); self.pending.unlink(missing_ok=True)
            return {'result': 'Previous software restored and health checked', 'backup': str(backup)}
