"""One-time administrator setup for the approved instrument catalog."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import time

SOURCE=Path(__file__).resolve().parent
ROOT=Path('/opt/fischer-suite-manager')
HOME=Path('/home/pi')
UNIT=Path('/etc/systemd/system/fischer-suite-manager.service')
SUDOERS=Path('/etc/sudoers.d/fischer-suite-catalog')
SYSTEMD=Path('/etc/systemd/system')
BACKUPS=Path('/var/backups/fischer-suite-manager')
WEB_SERVICES=('hp6033a','hp34401a','tektronix-controller','fischer-suite-web')
FILES=('catalog_service.py','manager_engine.py','activate.py','catalog_cli.py','deployment_profile.py')
WEB=('suite_navigation.py','navigation.js','catalog_web.py','catalog.html','tool_registration.py','suite_gateway.py')

def run(*args,check=True):return subprocess.run(list(map(str,args)),check=check,timeout=45)

def main():
    if os.geteuid()!=0:raise RuntimeError('Run this one-time setup with sudo')
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
    targets=[HOME/'instrument-suite']
    if (HOME/'hp34401a').exists():targets.append(HOME/'hp34401a')
    managed=[]
    for target in targets:
        for name in WEB:
            path=target/name;slot=backup/('web-'+str(len(managed)));managed.append((path,slot,path.exists()))
            if path.exists():shutil.copy2(path,slot)
    (backup/'manifest.json').write_text(json.dumps({'original':original,'web':[{'path':str(p),'backup':str(s),'existed':e} for p,s,e in managed]},indent=2))
    (backup/'ROLLBACK.txt').write_text('Stop fischer-suite-manager. Restore manager/service/sudoers and web files according to manifest.json, reload systemd, then restart the previously running web services. Existing instrument configuration and authentication were not modified. Do not restore a direct GPIB application alongside the broker.\n')
    try:
        ROOT.mkdir(exist_ok=True)
        for name in FILES:shutil.copy2(SOURCE/name,ROOT/name)
        shutil.copytree(SOURCE/'approved/packages',ROOT/'packages',dirs_exist_ok=True)
        shutil.copy2(SOURCE/'approved/catalog.json',ROOT/'catalog.json')
        # Root-owned code and approved packages cannot be changed by a web process.
        for folder,dirs,files in os.walk(ROOT):
            os.chown(folder,0,0);os.chmod(folder,0o755)
            for name in files:os.chown(Path(folder)/name,0,0);os.chmod(Path(folder)/name,0o644)
        commands=[f'/usr/bin/python3 -I {ROOT}/activate.py {tool} {action}' for tool in ('meter','supply','scope') for action in ('start','commit','rollback','remove','commit-remove','restore-remove')]
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
            if saved.is_dir():shutil.copytree(saved,path,dirs_exist_ok=True)
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
    print('Approved catalog enabled. Backup:',backup)

if __name__=='__main__':main()
