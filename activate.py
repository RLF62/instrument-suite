"""Root-only fixed service activation. Never executes package code as root."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from deployment_profile import bind_host,standalone_service,configure_app

BASE=Path('/home/pi')
UNITS=Path('/etc/systemd/system')
RECORDS=Path('/var/lib/fischer-suite-activation')
SIGNED_ACTIVE=Path('/run/fischer-suite-catalog-removal.json')

APPS={'meter':('hp34401a','hp34401a',8082,'standalone_app'),
      'supply':('hp6033a','hp6033a',8083,'supply_standalone'),
      'scope':('tektronix-controller','tektronix-controller',8081,'app'),
      'generator':('hp33120a','hp33120a',8084,'generator_app')}

def run(*args,check=True):
    return subprocess.run(list(args),check=check,timeout=25,stdout=sys.stderr,stderr=sys.stderr)

def perform(tool,action,data):
    if os.geteuid()!=0:raise PermissionError('Service activation requires the installed restricted helper')
    if tool not in APPS or action not in ('start','commit','rollback','remove','commit-remove','restore-remove','remove-signed','recover-signed','install-signed') or set(data)!=({'job','keep_settings'} if action=='remove-signed' else {'job'}) or not re.fullmatch('[a-f0-9]{32}',data['job']):
        raise ValueError('Invalid approved activation request')
    if action in ('remove-signed','recover-signed','install-signed'):
        return signed_operation(tool,action,data)
    folder,service,port,module=APPS[tool];unit=UNITS/(service+'.service')
    RECORDS.mkdir(mode=0o700,exist_ok=True);record=RECORDS/(tool+'.json')
    if action in ('remove','commit-remove','restore-remove'):
        record=RECORDS/(tool+'.removal.json')
        if action=='remove':
            if record.exists():raise RuntimeError('A removal recovery is already pending')
            if not unit.exists() or unit.is_symlink():raise RuntimeError('Removal requires a supported standalone service')
            text=unit.read_text()
            if 'User=pi' not in text or f'WorkingDirectory={BASE}/{folder}\n' not in text or f'{folder}/venv/bin/gunicorn' not in text or not standalone_service(tool,BASE/folder,text,port,module):
                raise RuntimeError('Legacy/shared service preserved; automatic removal requires a standalone controller')
            if 'maintenance_entry:app' in text:
                try:
                    st=SIGNED_ACTIVE.stat();approval=json.loads(SIGNED_ACTIVE.read_text())
                    valid=not SIGNED_ACTIVE.is_symlink() and st.st_uid==0 and not st.st_mode&0o077
                    valid=valid and approval['tool']==tool and approval['job']==data['job'] and time.time()<approval['expires']
                    valid=valid and Path('/proc',str(approval['pid']),'stat').read_text().split()[21]==approval['start']
                except (OSError,ValueError,KeyError,TypeError):valid=False
                if not valid:raise RuntimeError('Use the signed removal operation so instrument safety is verified')
            active=subprocess.run(['systemctl','is-active','--quiet',service]).returncode==0
            enabled=subprocess.run(['systemctl','is-enabled','--quiet',service]).returncode==0
            record.write_text(json.dumps({'job':data['job'],'unit':text,'active':active,'enabled':enabled}));record.chmod(0o600)
            run('systemctl','disable','--now',service)
            unit.unlink();run('systemctl','daemon-reload')
            return {'removed_service':True}
        if not record.exists():return {'committed':action=='commit-remove','restored':False}
        prior=json.loads(record.read_text())
        if prior['job']!=data['job']:raise RuntimeError('Removal belongs to another job')
        if action=='restore-remove':
            if unit.exists() and unit.read_text()!=prior['unit']:raise RuntimeError('Service path is occupied; refusing to overwrite it during recovery')
            unit.write_text(prior['unit']);unit.chmod(0o644);run('systemctl','daemon-reload')
            if prior['enabled']:run('systemctl','enable',service)
            if prior['active']:run('systemctl','start',service)
            record.unlink();return {'restored':True}
        history=RECORDS/'removal-history';history.mkdir(mode=0o700,exist_ok=True)
        record.rename(history/(data['job']+'-'+tool+'.json'));return {'committed':True}
    if action=='start':
        if unit.exists() or unit.is_symlink() or record.exists():raise RuntimeError('Existing service or pending activation preserved')
        broker=UNITS/'fischer-gpib.service';new_broker=tool!='scope' and not broker.exists()
        if tool!='scope' and broker.exists() and '/home/pi/instrument-suite/adapter_broker.py' not in broker.read_text():
            raise RuntimeError('Unrecognized broker service; refusing independent adapter access')
        record.write_text(json.dumps({'job':data['job'],'new_broker':new_broker}));record.chmod(0o600)
        if new_broker:
            rule=Path('/etc/udev/rules.d/70-fischer-gpib.rules')
            if not rule.exists():rule.write_text('SUBSYSTEM=="usb", ATTR{idVendor}=="03eb", ATTR{idProduct}=="2065", MODE="0660", GROUP="www-data"\n')
            run('udevadm','control','--reload-rules')
            run('udevadm','trigger','--action=change','--subsystem-match=usb','--attr-match=idVendor=03eb','--attr-match=idProduct=2065')
            broker.write_text(f'''[Unit]
Description=Fischer shared GPIB adapter owner
After=network.target
[Service]
User=pi
Group=www-data
RuntimeDirectory=fischer-gpib
RuntimeDirectoryMode=0750
UMask=0007
ExecStart={BASE}/{folder}/venv/bin/python {BASE}/instrument-suite/adapter_broker.py
Restart=on-failure
TimeoutStopSec=7
KillMode=control-group
[Install]
WantedBy=multi-user.target
''')
            broker.chmod(0o644)
        unit.write_text(f'''[Unit]
Description=Fischer approved {tool} controller
After=network.target
{'Requires=fischer-gpib.service' if tool!='scope' else ''}
{'After=fischer-gpib.service' if tool!='scope' else ''}
[Service]
User=pi
Group=www-data
WorkingDirectory={BASE}/{folder}
Environment=PYTHONPATH={BASE}/instrument-suite
ExecStart={BASE}/{folder}/venv/bin/gunicorn --workers 1 --threads 4 --bind {bind_host(tool)}:{port} {module}:app
Restart=on-failure
TimeoutStopSec=7
{'NoNewPrivileges=true' if tool=='scope' else ''}
[Install]
WantedBy=multi-user.target
''')
        unit.chmod(0o644)
        run('systemctl','daemon-reload')
        if new_broker:run('systemctl','enable','--now','fischer-gpib')
        run('systemctl','start',service)
        return {'started':True}
    if not record.exists():return {'rolled_back':False}
    prior=json.loads(record.read_text())
    if prior['job']!=data['job']:raise RuntimeError('Activation belongs to another job')
    if action=='commit':
        run('systemctl','enable',service);record.unlink();return {'committed':True}
    run('systemctl','disable','--now',service,check=False)
    if unit.exists():unit.unlink()
    if prior['new_broker']:
        run('systemctl','disable','--now','fischer-gpib',check=False)
        (UNITS/'fischer-gpib.service').unlink(missing_ok=True)
    run('systemctl','daemon-reload');record.unlink();return {'rolled_back':True}

def signed_operation(tool,action,data):
    """Fixed catalog bridge into the already root-owned signed update engine."""
    import contextlib
    import pwd
    sys.path.insert(0,'/opt/fischer-suite-updater/current')
    from maintenance import cli
    from maintenance.engine import Engine,exclusive
    from maintenance.linux import LinuxHost
    from maintenance.security import atomic_json
    import manager_engine as manager
    cli.config()  # Validates the protected enrollment and pinned trust key.
    private=cli.ROOT/'catalog'
    private.mkdir(mode=0o700,exist_ok=True)
    if private.is_symlink() or private.stat().st_uid!=0 or private.stat().st_mode&0o077:
        raise RuntimeError('Unsafe private catalog recovery directory')
    manager.STATE=private
    job=private/data['job']
    job.mkdir(mode=0o700,exist_ok=True)
    if job.is_symlink() or job.stat().st_uid!=0:raise RuntimeError('Unsafe catalog recovery job')
    (job/'install.log').touch(mode=0o600)
    host=LinuxHost(cli.ROOT);engine=Engine(cli.ROOT,host)
    uid=pwd.getpwnam('pi').pw_uid;gid=pwd.getpwnam('pi').pw_gid
    def settings_owner(target):
        for name in manager.SETTINGS[tool]:
            p=target/name
            if not p.exists():continue
            entries=[p,*p.rglob('*')] if p.is_dir() else [p]
            for item in entries:
                if item.is_symlink():raise RuntimeError('Settings path must not be a symlink')
                os.chown(item,uid,gid)
    if action=='install-signed':
        class CatalogHost(LinuxHost):
            def start(self,affected,changes):
                if tool in changes:
                    target=self.folder(tool)
                    manager.restore_settings(tool,target)
                    configure_app(tool,target)
                    settings_owner(target)
                    # Deployment wrappers remain readable by the application account.
                    for name in ('supply_standalone.py','standalone_app.py'):
                        p=target/name
                        if p.is_file():p.chmod(0o644)
                return super().start(affected,changes)
        cfg=cli.config();host=CatalogHost(cli.ROOT);engine=Engine(cli.ROOT,host)
        manifest=engine.release(cli.latest_url(),cfg['key'])
        with contextlib.redirect_stdout(sys.stderr):
            return engine.apply(manifest,[tool])
    with exclusive(host.lock_path):
        if engine.pending.exists():raise RuntimeError('Finish pending signed update recovery before removal')
        if action=='recover-signed':
            manager._recover_remove(tool,job)
            result={'recovered':True}
        else:
            if type(data['keep_settings']) is not bool:raise ValueError('Explicit settings choice required')
            with host.quiesce([tool]):
                atomic_json(SIGNED_ACTIVE,{'tool':tool,'job':data['job'],'pid':os.getpid(),
                    'start':Path('/proc/self/stat').read_text().split()[21],'expires':time.time()+90})
                SIGNED_ACTIVE.chmod(0o600)
                try:result=manager._remove(tool,job,data['keep_settings'],lambda message:None,verified=True)
                finally:SIGNED_ACTIVE.unlink(missing_ok=True)
        # Preserve sequence anti-replay state, but stop reporting a removed app installed.
        if not (host.folder(tool)/({'meter':'standalone_app.py','supply':'app.py','scope':'app.py','generator':'generator_app.py'}[tool])).exists():
            state=engine.state();state['components'].pop(tool,None);atomic_json(engine.state_path,state)
        # HTTPS gateway fallback credentials must retain application ownership.
        from deployment_profile import SECURITY,AUTH_NAMES
        if SECURITY.exists():
            os.chown(SECURITY,uid,gid)
            for name in AUTH_NAMES:
                p=SECURITY/name
                if p.is_file() and not p.is_symlink():os.chown(p,uid,gid)
        return result

if __name__=='__main__':
    try:
        if len(sys.argv)!=3:raise ValueError('Expected approved tool and operation')
        data=json.loads(sys.stdin.read(256));print(json.dumps(perform(sys.argv[1],sys.argv[2],data)))
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
