"""One-time administrator setup for the approved instrument catalog."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import time
import socket
import sys

SOURCE=Path(__file__).resolve().parent
ROOT=Path('/opt/fischer-suite-manager')
HOME=Path('/home/pi')
UNIT=Path('/etc/systemd/system/fischer-suite-manager.service')
SUDOERS=Path('/etc/sudoers.d/fischer-suite-catalog')
SYSTEMD=Path('/etc/systemd/system')
BACKUPS=Path('/var/backups/fischer-suite-manager')
UPDATER_CONFIG=Path('/etc/fischer-suite-updater.json')
MANAGER_SOCKET=Path('/run/fischer-suite-manager/install.sock')
WEB_SERVICES=('hp6033a','hp34401a','tektronix-controller','fischer-suite-web')
FILES=('catalog_service.py','manager_engine.py','activate.py','catalog_cli.py','deployment_profile.py')
WEB=('suite_navigation.py','navigation.js','catalog_web.py','catalog.html','tool_registration.py','suite_gateway.py')

def run(*args,check=True):return subprocess.run(list(map(str,args)),check=check,timeout=45)

def main(signed_only=False):
    if os.geteuid()!=0:raise RuntimeError('Run this one-time setup with sudo')
    if signed_only:
        if not UPDATER_CONFIG.is_file():raise RuntimeError('Signed catalog setup requires an enrolled updater')
        if MANAGER_SOCKET.exists():
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.settimeout(4);client.connect(str(MANAGER_SOCKET))
                client.sendall(b'{"action":"status"}\n')
                reply=json.loads(client.makefile('rb').readline(65537))
            if not reply.get('ok'):raise RuntimeError('Cannot verify catalog is idle')
            job=reply['result'].get('job')
            if job and job.get('state') in ('queued','running'):raise RuntimeError('Wait for the current catalog operation to finish')
        metadata={'version':'signed','tools':{
            'meter':{'name':'HP 34401A Multimeter','description':'Signed HP multimeter controller'},
            'supply':{'name':'HP 6033A Supply','description':'Signed HP power supply controller'},
            'scope':{'name':'Tektronix Ethernet','description':'Signed oscilloscope controller'}}}
        for name in FILES:compile((SOURCE/name).read_bytes(),name,'exec')
        active_web={};active_user_scope=False
    else:
        metadata=json.loads((SOURCE/'approved/catalog.json').read_text())
        if set(metadata['tools'])!={'meter','supply','scope'}:raise RuntimeError('Unapproved catalog entries')
        for key,item in metadata['tools'].items():
            if hashlib.sha256((SOURCE/'approved/packages'/(key+'.zip')).read_bytes()).hexdigest()!=item['sha256']:
                raise RuntimeError('Package checksum mismatch: '+key)
        active_web={name:subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0 for name in WEB_SERVICES}
        uid=pwd.getpwnam('pi').pw_uid
        user=['runuser','-u','pi','--','env','XDG_RUNTIME_DIR=/run/user/'+str(uid),'systemctl','--user']
        active_user_scope=subprocess.run([*user,'is-active','--quiet','tektronix-controller']).returncode==0
    backup=BACKUPS/time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True,mode=0o700)
    original={}
    for name,path in [('manager',ROOT),('service',UNIT),('sudoers',SUDOERS)]:
        original[name]=path.exists()
        if path.is_dir():shutil.copytree(path,backup/name)
        elif path.exists():shutil.copy2(path,backup/name)
    targets=[] if signed_only else [HOME/'instrument-suite']
    if not signed_only and (HOME/'hp34401a').exists():targets.append(HOME/'hp34401a')
    managed=[]
    for target in targets:
        for name in WEB:
            path=target/name;slot=backup/('web-'+str(len(managed)));managed.append((path,slot,path.exists()))
            if path.exists():shutil.copy2(path,slot)
    (backup/'manifest.json').write_text(json.dumps({'original':original,'web':[{'path':str(p),'backup':str(s),'existed':e} for p,s,e in managed]},indent=2))
    (backup/'ROLLBACK.txt').write_text('Stop fischer-suite-manager. Restore manager/service/sudoers and web files according to manifest.json, reload systemd, then restart the previously running web services. Existing instrument configuration and authentication were not modified. Do not restore a direct GPIB application alongside the broker.\n')
    try:
        if signed_only and original['service']:run('systemctl','stop','fischer-suite-manager')
        ROOT.mkdir(exist_ok=True)
        for name in FILES:shutil.copy2(SOURCE/name,ROOT/name)
        if not signed_only:
            shutil.copytree(SOURCE/'approved/packages',ROOT/'packages',dirs_exist_ok=True)
            shutil.copy2(SOURCE/'approved/catalog.json',ROOT/'catalog.json')
        elif not (ROOT/'catalog.json').exists():
            (ROOT/'catalog.json').write_text(json.dumps(metadata,indent=2)+'\n')
        # Root-owned code and approved packages cannot be changed by a web process.
        for folder,dirs,files in os.walk(ROOT):
            os.chown(folder,0,0);os.chmod(folder,0o755)
            for name in files:os.chown(Path(folder)/name,0,0);os.chmod(Path(folder)/name,0o644)
        commands=[f'/usr/bin/python3 -I {ROOT}/activate.py {tool} {action}' for tool in ('meter','supply','scope') for action in ('start','commit','rollback','remove','commit-remove','restore-remove','remove-signed','recover-signed','install-signed')]
        temporary=backup/'sudoers.new';temporary.write_text('pi ALL=(root) NOPASSWD: '+', '.join(commands)+'\n');temporary.chmod(0o440)
        run('visudo','-cf',temporary);shutil.copy2(temporary,SUDOERS);SUDOERS.chmod(0o440)
        for name in ('hp34401a','hp6033a','tektronix-controller','fischer-gpib'):
            path=SYSTEMD/(name+'.service')
            if path.is_file() and not path.is_symlink():path.chmod(0o644)
        uid=pwd.getpwnam('pi').pw_uid;gid=pwd.getpwnam('pi').pw_gid
        for target in targets:
            target.mkdir(exist_ok=True);os.chown(target,uid,gid)
            for name in WEB:
                path=target/name;shutil.copy2(SOURCE/name,path);os.chown(path,uid,gid);path.chmod(0o644)
        UNIT.write_text(f'''[Unit]
Description=Fischer approved instrument installation manager
After=network.target
[Service]
User=pi
Group=www-data
RuntimeDirectory=fischer-suite-manager
RuntimeDirectoryMode=0750
UMask=0007
ExecStart=/usr/bin/python3 -I {ROOT}/catalog_service.py
Restart=on-failure
RestartSec=2
TimeoutStopSec=10
KillMode=control-group
[Install]
WantedBy=multi-user.target
''')
        run('systemctl','daemon-reload');run('systemctl','enable','--now','fischer-suite-manager');run('systemctl','restart','fischer-suite-manager')
        for service,was_running in active_web.items():
            if was_running:run('systemctl','restart',service)
        if active_user_scope:run(*user,'restart','tektronix-controller')
    except Exception:
        run('systemctl','stop','fischer-suite-manager',check=False)
        for name,path in [('manager',ROOT),('service',UNIT),('sudoers',SUDOERS)]:
            saved=backup/name
            if saved.is_dir():
                if signed_only and name=='manager':
                    for leaf in (*FILES,'catalog.json'):
                        target=path/leaf
                        if not (saved/leaf).exists() and (target.is_file() or target.is_symlink()):target.unlink()
                shutil.copytree(saved,path,dirs_exist_ok=True)
            elif signed_only and name=='manager' and not original['manager']:
                for leaf in (*FILES,'catalog.json'):
                    target=path/leaf
                    if target.is_file() or target.is_symlink():target.unlink()
                if path.is_dir() and not any(path.iterdir()):path.rmdir()
            elif saved.exists():shutil.copy2(saved,path)
            elif path.is_file():path.unlink()
        for path,slot,existed in managed:
            if existed:shutil.copy2(slot,path)
            elif path.exists():path.unlink()
        run('systemctl','daemon-reload')
        if original['service']:run('systemctl','start','fischer-suite-manager',check=False)
        for service,was_running in active_web.items():
            if was_running:run('systemctl','restart',service,check=False)
        if active_user_scope:run(*user,'restart','tektronix-controller',check=False)
        raise
    print('Signed catalog enabled. Backup:' if signed_only else 'Approved catalog enabled. Backup:',backup)

if __name__=='__main__':
    if sys.argv[1:] not in ([],['--signed-only']):raise SystemExit('Use --signed-only for an enrolled signed installation')
    main(signed_only=sys.argv[1:]==['--signed-only'])
