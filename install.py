"""Install/update the shared-adapter meter add-on on an existing supported HP host."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

SOURCE = Path(__file__).resolve().parent
HOME = Path('/home/pi')
HP = HOME/'hp6033a'
SUITE = HOME/'instrument-suite'
UNIT = Path('/etc/systemd/system/fischer-gpib.service')
DROP = Path('/etc/systemd/system/hp6033a.service.d/instrument-suite.conf')
NGINX = (Path('/etc/nginx/sites-available/hp6033a'),Path('/etc/nginx/sites-enabled/hp6033a'))
FILES = ('adapter_broker.py','adapter_worker.py','gpib_client.py','test_coordination.py','test_views.py','suite_navigation.py','navigation.js','catalog_web.py','catalog.html','tool_registration.py')

def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, timeout=120, **kwargs)

def wait_for_web():
    """A missing Unix socket during service startup is not a failed deployment."""
    for attempt in range(20):
        try:
            run('curl','-fsS','--max-time','2','--unix-socket',
                '/run/hp6033a/gunicorn.sock','http://localhost/multimeter/assets/docs/index.html',
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return
        except subprocess.CalledProcessError:
            if attempt==19:raise
            time.sleep(.25)

def stage(destination, hp=HP):
    """Check the actual HP source before changing any installed file."""
    candidate = destination/'app.py'
    shutil.copy2(hp/'app.py',candidate)
    run(hp/'venv/bin/python',SOURCE/'patch_hp.py',candidate)
    text=candidate.read_text()
    ast.parse(text)
    if 'FISCHER_SHARED_ADAPTER_V1' not in text or 'ResourceManager' in text or 'serial.Serial' in text:
        raise RuntimeError('HP app does not exclusively use the shared adapter')
    for name in FILES:
        if name.endswith('.py'):ast.parse((SOURCE/name).read_text())
    run(hp/'venv/bin/python','-m','unittest','test_coordination','test_views','test_install','-v',cwd=SOURCE)
    return candidate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true')
    g.add_argument('--apply',action='store_true')
    p.add_argument('--instruments',help='Installed tools: meter,supply and optionally scope; omitted keeps existing selection')
    args=p.parse_args()
    instruments=None
    if args.instruments:
        instruments=list(dict.fromkeys(args.instruments.split(',')))
        if not {'meter','supply'} <= set(instruments) or any(x not in ('meter','supply','scope','generator') for x in instruments):
            p.error('Integrated mode requires meter,supply; optionally add scope. For meter only use install.sh.')
        if 'scope' in instruments and not (HOME/'tektronix-controller/app.py').exists():
            p.error('Install the optional scope controller before selecting its link')
    if not (HP/'app.py').is_file() or not (HP/'venv/bin/python').is_file():
        p.error('Install the HP base controller at /home/pi/hp6033a first')
    if SOURCE==SUITE or SUITE in SOURCE.parents:
        p.error('Run from a separate extracted source directory, not the installed suite')
    if os.getuid()==0 or Path.home()!=HOME:
        p.error('Run as the supported pi account; sudo is used only for service setup')
    if (SOURCE/'config.json').exists():
        p.error('Staging source must not contain a runtime config.json')
    with tempfile.TemporaryDirectory(prefix='meter-stage-') as temporary:
        candidate=stage(Path(temporary))
        print('Checks passed; no hardware was opened and no installed files changed.')
        if args.check:return
        run('sudo','-v')
        backup=HOME/'.instrument-suite-backups'/time.strftime('%Y%m%d-%H%M%S')
        backup.mkdir(parents=True,mode=0o700)
        archive=backup/'backup.tar.gz'
        original_enabled=subprocess.run(['systemctl','is-enabled','--quiet','fischer-gpib']).returncode==0
        paths=[HP,SUITE,UNIT,DROP,*NGINX]
        existing=[str(x) for x in paths if x.exists()]
        manifest={'existing':existing,'absent':[str(x) for x in paths if not x.exists()]}
        (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
        run('sudo','tar','-czf',archive,'-C','/',*[x.lstrip('/') for x in existing])
        run('sudo','chown','pi:pi',archive)
        archive.chmod(0o600)
        (backup/'ROLLBACK.txt').write_text(
            'Run as pi. Stop both services before restoring.\n'
            'sudo systemctl stop hp6033a fischer-gpib\n'
            f'sudo tar -xzf {archive} -C /\n'
            'For paths listed absent in manifest.json, remove ONLY newly installed files/units after review.\n'
            'sudo systemctl daemon-reload\n'
            'Start fischer-gpib before hp6033a only if the original installation used that broker.\n'
            'Do not run an unpatched HP app alongside the broker.\n')
        originally_active={s:subprocess.run(['systemctl','is-active','--quiet',s]).returncode==0
                           for s in ('hp6033a','fischer-gpib','hp34401a')}
        try:
            run('sudo','systemctl','stop','hp6033a')
            subprocess.run(['sudo','systemctl','stop','fischer-gpib'],check=False,timeout=15)
            SUITE.mkdir(exist_ok=True)
            for name in FILES:shutil.copy2(SOURCE/name,SUITE/name)
            shutil.copytree(SOURCE/'hp34401a',SUITE/'hp34401a',dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.before-*'))
            cfg=SUITE/'config.json'
            tools=SUITE/'tools.json'
            if instruments is not None or not tools.exists():
                chosen=instruments or ['meter','supply']+(['scope'] if (HOME/'tektronix-controller/app.py').exists() else [])
                tools.write_text(json.dumps({'instruments':chosen},indent=2)+'\n')
            if not cfg.exists():
                config=json.loads((SOURCE/'config.example.json').read_text())
                hpconfig=json.loads((HP/'config.json').read_text())
                config['resource']=hpconfig.get('gpib_resource',config['resource'])
                cfg.write_text(json.dumps(config,indent=2)+'\n');cfg.chmod(0o600)
            shutil.copy2(candidate,HP/'app.py')
            for source in (SOURCE/'integration/templates').glob('*.html'):
                shutil.copy2(source,HP/'templates'/source.name)
            unit='''[Unit]
Description=Fischer shared GPIB adapter owner
After=network.target
[Service]
User=pi
Group=www-data
WorkingDirectory=/home/pi/instrument-suite
RuntimeDirectory=fischer-gpib
RuntimeDirectoryMode=0750
UMask=0007
ExecStart=/home/pi/hp6033a/venv/bin/python /home/pi/instrument-suite/adapter_broker.py
Restart=on-failure
RestartSec=2
TimeoutStopSec=7
KillMode=control-group
[Install]
WantedBy=multi-user.target
'''
            drop='''[Unit]
Requires=fischer-gpib.service
After=fischer-gpib.service
[Service]
ExecStart=
ExecStart=/home/pi/hp6033a/venv/bin/gunicorn --workers 1 --threads 4 --bind unix:/run/hp6033a/gunicorn.sock app:app
'''
            for path,text in ((UNIT,unit),(DROP,drop)):
                run('sudo','mkdir','-p',path.parent)
                run('sudo','tee',path,input=text,text=True,stdout=subprocess.DEVNULL)
            run('sudo','systemctl','daemon-reload')
            run('sudo','systemctl','enable','fischer-gpib')
            run('sudo','systemctl','start','fischer-gpib','hp6033a')
            wait_for_web()
            if originally_active['hp34401a']:run('sudo','systemctl','start','hp34401a')
            if HOME==Path('/home/pi'):
                from tool_registration import register_installed
                register_installed('meter')
        except Exception:
            subprocess.run(['sudo','systemctl','stop','hp6033a','fischer-gpib'],timeout=20)
            run('sudo','tar','-xzf',archive,'-C','/')
            # Remove only exact new unit files; do not delete application/configuration trees.
            if not original_enabled:
                subprocess.run(['sudo','systemctl','disable','fischer-gpib'],check=False,timeout=15)
            for path in (UNIT,DROP):
                if str(path) in manifest['absent']:run('sudo','rm','-f','--',path)
            run('sudo','systemctl','daemon-reload')
            for service in ('fischer-gpib','hp6033a','hp34401a'):
                if originally_active[service]:run('sudo','systemctl','start',service)
            print(f'Activation failed; prior files/services restored. Retained backup: {backup}')
            raise
        print(f'Installed. Backup and rollback instructions: {backup}')
        print('Existing config bytes retained. New configs have hardware disabled/read-only. Follow INSTALL.md.')

if __name__=='__main__':main()
