"""Install a meter-only host, reusing an existing broker when present."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

SOURCE=Path(__file__).resolve().parent
HOME=Path.home()
APP=HOME/'hp34401a'
SUITE=HOME/'instrument-suite'
WEB_UNIT=Path('/etc/systemd/system/hp34401a.service')
BROKER_UNIT=Path('/etc/systemd/system/fischer-gpib.service')
UDEV_RULE=Path('/etc/udev/rules.d/70-fischer-gpib.rules')
NAMES=('standalone_app.py','suite_navigation.py','navigation.js','gpib_client.py','requirements.txt','catalog_web.py','catalog.html','tool_registration.py')

def run(*args,**kw):
    return subprocess.run(list(map(str,args)),check=True,timeout=180,**kw)

def selection(text):
    result=list(dict.fromkeys(text.split(',')))
    if 'meter' not in result or any(x not in ('meter','supply','scope','generator') for x in result):
        raise argparse.ArgumentTypeError('Choose meter, optionally supply and/or scope')
    return result

def preflight(instruments):
    if HOME!=Path('/home/pi') or os.getuid()==0:
        raise RuntimeError('Use the supported pi account on Raspberry Pi OS, not root')
    if SOURCE==APP or APP in SOURCE.parents:
        raise RuntimeError('Extract source into a separate staging directory')
    if 'supply' in instruments and not (HOME/'hp6033a/app.py').exists():
        raise RuntimeError('Supply selected but its controller is not installed; install it first')
    if 'scope' in instruments and not (HOME/'tektronix-controller/app.py').exists():
        raise RuntimeError('Scope selected but its controller is not installed; install it first')
    hp=HOME/'hp6033a/app.py'
    if hp.exists() and 'FISCHER_SHARED_ADAPTER_V1' not in hp.read_text():
        raise RuntimeError('Existing supply app opens the adapter directly; integrate the shared broker first')
    if BROKER_UNIT.exists():
        if str(SUITE/'adapter_broker.py') not in BROKER_UNIT.read_text():
            raise RuntimeError('Unrecognized broker service; refusing a competing adapter owner')
        if not (SUITE/'config.json').exists():
            raise RuntimeError('Existing broker configuration is missing')
    for name in (*NAMES,'adapter_broker.py','adapter_worker.py'):
        if name.endswith('.py'):ast.parse((SOURCE/name).read_text())

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true');g.add_argument('--apply',action='store_true')
    p.add_argument('--instruments',type=selection,default=['meter'])
    p.add_argument('--listen',choices=('127.0.0.1','0.0.0.0'),default='127.0.0.1')
    p.add_argument('--port',type=int,default=8082)
    args=p.parse_args(argv)
    if not 1024<=args.port<=65535:p.error('Choose an unprivileged port from 1024 to 65535')
    preflight(args.instruments)
    print('Selected tools:',', '.join(args.instruments))
    print('Meter HTTP listener:',args.listen,args.port)
    print('Local HTTP mode has no login or encryption. Do not expose it to the internet. Use a trusted LAN or a secured reverse proxy.')
    if args.check:
        print('Preflight passed. No files/services/hardware changed.');return
    run('sudo','-n','true')
    fresh_broker=not BROKER_UNIT.exists()
    shared_navigation=[SUITE/'suite_navigation.py',SUITE/'navigation.js',SUITE/'tools.json']
    tracked=[APP,WEB_UNIT]+([SUITE,BROKER_UNIT,UDEV_RULE] if fresh_broker else shared_navigation)
    backup=HOME/'.instrument-suite-backups'/('standalone-'+time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True,mode=0o700)
    existing=[x for x in tracked if x.exists()]
    archive=backup/'backup.tar.gz'
    if existing:run('sudo','tar','-czf',archive,'-C','/',*[str(x).lstrip('/') for x in existing])
    if archive.exists():run('sudo','chmod','600',archive)
    (backup/'manifest.json').write_text(json.dumps({'existing':list(map(str,existing)),'absent':[str(x) for x in tracked if x not in existing]},indent=2))
    active=subprocess.run(['systemctl','is-active','--quiet','hp34401a']).returncode==0
    enabled=subprocess.run(['systemctl','is-enabled','--quiet','hp34401a']).returncode==0
    (backup/'ROLLBACK.txt').write_text('Stop hp34401a before restoring backup.tar.gz at /. Reload systemd and restore the previous enabled/active state. If this was a fresh broker install, stop/disable fischer-gpib first and remove only its newly created unit. Never run two adapter owners. Configuration and credentials in existing installations were not modified.\n')
    try:
        APP.mkdir(exist_ok=True)
        for name in NAMES:shutil.copy2(SOURCE/name,APP/name)
        shutil.copytree(SOURCE/'hp34401a',APP/'hp34401a',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        tools=APP/'tools.json';tools.write_text(json.dumps({'instruments':args.instruments},indent=2)+'\n')
        python=APP/'venv/bin/python'
        if not python.exists():run('python3','-m','venv',APP/'venv')
        run(python,'-m','pip','install','-r',APP/'requirements.txt')
        run(python,'-m','unittest','test_standalone','test_standalone_install','test_views','test_coordination','-v',cwd=SOURCE)
        SUITE.mkdir(exist_ok=True)
        for name in ('suite_navigation.py','navigation.js'):
            if not (SUITE/name).exists():shutil.copy2(SOURCE/name,SUITE/name)
        if not (SUITE/'tools.json').exists():
            (SUITE/'tools.json').write_text(json.dumps({'instruments':args.instruments},indent=2)+'\n')
        if fresh_broker:
            rule='SUBSYSTEM=="usb", ATTR{idVendor}=="03eb", ATTR{idProduct}=="2065", MODE="0660", GROUP="www-data"\n'
            run('sudo','tee',UDEV_RULE,input=rule,text=True,stdout=subprocess.DEVNULL)
            run('sudo','udevadm','control','--reload-rules')
            run('sudo','udevadm','trigger','--action=change','--subsystem-match=usb','--attr-match=idVendor=03eb','--attr-match=idProduct=2065')
            SUITE.mkdir(exist_ok=True)
            for name in ('adapter_broker.py','adapter_worker.py','gpib_client.py'):shutil.copy2(SOURCE/name,SUITE/name)
            cfg=SUITE/'config.json'
            if not cfg.exists():shutil.copy2(SOURCE/'config.example.json',cfg);cfg.chmod(0o600)
            broker=f'''[Unit]
Description=Fischer shared GPIB adapter owner
After=network.target
[Service]
User=pi
Group=www-data
WorkingDirectory={SUITE}
RuntimeDirectory=fischer-gpib
RuntimeDirectoryMode=0750
UMask=0007
ExecStart={python} {SUITE}/adapter_broker.py
Restart=on-failure
TimeoutStopSec=7
KillMode=control-group
[Install]
WantedBy=multi-user.target
'''
            run('sudo','tee',BROKER_UNIT,input=broker,text=True,stdout=subprocess.DEVNULL)
        web=f'''[Unit]
Description=HP 34401A standalone web controller
Requires=fischer-gpib.service
After=network.target fischer-gpib.service
[Service]
User=pi
Group=www-data
WorkingDirectory={APP}
Environment=FISCHER_SUITE_TOOLS={tools}
Environment=FISCHER_GPIB_SOCKET=/run/fischer-gpib/adapter.sock
ExecStart={APP}/venv/bin/gunicorn --workers 1 --threads 4 --bind {args.listen}:{args.port} standalone_app:app
Restart=on-failure
TimeoutStopSec=7
[Install]
WantedBy=multi-user.target
'''
        run('sudo','tee',WEB_UNIT,input=web,text=True,stdout=subprocess.DEVNULL)
        run('sudo','systemctl','daemon-reload')
        if fresh_broker:run('sudo','systemctl','enable','--now','fischer-gpib')
        run('sudo','systemctl','restart','hp34401a')
        for attempt in range(30):
            try:
                run('curl','-fsS','--max-time','2',f'http://127.0.0.1:{args.port}/api/multimeter/status',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);break
            except subprocess.CalledProcessError:
                if attempt==29:raise
                time.sleep(.25)
        run('sudo','systemctl','enable','hp34401a')
        if HOME==Path('/home/pi') and (SOURCE/'approved/catalog.json').exists():
            run('sudo','-n','/usr/bin/python3','-I',SOURCE/'deploy_manager.py')
        if HOME==Path('/home/pi'):
            from tool_registration import register_installed
            register_installed('meter')
    except Exception:
        subprocess.run(['sudo','systemctl','stop','hp34401a'],timeout=15)
        if fresh_broker:subprocess.run(['sudo','systemctl','disable','--now','fischer-gpib'],timeout=15)
        if archive.exists():run('sudo','tar','-xzf',archive,'-C','/')
        if not fresh_broker:
            for path in shared_navigation:
                if path not in existing and path.exists():path.unlink()
        for unit in [WEB_UNIT]+([BROKER_UNIT,UDEV_RULE] if fresh_broker else []):
            if unit not in existing:run('sudo','rm','-f','--',unit)
        if fresh_broker:run('sudo','udevadm','control','--reload-rules')
        run('sudo','systemctl','daemon-reload')
        if not enabled:subprocess.run(['sudo','systemctl','disable','hp34401a'],timeout=15)
        if active:run('sudo','systemctl','start','hp34401a')
        print('Activation failed; previous service/files restored. Backup:',backup);raise
    print('Installed meter-only web host. Backup:',backup)
    print('Open http://CONTROLLER_HOST:'+str(args.port)+'/ . New hardware configs remain disabled; follow STANDALONE.md.')

if __name__=='__main__':main()
