"""Fixed-path Raspberry Pi adapter. Controller/package code never runs as root."""
from contextlib import contextmanager
import grp
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
from .security import MaintenanceError, atomic_json, safe_member

SPECS = {'suite': ('instrument-suite', 'fischer-suite-dashboard', 8090, 'maintenance.landing'),
         'meter': ('hp34401a', 'hp34401a', 8082, 'standalone_app'),
         'supply': ('hp6033a', 'hp6033a', 8083, 'supply_standalone'),
         'scope': ('tektronix-controller', 'tektronix-controller', 8081, 'app'),
         'generator': ('hp33120a', 'hp33120a', 8084, 'generator_app')}
DIRECTORIES = {'suite': {'hp34401a', 'integration', 'deploy', 'maintenance'},
               'meter': {'hp34401a'}, 'supply': {'templates', 'static', 'docs', 'deploy', 'screenshots', 'tests'},
               'scope': {'docs', 'static'}, 'generator': {'hp33120a'}}
FILES = {'suite': {'activate.py', 'adapter_broker.py', 'adapter_worker.py', 'catalog.html', 'catalog_cli.py',
    'catalog_service.py', 'catalog_web.py', 'deploy_manager.py', 'deployment_profile.py', 'gpib_client.py',
    'manager_engine.py', 'navigation.js', 'suite_gateway.py', 'suite_navigation.py', 'tool_registration.py',
    'patch_hp.py', 'standalone_app.py', 'standalone_install.py', 'install.py', 'build_catalog.py'},
    'meter': {'standalone_app.py', 'gpib_client.py', 'suite_navigation.py', 'navigation.js', 'catalog_web.py', 'catalog.html', 'tool_registration.py', 'suite_gateway.py'},
    'supply': {'app.py', 'supply_standalone.py', 'tool_registration.py'},
    'scope': {'app.py', 'scope_io.py', 'ethernet_transport.py', 'screen_effect.py', 'archive_tools.py', 'example_catalog.py',
              'index.html', 'setup.html', 'tool_registration.py'},
    'generator': {'generator_app.py', 'gpib_client.py', 'suite_navigation.py', 'navigation.js',
                  'catalog_web.py', 'catalog.html'}}
COMMON = {'requirements.txt', 'requirements.lock', 'config.example.json', 'README.md', 'ONE_COMMAND_UPDATER.md','INSTALL.md',
          'STANDALONE.md', 'CATALOG.md', 'GATEWAY_MIGRATION.md', 'DEPLOYMENT.md', 'INSTRUMENT_SUITE.md', 'PROJECT_HANDOFF.md',
          'HTTPS_MIGRATION_VALIDATION.md','GPIB_FIRMWARE.md'}
SYSTEM = (Path('/etc/nginx'), Path('/etc/systemd/system'), Path('/etc/sudoers.d'),
          Path('/etc/fischer-suite'), Path('/etc/udev/rules.d'), Path('/opt/fischer-suite-manager'),
          Path('/etc/ssl'), Path('/etc/letsencrypt'),
          Path('/etc/fischer-suite-updater.json'),Path('/etc/fischer-suite-updater-web.json'))

