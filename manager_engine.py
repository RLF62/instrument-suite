"""Approved-package installation. Root handles fixed files/units; package code runs as pi."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import tempfile
import subprocess
import time
import urllib.request
import zipfile
from deployment_profile import public_records,configure_app,sync_security,standalone_service

HOME=Path('/home/pi')
SUITE=HOME/'instrument-suite'
ROOT=Path('/opt/fischer-suite-manager')
STATE=HOME/'.instrument-suite-manager'
UNITS=Path('/etc/systemd/system')
REGISTRY=SUITE/'registry.json'
APP_DIRS={'meter':'hp34401a','supply':'hp6033a','scope':'tektronix-controller'}
SERVICES={'meter':'hp34401a','supply':'hp6033a','scope':'tektronix-controller'}
PORTS={'meter':8082,'supply':8083,'scope':8081}

def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        if json.loads(path.read_text())==data:return
    except (OSError,ValueError):pass
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
        stream.write(json.dumps(data,indent=2)+'\n');tmp=Path(stream.name)
    tmp.chmod(0o644);os.replace(tmp,path)

def command(args,log,as_pi=False,timeout=180):
    if as_pi and os.geteuid()==0:args=['runuser','-u','pi','--',*map(str,args)]
    with log.open('a') as out:
        out.write('Running: '+' '.join(map(str,args))+'\n');out.flush()
        subprocess.run(list(map(str,args)),stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,check=True,timeout=timeout,
                       env={**os.environ,'HOME':str(HOME),'USER':'pi','LOGNAME':'pi','PYTHONUNBUFFERED':'1'})

def catalog():
    data=json.loads((ROOT/'catalog.json').read_text())
    if set(data['tools'])!={'meter','supply','scope'}:raise RuntimeError('Invalid approved catalog')
    return data

def unpack(tool,destination):
    item=catalog()['tools'][tool];archive=ROOT/'packages'/(tool+'.zip')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Approved package checksum did not match')
    with zipfile.ZipFile(archive) as source:
        size=0
        for entry in source.infolist():
            path=Path(entry.filename);size+=entry.file_size
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or (entry.external_attr>>16)&0o170000==0o120000:
                raise RuntimeError('Unsafe package path')
        if size>100_000_000:raise RuntimeError('Approved package is too large')
        source.extractall(destination)
    return destination

def pi_owned(path):
    if os.geteuid()!=0:return
    uid=pwd.getpwnam('pi').pw_uid;gid=pwd.getpwnam('pi').pw_gid
    for folder,dirs,files in os.walk(path):
        os.chown(folder,uid,gid)
        for name in files:
            p=Path(folder)/name
            if p.is_symlink():raise RuntimeError('Unexpected application symlink')
            os.chown(p,uid,gid)

def active(service,user=False):
    args=['systemctl','is-active','--quiet',service]
    if user:
        args=['env','XDG_RUNTIME_DIR=/run/user/'+str(pwd.getpwnam('pi').pw_uid),'systemctl','--user','is-active','--quiet',service]
        if os.geteuid()==0:args=['runuser','-u','pi','--',*args]
    return subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0

def healthy(port,path='/'):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=2) as response:return response.status==200
    except (OSError,ValueError):return False

def scan():
    result={}
    hp=HOME/'hp6033a/app.py';hp_text=hp.read_text() if hp.exists() else ''
    if hp_text and active('hp6033a'):
        if (HOME/'hp6033a/supply_standalone.py').exists():
            ok=healthy(8083);port=8083;scheme='http'
        else:
            check=subprocess.run(['curl','-fsS','--max-time','2','--unix-socket','/run/hp6033a/gunicorn.sock','http://localhost/'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=4)
            ok=check.returncode==0;port=None;site=Path('/etc/nginx/sites-enabled/hp6033a');scheme='https' if site.exists() and 'listen 443' in site.read_text() else 'http'
        if ok:
            result['supply']={'port':port,'scheme':scheme,'path':'/','folder':str(HOME/'hp6033a')}
            if 'FISCHER_SHARED_ADAPTER_V1' in hp_text and 'install_meter(app)' in hp_text and (SUITE/'hp34401a').exists():
                result['meter']={'port':port,'scheme':scheme,'path':'/multimeter/classic','folder':str(SUITE/'hp34401a')}
    if 'meter' not in result and (HOME/'hp34401a/standalone_app.py').exists() and active('hp34401a') and healthy(8082,'/api/multimeter/status'):
        result['meter']={'port':8082,'scheme':'http','path':'/multimeter/classic','folder':str(HOME/'hp34401a')}
    if (HOME/'tektronix-controller/app.py').exists() and (active('tektronix-controller') or active('tektronix-controller',True)) and healthy(8081,'/api/config'):
        result['scope']={'port':8081,'scheme':'http','path':'/','folder':str(HOME/'tektronix-controller')}
    return public_records(result)

def register(force=False):
    tools=scan()
    if tools or force:
        atomic(REGISTRY,{'schema':1,'instruments':tools})
        atomic(SUITE/'tools.json',{'instruments':list(tools)})
    return tools

def unit_text(tool):
    folder=HOME/APP_DIRS[tool];module='standalone_app' if tool=='meter' else 'supply_standalone' if tool=='supply' else 'app'
    return f'''[Unit]
Description=Fischer {tool} web controller
After=network.target
{'Requires=fischer-gpib.service' if tool!='scope' else ''}
{'After=fischer-gpib.service' if tool!='scope' else ''}
[Service]
User=pi
Group=www-data
WorkingDirectory={folder}
Environment=PYTHONPATH={SUITE}
ExecStart={folder}/venv/bin/gunicorn --workers 1 --threads 4 --bind 0.0.0.0:{PORTS[tool]} {module}:app
Restart=on-failure
TimeoutStopSec=7
[Install]
WantedBy=multi-user.target
'''

def ensure_broker(meter_source,python,log):
    unit=UNITS/'fischer-gpib.service'
    if unit.exists():
        if str(SUITE/'adapter_broker.py') not in unit.read_text():raise RuntimeError('Unrecognized adapter owner; refusing a competing connection')
        return
    SUITE.mkdir(exist_ok=True)
    for name in ('adapter_broker.py','adapter_worker.py','gpib_client.py'):shutil.copy2(meter_source/name,SUITE/name)
    config=SUITE/'config.json'
    if not config.exists():shutil.copy2(meter_source/'config.example.json',config);config.chmod(0o600)
    pi_owned(SUITE)

def activate(tool,operation,job,log,keep_settings=None):
    if tool not in APP_DIRS or operation not in ('start','commit','rollback','remove','commit-remove','restore-remove','remove-signed','recover-signed','install-signed'):raise ValueError('Invalid activation request')
    args=['sudo','-n','/usr/bin/python3','-I',str(ROOT/'activate.py'),tool,operation]
    data={'job':job.name}
    if keep_settings is not None:data['keep_settings']=keep_settings
    result=subprocess.run(args,input=json.dumps(data),capture_output=True,text=True,timeout=900 if operation=='install-signed' else 90)
    with log.open('a') as stream:stream.write(result.stderr)
    if result.returncode:raise RuntimeError('Service activation '+operation+' failed: '+result.stderr[-800:])
    return json.loads(result.stdout)

UPDATER_CONFIG=Path('/etc/fischer-suite-updater.json')

def provision(tool,job,notify):
    if tool not in APP_DIRS:raise ValueError('Choose an approved instrument')
    if tool in scan():register();return {'already_installed':True}
    if UPDATER_CONFIG.exists():
        notify('Installing through the signed updater with retained settings and safety checks')
        result=activate(tool,'install-signed',job,job/'install.log')
        register(force=True)
        return result
    target=HOME/APP_DIRS[tool];unit=UNITS/(SERVICES[tool]+'.service')
    stub=is_runtime_stub(tool)
    if (target.exists() and not stub) or target.is_symlink() or unit.exists():
        raise RuntimeError('Existing files or service found. Preserved them; repair/register the existing controller before installing.')
    if (HOME/'.config/systemd/user'/(SERVICES[tool]+'.service')).exists():
        raise RuntimeError('Existing user service found; preserved it. Start or repair that controller before registration.')
    hp=HOME/'hp6033a/app.py'
    if tool!='scope' and hp.exists() and 'FISCHER_SHARED_ADAPTER_V1' not in hp.read_text():
        raise RuntimeError('Existing supply uses direct adapter access; integrate coordination before adding a GPIB tool')
    log=job/'install.log';source=job/'source';source.mkdir(mode=0o755)
    notify('Verifying approved package checksum')
    unpack(tool,source)
    # Write recovery intent before creating any application/service paths.
    atomic(job/'recovery.json',{'tool':tool,'target_created':True,**({'runtime_stub':True} if stub else {})})
    try:
        notify('Preparing application files and isolated dependencies')
        target.mkdir(exist_ok=stub)
        if tool=='meter':
            for name in ('standalone_app.py','gpib_client.py','suite_navigation.py','navigation.js','catalog_web.py','catalog.html'):
                shutil.copy2(source/name,target/name)
            shutil.copytree(source/'hp34401a',target/'hp34401a')
            tests=['test_standalone','test_standalone_install','test_views','test_coordination']
        elif tool=='supply':
            for name in ('app.py','requirements.txt','config.example.json'):shutil.copy2(source/name,target/name)
            for name in ('templates','static','docs','deploy'):shutil.copytree(source/name,target/name)
            # Patched app comes from a reviewed package, never a direct VISA controller.
            if 'FISCHER_SHARED_ADAPTER_V1' not in (target/'app.py').read_text():raise RuntimeError('Supply package is not coordinated')
            shutil.copy2(source/'supply_standalone.py',target/'supply_standalone.py')
            shutil.copy2(source/'config.example.json',target/'config.json')
            tests=[]
        else:
            for name in ('app.py','archive_tools.py','ethernet_transport.py','example_catalog.py','scope_io.py','screen_effect.py','index.html','setup.html','requirements.txt'):
                shutil.copy2(source/name,target/name)
            shutil.copytree(source/'docs',target/'docs')
            if (source/'static').is_dir():shutil.copytree(source/'static',target/'static')
            atomic(target/'connection.json',{'address':'scope-not-configured.invalid','timeout':6})
            tests=['discover','-s',str(source),'-p','test_*.py']
        shutil.copy2(source/'tool_registration.py',target/'tool_registration.py')
        pi_owned(target)
        python=target/'venv/bin/python'
        if stub:
            # Never upgrade packages beneath the running shared broker.
            check="import importlib.metadata as m,sys; r=[s.strip().split('==') for s in open(sys.argv[1]) if s.strip() and not s.startswith('#')]; bad=[n for n,v in r if m.version(n)!=v]; print('Shared runtime dependency mismatches:',bad); sys.exit(bool(bad))"
            command([python,'-c',check,source/'requirements.txt'],log,as_pi=True)
        else:
            command(['python3','-m','venv',str(target/'venv')],log,as_pi=True)
            command([python,'-m','pip','install','-r',source/'requirements.txt'],log,as_pi=True,timeout=420)
        notify('Checking software before starting the controller')
        if tests:
            command([python,'-m','unittest',*tests],log,as_pi=True,timeout=120) if tool=='scope' else command([python,'-m','unittest','discover','-s',source,'-p','test_views.py'],log,as_pi=True,timeout=120)
        restore_settings(tool,target)
        configure_app(tool,target)
        if tool!='scope':
            meter_source=source if tool=='meter' else unpack('meter',job/'shared-meter')
            ensure_broker(meter_source,python,log)
        notify('Starting web service; instrument communication stays unconfigured')
        activate(tool,'start',job,log)
        endpoint='/api/multimeter/status' if tool=='meter' else '/api/config' if tool=='scope' else '/'
        for attempt in range(30):
            if healthy(PORTS[tool],endpoint):break
            if attempt==29:raise RuntimeError('Controller did not become ready within the startup limit')
            time.sleep(.5)
        notify('Registering installed controller and navigation links')
        registered=register()
        if tool not in registered:raise RuntimeError('Controller startup passed but registration could not verify it')
        activate(tool,'commit',job,log)
        (target/'.shared-broker-runtime.json').unlink(missing_ok=True)
        (job/'recovery.json').unlink()
        return registered[tool]
    except Exception:
        rollback(tool,job)
        raise

def rollback(tool,job):
    # Only targets proven absent before this job may be stopped/quarantined.
    intent=job/'recovery.json'
    if not intent.exists():return
    data=json.loads(intent.read_text())
    if data not in ({'tool':tool,'target_created':True},{'tool':tool,'target_created':True,'runtime_stub':True}) or tool not in APP_DIRS:raise RuntimeError('Invalid recovery manifest')
    log=job/'install.log'
    outcome=activate(tool,'rollback',job,log)
    if not outcome.get('rolled_back') and tool in scan():intent.unlink();register();return
    target=HOME/APP_DIRS[tool]
    if target.exists() and not target.is_symlink():
        if data.get('runtime_stub'):
            failed=job/'failed-app';failed.mkdir()
            for p in target.iterdir():
                if p.name not in ('venv','.shared-broker-runtime.json'):p.rename(failed/p.name)
        else:target.rename(target.with_name(target.name+'.failed-'+job.name))
    intent.unlink();register()

SETTINGS={'meter':('appearance.json','presets.json'),
          'supply':('config.json','config.example.json','presets.json','.hp6033a-version.json','.control_auth_mode','.control_htpasswd'),
          'scope':('connection.json','appearance.json','measurement-selection.json','presets.json','captures','setup-backups','personal-examples')}

def is_runtime_stub(tool):
    target=HOME/APP_DIRS[tool];marker=target/'.shared-broker-runtime.json'
    if target.is_symlink() or not marker.is_file():return False
    try:
        return json.loads(marker.read_text())=={'tool':tool,'runtime_only':True} and (target/'venv/bin/python').exists() and {p.name for p in target.iterdir()} <= {'venv',marker.name}
    except (OSError,ValueError):return False

def removal_policy(tool):
    target=HOME/APP_DIRS[tool];unit=UNITS/(SERVICES[tool]+'.service')
    try:
        records=json.loads(REGISTRY.read_text()).get('instruments',{})
        record=records.get(tool,{})
        if record.get('folder') and Path(record['folder'])!=target:
            return False,'This instrument is integrated into another web host. Migrate it to standalone before removal.'
    except FileNotFoundError:pass
    except (OSError,ValueError,TypeError,AttributeError):return False,'Repair controller registration before removal.'
    module='standalone_app' if tool=='meter' else 'supply_standalone' if tool=='supply' else 'app'
    if target.is_symlink() or not unit.is_file() or unit.is_symlink():return False,'Removal is available for standalone/catalog services; this legacy or shared installation is protected.'
    try:text=unit.read_text()
    except OSError:return False,'Service definition is not readable; administrator setup must repair its permissions.'
    if not standalone_service(tool,target,text,PORTS[tool],module):
        return False,'This controller shares a legacy service. Migrate it before removal so other tools stay available.'
    return True,''

def checked_archive(tool,job_id):
    if tool not in APP_DIRS or not re.fullmatch('[a-f0-9]{32}',job_id):raise ValueError('Invalid removal archive')
    archive=STATE/'removed'/tool/job_id/'app'
    if archive.exists() and archive.resolve()!=archive.absolute():raise RuntimeError('Removal archive must not use symlinks')
    return archive

def restore_settings(tool,target):
    marker=STATE/'retained'/(tool+'.json')
    if not marker.exists():return
    retained=json.loads(marker.read_text())
    if not retained.get('keep_settings'):return
    archive=checked_archive(tool,retained['job'])
    for name in SETTINGS[tool]:
        source=archive/name;destination=target/name
        if source.is_symlink():raise RuntimeError('Settings recovery refuses symbolic links')
        if source.is_dir():
            if any(p.is_symlink() for p in source.rglob('*')):raise RuntimeError('Settings recovery refuses symbolic links')
            shutil.copytree(source,destination,dirs_exist_ok=True)
        elif source.is_file():shutil.copy2(source,destination)

def remove(tool,job,keep_settings,notify):
    if UPDATER_CONFIG.exists():
        notify('Verifying signed controller safety before removal')
        return activate(tool,'remove-signed',job,job/'install.log',keep_settings)
    return _remove(tool,job,keep_settings,notify)

def _remove(tool,job,keep_settings,notify,verified=False):
    if tool not in APP_DIRS or type(keep_settings) is not bool:raise ValueError('Invalid removal request')
    allowed,reason=removal_policy(tool)
    if not allowed:raise RuntimeError(reason)
    if not verified:
        # This endpoint reads application flags only, never instrument state.
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORTS[tool]}/api/suite/removal-state',timeout=3) as response:state=json.load(response)
        except OSError as exc:raise RuntimeError('Could not verify that controller acquisition/programming is idle; no removal performed') from exc
        if state.get('polling') or state.get('remote_control_enabled'):raise RuntimeError('Pause meter acquisition and disable remote programming before removal')
    target=HOME/APP_DIRS[tool];archive=checked_archive(tool,job.name)
    archive.parent.mkdir(parents=True,mode=0o700);archive.parent.chmod(0o700)
    broker=UNITS/'fischer-gpib.service'
    keep_runtime=(target/'venv').exists() and broker.exists() and str(target/'venv') in broker.read_text()
    prior=STATE/'retained'/(tool+'.json')
    if prior.exists():shutil.copy2(prior,job/'previous-retained.json')
    intent=job/'removal.json';atomic(intent,{'tool':tool,'keep_settings':keep_settings,'runtime_stub':keep_runtime,'stage':'prepared'})
    try:
        notify('Stopping only the selected dashboard; shared adapter stays running')
        activate(tool,'remove',job,job/'install.log')
        if tool=='supply':sync_security(target)
        if keep_runtime:
            archive.mkdir()
            for p in list(target.iterdir()):
                if p.name!='venv':p.rename(archive/p.name)
            atomic(target/'.shared-broker-runtime.json',{'tool':tool,'runtime_only':True})
        else:target.rename(archive)
        atomic(prior,{'job':job.name,'keep_settings':keep_settings})
        register(force=True)
        atomic(intent,{'tool':tool,'keep_settings':keep_settings,'runtime_stub':keep_runtime,'stage':'committing'})
        activate(tool,'commit-remove',job,job/'install.log');intent.unlink()
        return {'archive':str(archive),'keep_settings':keep_settings,'shared_runtime_retained':keep_runtime}
    except Exception:
        if json.loads(intent.read_text())['stage']!='committing':recover_remove(tool,job)
        raise

def recover_remove(tool,job):
    if UPDATER_CONFIG.exists() and os.geteuid()!=0:
        return activate(tool,'recover-signed',job,job/'install.log')
    return _recover_remove(tool,job)

def _recover_remove(tool,job):
    intent=job/'removal.json'
    if not intent.exists():return
    data=json.loads(intent.read_text())
    if data['tool']!=tool or data['stage'] not in ('prepared','committing'):raise RuntimeError('Invalid removal recovery')
    if data['stage']=='committing':
        activate(tool,'commit-remove',job,job/'install.log');intent.unlink();register(force=True);return
    target=HOME/APP_DIRS[tool];archive=checked_archive(tool,job.name)
    if archive.exists():
        if data['runtime_stub']:
            target.mkdir(exist_ok=True)
            for p in archive.iterdir():p.rename(target/p.name)
            (target/'.shared-broker-runtime.json').unlink(missing_ok=True)
        elif not target.exists():archive.rename(target)
        else:raise RuntimeError('Application path occupied; refusing to overwrite recovery data')
    activate(tool,'restore-remove',job,job/'install.log')
    retained=STATE/'retained'/(tool+'.json');previous=job/'previous-retained.json'
    if previous.exists():atomic(retained,json.loads(previous.read_text()))
    elif retained.exists():retained.unlink()
    intent.unlink();register(force=True)