class LinuxHost:
    def __init__(self, root=Path('/var/lib/fischer-suite-updater'), home=Path('/home/pi')):
        self.root, self.home = Path(root), Path(home)
        self.lock_path = Path('/run/lock/fischer-suite-maintenance.lock')
        self.runtimes = {}
        self.restart_broker = True
        self.config = Path('/etc/fischer-suite-updater.json')

    def run(self, args, as_pi=False, timeout=90, capture=True):
        if as_pi:
            args = ['runuser', '-u', 'pi', '--', 'env', 'HOME=/home/pi', 'PYTHONNOUSERSITE=1', *map(str, args)]
        result = subprocess.run(list(map(str, args)), capture_output=capture, text=True, timeout=timeout,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
        if result.returncode:
            # Do not echo process arguments, environment or package/server output:
            # they can contain private resource names or credentials.
            raise MaintenanceError('Required command failed: '+Path(str(args[0])).name+' (exit '+str(result.returncode)+')')
        return result.stdout or ''

    def temporary(self): return tempfile.TemporaryDirectory(prefix='fischer-release-')
    def folder(self, name): return self.home/SPECS[name][0]

    def service(self, name):
        if name == 'suite' and self.https_gateway():
            unit = Path('/etc/systemd/system/fischer-suite-web.service')
            if not unit.is_file() or unit.is_symlink():
                raise MaintenanceError('Existing HTTPS gateway service must be reviewed before maintenance')
            return 'fischer-suite-web'
        return SPECS[name][1]

    def runtime_link(self, name):
        leaf = 'gateway-venv' if name == 'suite' and self.https_gateway() else 'venv'
        return self.folder(name)/leaf

    def https_gateway(self):
        """Recognize the protected administrator policy without changing the deployment."""
        profile = Path('/etc/fischer-suite/profile.json')
        gateway = Path('/etc/systemd/system/fischer-suite-web.service')
        if not profile.exists():
            if profile.is_symlink() or gateway.exists() or gateway.is_symlink():
                raise MaintenanceError('Existing HTTPS gateway requires its protected deployment policy; no network settings changed')
            return False
        stat = profile.stat()
        if profile.is_symlink() or not profile.is_file() or stat.st_uid != 0 or stat.st_mode & 0o022:
            raise MaintenanceError('HTTPS deployment policy must be root-owned and protected; no network settings changed')
        try:
            value = json.loads(profile.read_text())
        except (OSError, ValueError):
            raise MaintenanceError('HTTPS deployment policy is unreadable; no network settings changed') from None
        if not isinstance(value, dict) or value.get('schema') != 1 or value.get('https_gateway') is not True:
            raise MaintenanceError('Unrecognized HTTPS deployment policy preserved; attended migration required')
        return True

    def publish(self,state):
        records={}
        prior=self.folder('suite')/'registry.json'
        try:records=json.loads(prior.read_text()).get('instruments',{})
        except (OSError,ValueError):pass
        available={}
        for n in state['components']:
            if n=='suite' or not self.folder(n).exists():continue
            available[n]=records.get(n,{'scheme':'http','port':SPECS[n][2],
                                       'path':'/multimeter/classic' if n=='meter' else '/',
                                       'folder':str(self.folder(n))})
        for p,value in [(prior,{'schema':1,'instruments':available}),
                        (self.folder('suite')/'tools.json',{'instruments':list(available)})]:
            if not p.parent.exists():continue
            if p.exists() and json.loads(p.read_text())==value:continue
            atomic_json(p,value);p.chmod(0o644)
    def active(self, name):
        return subprocess.run(['systemctl','is-active','--quiet',self.service(name)], capture_output=True, timeout=10).returncode == 0

    def discover(self):
        return {name for name in SPECS if self.folder(name).exists() or Path('/etc/systemd/system', SPECS[name][1]+'.service').exists()}

    def audit(self, state, recovery_pending=False):
        """Read-only migration inventory. This never enrolls unknown software."""
        gateway = self.https_gateway()
        actual = self.discover()
        known = set(state.get('components', {}))
        blockers = []
        if recovery_pending:
            blockers.append('Complete the existing recovery before enrollment or updates')
        records = {}
        for name in sorted(actual):
            folder = self.folder(name)
            unit_name = 'fischer-suite-web' if name == 'suite' and gateway else SPECS[name][1]
            unit = Path('/etc/systemd/system', unit_name+'.service')
            try:
                text = unit.read_text() if unit.is_file() and not unit.is_symlink() else ''
            except OSError:
                text = ''
            guarded = name == 'suite' or 'maintenance_entry:app' in text
            loopback = name == 'suite' or '--bind 127.0.0.1:' in text or '--bind=127.0.0.1:' in text
            runtime = self.runtime_link(name)
            permanent_runtime = runtime.is_symlink() and runtime.is_dir()
            if name not in known:
                blockers.append(name+': unversioned software preserved; compare with reviewed release artifacts before attended enrollment')
            if not text:
                blockers.append(name+': service layout is missing, unreadable or a legacy symlink; attended review required')
            if not guarded:
                blockers.append(name+': verified maintenance guard must be installed before controller replacement')
            if gateway and name in ('meter','supply','generator') and not loopback:
                blockers.append(name+': HTTPS backend must remain bound to loopback')
            if runtime.exists() and not permanent_runtime:
                blockers.append(name+': preserve the in-directory runtime until a permanent runtime migration is verified')
            records[name] = {'enrolled':name in known, 'service':unit_name,
                             'maintenance_guard_present':guarded, 'loopback_backend':loopback,
                             'permanent_runtime':permanent_runtime,
                             'version':state.get('components', {}).get(name, {}).get('version')}
        return {'action':'audit', 'changes_performed':False,
                'deployment':'https-gateway' if gateway else 'standalone-or-http',
                'components':records, 'requires_attended_enrollment':sorted(actual-known),
                'blocking_reasons':blockers, 'recovery_pending':bool(recovery_pending),
                'next_step':'Resolve the listed items using the attended migration guide; audit never authorizes adoption or instrument interruption'}

    def affected(self, changes, actual):
        return sorted(set(actual) if 'suite' in changes else (set(changes)&set(actual)))

    def refine_affected(self,stages,conservative):
        allowed={'test_build_release.py','test_supply_integration.py','integration/supply_standalone.py','README.md','ONE_COMMAND_UPDATER.md','HTTPS_MIGRATION_VALIDATION.md','test_web_update_policy.py','test_maintenance.py','test_https_migration.py'}|{'maintenance/'+n for n in (
            'landing.py','web_updates.py','web_policy.py','helper.py','cli.py','bootstrap_setup.py','firmware.py','firmware_web.py',
            'engine.py','linux.py','candidate.py','security.py')}
        if 'suite' in stages:
            stage=stages['suite'];changed=[]
            for p in self.managed('suite',stage):
                rel=p.relative_to(stage);target=self.folder('suite')/rel
                if not target.is_file() or target.read_bytes()!=p.read_bytes():changed.append(rel.as_posix())
            if changed and set(changed)<=allowed:
                self.restart_broker=False
                self.actual_affected=sorted((set(conservative)-{'meter','supply','scope','generator'})|((set(stages)-{'suite'})&set(conservative)))
                return self.actual_affected
        self.actual_affected=conservative
        return conservative

    def preflight(self, download_bytes=0):
        if os.geteuid() != 0: raise MaintenanceError('Run sudo instrument-suite for installation operations')
        os_release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        if os_release.get('ID', '').strip('"') not in ('raspbian', 'debian'):
            raise MaintenanceError('Supported OS: Raspberry Pi OS (Debian based)')
        if platform.machine() not in ('aarch64','armv7l','armv6l'):
            raise MaintenanceError('Supported architecture: Raspberry Pi ARM Linux')
        model = Path('/proc/device-tree/model')
        if not model.exists() or b'Raspberry Pi' not in model.read_bytes():
            raise MaintenanceError('This installer currently supports Raspberry Pi hardware only')
        try: pwd.getpwnam('pi')
        except KeyError: raise MaintenanceError('The reviewed installers require a pi account with /home/pi; create it before installation') from None
        required = max(512*1024*1024, download_bytes*6)
        used = sum(p.stat().st_size for name in self.discover() for p in self.folder(name).rglob('*')
                   if p.is_file() and not p.is_symlink() and 'venv' not in p.parts and '__pycache__' not in p.parts)
        if shutil.disk_usage(self.home).free < required+used:
            raise MaintenanceError(f'Insufficient storage. Free at least {(required+used)//(1024*1024)+1} MiB for staging, dependencies and a verified backup')
        for command in ('openssl','nginx','systemctl','curl','runuser','python3','visudo'):
            if not shutil.which(command): raise MaintenanceError('Missing dependency: '+command+'; run the verified bootstrap to install dependencies')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o755)
        if self.root.is_symlink() or self.root.stat().st_uid != 0 or self.root.stat().st_mode & 0o022:
            raise MaintenanceError('Updater state directory must be root-owned and protected')
        self.root.chmod(0o755)  # Only public status/gate files are world-readable; private children are 0700/0600.

    def validate_payload(self, name, source):
        for p in source.rglob('*'):
            if not p.is_file(): continue
            rel = p.relative_to(source); safe_member(rel.as_posix())
            if rel.parts[0] not in DIRECTORIES[name] and rel.name not in FILES[name]|COMMON and not (len(rel.parts)==1 and rel.name.startswith('test_')):
                raise MaintenanceError('Release contains an unsupported managed file: '+name+'/'+rel.as_posix())
        if not (source/'requirements.lock').is_file():
            raise MaintenanceError('Release lacks hash-locked dependency metadata')
        if name == 'supply' and 'FISCHER_SHARED_ADAPTER_V1' not in (source/'app.py').read_text():
            raise MaintenanceError('The approved supply payload must use the shared GPIB adapter')

    def prepare_runtimes(self, stages, job):
        uid, gid = pwd.getpwnam('pi').pw_uid, pwd.getpwnam('pi').pw_gid
        # New runtimes have permanent paths; console-script shebangs never move.
        for name, stage in stages.items():
            previous = self.folder(name)
            runtime_link = self.runtime_link(name)
            lock = stage/'requirements.lock'
            if (runtime_link/'bin/python').exists() and (previous/'requirements.lock').is_file() and (previous/'requirements.lock').read_bytes()==lock.read_bytes():
                self.run([runtime_link/'bin/python','-m','pip','check'], as_pi=True)
                continue
            if runtime_link.exists() and not runtime_link.is_symlink():
                raise MaintenanceError(name+': existing in-directory runtime is preserved. Attended enrollment must establish a permanent runtime before dependency changes')
            runtime = Path('/opt/fischer-suite-runtimes')/job.name/name
            runtime.mkdir(parents=True, mode=0o755); os.chown(runtime, uid, gid)
            runtime.parent.chmod(0o755);runtime.parent.parent.chmod(0o755)
            locked = runtime/'requirements.lock'; shutil.copy2(lock,locked); os.chown(locked,uid,gid)
            self.run(['python3','-m','venv',runtime/'venv'],as_pi=True,timeout=180)
            self.run([runtime/'venv/bin/python','-m','pip','install','--disable-pip-version-check',
                      '--only-binary=:all:','--require-hashes','-r',locked],as_pi=True,timeout=600)
            self.run([runtime/'venv/bin/python','-m','pip','check'],as_pi=True)
            self.runtimes[name] = runtime/'venv'

    @contextmanager
    def quiesce(self, affected):
        connections = []
        try:
            for name in affected:
                if name=='suite':continue
                unit = Path('/etc/systemd/system', SPECS[name][1]+'.service')
                if not unit.is_file() or unit.is_symlink() or 'maintenance_entry:app' not in unit.read_text():
                    raise MaintenanceError(name+': legacy/shared service preserved. Attended enrollment and verified safety guard are required; removal protections stay enabled')
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); connections.append(client)
                client.settimeout(18)
                try:
                    client.connect('/run/fischer-maintenance-'+name+'/control.sock')
                    client.sendall(b'{"action":"quiesce","schema":1}\n')
                    raw = client.makefile('rb').readline(4097)
                    reply = json.loads(raw)
                except (OSError, ValueError):
                    raise MaintenanceError(name+': cannot verify instrument safety. Keep the controller running, verify its connection and retry') from None
                if len(raw)>4096 or reply.get('ok') is not True or reply.get('schema')!=1 or reply.get('tool')!=name or reply.get('state',{}).get('verified') is not True:
                    raise MaintenanceError(name+': '+str(reply.get('error','Safety condition could not be verified')))
            yield
        finally:
            for connection in connections: connection.close()

    def managed(self, name, folder):
        for p in folder.rglob('*') if folder.exists() else []:
            if not p.is_file() or p.is_symlink(): continue
            rel = p.relative_to(folder)
            if any(x in {'venv','__pycache__','.git'} for x in rel.parts): continue
            if rel.parts[0] in DIRECTORIES[name] or (len(rel.parts)==1 and (rel.name in FILES[name]|COMMON|{'maintenance_guard.py','maintenance_entry.py'} or rel.name.startswith('test_'))):
                yield p

    def backup(self, job, changes, stages, state):
        destination = Path(job)/'backup'; destination.mkdir(mode=0o700)
        affected = sorted(set(getattr(self,'actual_affected',self.affected(changes,self.discover())))|set(changes))
        files = []
        # Code inventory includes all installed components for an explicit backup;
        # an update stores only selected code, preserving unrelated applications.
        for name in changes:
            for p in self.managed(name,self.folder(name)): files.append(p)
            files.append(Path('/etc/systemd/system',self.service(name)+'.service'))
        if 'suite' in changes:
            files += [Path('/etc/nginx/sites-available/fischer-suite-dashboard'),Path('/etc/nginx/sites-enabled/fischer-suite-dashboard')]
            files += [Path('/etc/systemd/system/fischer-gpib.service'),Path('/etc/udev/rules.d/70-fischer-gpib.rules')]
        inventory=[]
        for target in dict.fromkeys(files):
            if target.is_symlink():
                raise MaintenanceError('Unexpected managed symlink; attended migration required: '+str(target))
            if target.is_file():
                slot=destination/'files'/str(len(inventory));slot.parent.mkdir(exist_ok=True);shutil.copy2(target,slot)
                inventory.append({'path':str(target),'slot':str(slot.relative_to(destination)),'sha256':hashlib.sha256(slot.read_bytes()).hexdigest(), 'mode':target.stat().st_mode&0o777})
        # Comprehensive private backup is independent of code-only rollback.
        paths=[self.folder(n) for n in self.discover()]+[p for p in SYSTEM if p.exists()]
        archive=destination/'private-system.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            def filter_member(member):
                if any(x in {'venv','gateway-venv','__pycache__','.git'} for x in Path(member.name).parts): return None
                return member
            for p in paths:
                if p.exists():tar.add(p,arcname=str(p).lstrip('/'),filter=filter_member)
        archive.chmod(0o600)
        with tarfile.open(archive) as tar:
            for member in tar:
                if member.isfile():
                    stream=tar.extractfile(member)
                    while stream.read(65536):pass
        metadata={'schema':1,'state':state,'affected':affected,'changes':changes,'files':inventory,
                  'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'absent':[str(self.folder(n)) for n in changes if not self.folder(n).exists()],
                  'venvs':{n:os.readlink(self.runtime_link(n)) if self.runtime_link(n).is_symlink() else None for n in changes},
                  'runtime_links':{n:self.runtime_link(n).name for n in changes},
                  'created_files':[],'created_units':[],
                  'restart_broker':self.restart_broker,
                  'engine_link':os.readlink('/opt/fischer-suite-updater/current') if Path('/opt/fischer-suite-updater/current').is_symlink() else None,
                  'broker_active':subprocess.run(['systemctl','is-active','--quiet','fischer-gpib'],capture_output=True,timeout=10).returncode==0,
                  'service_states':{n:{'active':self.active(n),'enabled':subprocess.run(['systemctl','is-enabled','--quiet',self.service(n)],capture_output=True,timeout=10).returncode==0} for n in changes}}
        atomic_json(destination/'backup.json',metadata)
        (destination/'RECOVERY.txt').write_text('Run sudo instrument-suite rollback. Code rollback preserves current private settings. private-system.tar.gz contains applications and private system configuration; restore those only through an attended administrator recovery. Never start an uncoordinated GPIB process alongside the broker.\n')
        self.verify_backup(destination)
        return destination

    def verify_backup(self, backup):
        backup=Path(backup)
        if backup.is_symlink() or not backup.resolve().is_relative_to(self.root.resolve()): raise MaintenanceError('Backup is outside the protected updater directory')
        if backup.stat().st_uid!=0 or backup.stat().st_mode&0o077: raise MaintenanceError('Backup permissions are unsafe')
        data=json.loads((backup/'backup.json').read_text())
        if data['schema']!=1:raise MaintenanceError('Unknown backup schema')
        if hashlib.sha256((backup/'private-system.tar.gz').read_bytes()).hexdigest()!=data['archive_sha256']:raise MaintenanceError('Backup integrity check failed')
        for item in data['files']:
            slot=backup/item['slot']
            if not slot.resolve().is_relative_to(backup.resolve()) or hashlib.sha256(slot.read_bytes()).hexdigest()!=item['sha256']:raise MaintenanceError('Backup file integrity check failed')
        return data

    def set_recovery_scope(self,metadata):
        self.restart_broker=metadata.get('restart_broker',True)
        if type(self.restart_broker) is not bool:raise MaintenanceError('Invalid broker recovery policy')
        if self.restart_broker and 'suite' in metadata['affected']:
            required=self.discover()&{'meter','supply','scope','generator'}
            if not required<=set(metadata['affected']):raise MaintenanceError('Recovery would interrupt a shared broker without controller safety checks')

    def stop(self, affected):
        for name in affected:
            service = self.service(name)
            if Path('/etc/systemd/system',service+'.service').exists():self.run(['systemctl','stop',service])
        if 'suite' in affected and self.restart_broker and Path('/etc/systemd/system/fischer-gpib.service').exists():self.run(['systemctl','stop','fischer-gpib'])

    def copy_atomic(self, source, target):
        if target.is_symlink():raise MaintenanceError('Managed file is a symlink: '+str(target))
        root=target.parent
        for p in [root,*root.parents]:
            if p.is_symlink():raise MaintenanceError('Managed directory is a symlink: '+str(p))
        missing=[];parent=root
        while not parent.exists():missing.append(parent);parent=parent.parent
        for parent in reversed(missing):parent.mkdir(mode=0o755);parent.chmod(0o755)
        fd,tmp=tempfile.mkstemp(dir=root)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(Path(source).read_bytes());stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,0o644);os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)

    def activate(self, stages, job):
        gateway = self.https_gateway()
        backup=Path(job)/'backup';meta=json.loads((backup/'backup.json').read_text())
        uid,gid=pwd.getpwnam('pi').pw_uid,pwd.getpwnam('pi').pw_gid
        for name,source in stages.items():
            target=self.folder(name);fresh=not target.exists();target.mkdir(exist_ok=True)
            for p in self.managed(name,source):
                dest=target/p.relative_to(source)
                # Existing deployment/authentication wrapper is server policy.
                if name=='supply' and dest.name=='supply_standalone.py' and dest.exists():continue
                if dest.is_file() and dest.read_bytes()==p.read_bytes():continue
                if not dest.exists():meta['created_files'].append(str(dest));atomic_json(backup/'backup.json',meta)
                prepared=p
                if gateway and name=='meter' and p.relative_to(source).as_posix()=='standalone_app.py':
                    text=p.read_text()
                    if '# FISCHER_GATEWAY_PROXY:' not in text:
                        text+='\n# FISCHER_GATEWAY_PROXY: backend is bound to loopback by the root helper.\nfrom werkzeug.middleware.proxy_fix import ProxyFix\napp.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)\n'
                    prepared=Path(job)/'meter-https-standalone.py'
                    prepared.write_text(text)
                self.copy_atomic(prepared,dest)
            if name in self.runtimes:
                link=self.runtime_link(name)
                if link.exists() and not link.is_symlink():
                    raise MaintenanceError('Existing in-directory runtime preserved; attended enrollment must establish a permanent runtime first')
                link.unlink(missing_ok=True);link.symlink_to(self.runtimes[name],target_is_directory=True)
            if fresh:
                os.chown(target,uid,gid)
                config=target/'config.example.json'
                if name in ('suite','supply') and config.exists():
                    shutil.copy2(config,target/'config.json');os.chown(target/'config.json',uid,gid);(target/'config.json').chmod(0o600)
                if name=='scope':
                    atomic_json(target/'connection.json',{'address':'scope-not-configured.invalid','timeout':6});os.chown(target/'connection.json',uid,gid)
            if name!='suite':self.entry(name,job,meta)
            unit=Path('/etc/systemd/system',self.service(name)+'.service')
            if not unit.exists():
                meta['created_units'].append(str(unit));atomic_json(backup/'backup.json',meta)
                module='maintenance.landing' if name=='suite' else 'maintenance_entry'
                dependencies='Requires=fischer-gpib.service\nAfter=fischer-gpib.service\n' if name in ('meter','supply','generator') else ''
                text=f'[Unit]\nDescription=Fischer {name} controller\nAfter=network.target\n{dependencies}[Service]\nUser=pi\nGroup=www-data\nWorkingDirectory={target}\nEnvironment=PYTHONPATH={self.folder("suite")}\nRuntimeDirectory=fischer-maintenance-{name}\nRuntimeDirectoryMode=0700\nExecStart={target}/venv/bin/gunicorn --workers 1 --threads 4 --bind {"127.0.0.1" if name=="suite" or gateway and name in ("meter","supply") else "0.0.0.0"}:{SPECS[name][2]} {module}:app\nRestart=on-failure\nTimeoutStopSec=20\n[Install]\nWantedBy=multi-user.target\n'
                unit.write_text(text);unit.chmod(0o644)
        if 'suite' in stages:self.shared_setup(stages['suite'],job,meta)
        if set(stages)&{'meter','supply','generator'}:
            broker=Path('/etc/systemd/system/fischer-gpib.service')
            if not broker.exists():
                meta['created_units'].append(str(broker));atomic_json(backup/'backup.json',meta)
                broker.write_text(f'[Unit]\nDescription=Fischer shared GPIB adapter owner\nAfter=network.target\n[Service]\nUser=pi\nGroup=www-data\nRuntimeDirectory=fischer-gpib\nRuntimeDirectoryMode=0750\nUMask=0007\nExecStart={self.folder("suite")}/venv/bin/python {self.folder("suite")}/adapter_broker.py\nRestart=on-failure\nTimeoutStopSec=10\n[Install]\nWantedBy=multi-user.target\n');broker.chmod(0o644)
                rule=Path('/etc/udev/rules.d/70-fischer-gpib.rules')
                if not rule.exists():
                    meta['created_files'].append(str(rule));atomic_json(backup/'backup.json',meta)
                    rule.write_text('SUBSYSTEM=="usb", ATTR{idVendor}=="03eb", ATTR{idProduct}=="2065", MODE="0660", GROUP="www-data"\n');rule.chmod(0o644)
                    self.run(['udevadm','control','--reload-rules'])
                    self.run(['udevadm','trigger','--action=change','--subsystem-match=usb','--attr-match=idVendor=03eb','--attr-match=idProduct=2065'])
        self.run(['systemctl','daemon-reload'])

    def entry(self,name,job,meta):
        target=self.folder(name);path=target/'maintenance_entry.py'
        if not path.exists():meta['created_files'].append(str(path));atomic_json(Path(job)/'backup/backup.json',meta)
        module=SPECS[name][3]
        text=f'import {module} as controller\nfrom maintenance.guard import install\napp=controller.app\n'
        if name=='supply':text+='controller=controller.controller\n'
        extras=''
        if name=='meter':text+='import hp34401a as meter\n';extras=', meter=meter'
        if name=='scope':text+='import scope_io\n';extras=', scope_io=scope_io'
        text+=f'install(app,{name!r},controller{extras})\n'
        temporary=Path(job)/(name+'-entry.py');temporary.write_text(text);self.copy_atomic(temporary,path)

    def setup_dashboard_site(self,job,meta):
        # Never refresh the legacy catalog helper here: it restarts unrelated
        # controllers and has its own removal protections. Preserve it unchanged.
        site=Path('/etc/nginx/sites-available/fischer-suite-dashboard')
        enabled=Path('/etc/nginx/sites-enabled/fischer-suite-dashboard')
        if not site.exists():
            meta['created_files'] += [str(site),str(enabled)];atomic_json(Path(job)/'backup/backup.json',meta)
            text='server { listen 8080; server_name _; location / { proxy_pass http://127.0.0.1:8090; proxy_set_header Host $http_host; } }\n'
            site.write_text(text);site.chmod(0o644)
            # Regular include avoids a new symlink in a rollback-managed path.
            enabled.write_text('include /etc/nginx/sites-available/fischer-suite-dashboard;\n');enabled.chmod(0o644)
        original='server { listen 8080; server_name _; location / { proxy_pass http://127.0.0.1:8090; proxy_set_header Host $http_host; } }\n'
        if site.read_text()==original:
            site.write_text(original.replace('proxy_set_header Host $http_host;', 'proxy_set_header Host $http_host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-Proto $scheme;'))
            site.chmod(0o644)
        self.run(['nginx','-t'])
        self.run(['systemctl','reload','nginx'])
    def shared_setup(self,source,job,meta):
        # Keep the existing HTTPS gateway and its authentication/certificates.
        # In particular, never add the fresh-install HTTP listener alongside it.
        if not self.https_gateway():
            self.setup_dashboard_site(job,meta)
        engines=Path('/opt/fischer-suite-updater/releases');engines.mkdir(parents=True,exist_ok=True,mode=0o755)
        engine=engines/Path(job).name;engine.mkdir(mode=0o755)
        shutil.copytree(source/'maintenance',engine/'maintenance')
        for directory,dirs,files in os.walk(engine):
            os.chmod(directory,0o755)
            for name in files:os.chmod(Path(directory)/name,0o644)
        runner=engine/'runner.py';runner.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parent))\nfrom maintenance.cli import main\nraise SystemExit(main())\n');runner.chmod(0o644)
        pointer=engines.parent/'current';temporary=engines.parent/'next'
        if pointer.exists() and not pointer.is_symlink():raise MaintenanceError('Unexpected updater engine layout; preserved it')
        temporary.symlink_to(engine,target_is_directory=True);os.replace(temporary,pointer)

    def start(self, affected, changes):
        names=sorted(set(affected)|set(changes),key=lambda n:n!='suite')
        needs_broker = bool(set(names)&{'meter','supply'}) or ('suite' in names and self.restart_broker)
        if Path('/etc/systemd/system/fischer-gpib.service').exists() and needs_broker:
            self.run(['systemctl','start','fischer-gpib'])
        for name in names:
            service = self.service(name)
            if Path('/etc/systemd/system',service+'.service').exists() and (self.runtime_link(name)/'bin/python').exists():self.run(['systemctl','start',service])
        for name in changes:
            service = self.service(name)
            if Path('/etc/systemd/system',service+'.service').exists():self.run(['systemctl','enable',service])

    def health(self, affected, changes):
        for name in sorted(set(affected)|set(changes)):
            service = self.service(name)
            if not Path('/etc/systemd/system',service+'.service').exists():continue
            for attempt in range(20):
                try:
                    if not self.active(name):raise MaintenanceError('Service not active')
                    if name!='suite':
                        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
                            s.settimeout(2);s.connect('/run/fischer-maintenance-'+name+'/control.sock')
                            s.sendall(b'{"action":"health","schema":1}\n');data=json.loads(s.makefile('rb').readline(4097))
                            if data.get('ok') is not True or data.get('tool')!=name:raise MaintenanceError('Controller guard not ready')
                    if name == 'suite':
                        command = ['curl','--fail','--silent','--max-time','2']
                        if self.https_gateway():
                            command += ['--unix-socket','/run/hp6033a/gunicorn.sock',
                                        'http://localhost/api/suite/navigation.js']
                        else:
                            command += [f'http://127.0.0.1:{SPECS[name][2]}/']
                    else:
                        command = ['systemctl','is-active',service]
                    self.run(command)
                    break
                except (OSError,ValueError,MaintenanceError):
                    if attempt==19:raise MaintenanceError(name+' failed activation health checks')
                    time.sleep(.25)

    def restore(self, backup):
        backup=Path(backup);data=self.verify_backup(backup)
        for path in reversed(data['created_files']+data['created_units']):
            p=Path(path)
            if p.is_file() or p.is_symlink():p.unlink()
        for item in data['files']:
            self.copy_atomic(backup/item['slot'],Path(item['path']));Path(item['path']).chmod(item['mode'])
        for name,previous in data['venvs'].items():
            leaf = data.get('runtime_links', {}).get(name, 'venv')
            if leaf not in ('venv', 'gateway-venv') or leaf == 'gateway-venv' and name != 'suite':
                raise MaintenanceError('Invalid backup runtime path')
            link=self.folder(name)/leaf
            if link.is_symlink():
                link.unlink()
                if previous:link.symlink_to(previous,target_is_directory=True)
        for folder in data['absent']:
            p=Path(folder)
            if p not in {self.folder(n) for n in data['changes']} or p.is_symlink():raise MaintenanceError('Invalid new-application recovery path')
            if p.exists():shutil.rmtree(p)
        pointer=Path('/opt/fischer-suite-updater/current')
        if pointer.is_symlink():
            pointer.unlink()
            if data.get('engine_link'):pointer.symlink_to(data['engine_link'],target_is_directory=True)
        self.run(['systemctl','daemon-reload'])
        for name,state in data.get('service_states',{}).items():
            service = self.service(name)
            if Path('/etc/systemd/system',service+'.service').exists():
                self.run(['systemctl','enable' if state['enabled'] else 'disable',service])
        if Path('/etc/nginx/nginx.conf').exists():self.run(['nginx','-t']);self.run(['systemctl','reload','nginx'])
