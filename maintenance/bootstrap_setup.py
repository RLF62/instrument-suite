"""Executed only after bootstrap verifies the suite archive's offline signature."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from .engine import Engine
from .linux import LinuxHost
from .security import atomic_json, MaintenanceError

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest-url',required=True);p.add_argument('--key',type=Path,required=True)
    p.add_argument('--instruments');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--web-updates',choices=('disabled','trusted-lan','dashboard'))
    p.add_argument('--trusted-lan',action='append',default=[]);p.add_argument('--update-origin',action='append',default=[])
    args=p.parse_args(argv)
    from .cli import selection,menu
    selected=selection(args.instruments) if args.instruments else menu()
    root=Path('/var/lib/fischer-suite-updater');host=LinuxHost(root)
    # Verify the complete schema and signature a second time with the shared engine.
    engine=Engine(root,host);manifest=engine.release(args.manifest_url,args.key)
    if args.dry_run:
        print(engine.describe(manifest,selected));return 0
    if os.geteuid()!=0:raise MaintenanceError('Root installation required')
    cfg=Path('/etc/fischer-suite-updater.json')
    if cfg.exists():raise MaintenanceError('Existing updater preserved; use instrument-suite install')
    # Validate trusted-LAN settings before any OS packages or services change.
    if args.web_updates == 'trusted-lan':
        from .web_policy import disabled, fresh_lan_network, fresh_lan_origin, validate
        if not args.trusted_lan or not args.update_origin:
            addresses=subprocess.check_output(['hostname','-I'],text=True,timeout=10).split()
            if not args.trusted_lan:
                interfaces=json.loads(subprocess.check_output(['ip','-j','-4','addr','show','scope','global'],text=True,timeout=10))
                args.trusted_lan=[fresh_lan_network(interfaces,addresses)]
                print('Trusted LAN: '+args.trusted_lan[0],flush=True)
            if not args.update_origin:
                args.update_origin=[fresh_lan_origin(args.trusted_lan,addresses)]
                print('Web-update origin: '+args.update_origin[0],flush=True)
        policy=disabled()
        policy.update(mode='trusted-lan',origins=args.update_origin,trusted_lans=args.trusted_lan,
                      trusted_proxies=['127.0.0.1/32','::1/128'])
        validate(policy)
    print('Preparing Raspberry Pi OS dependencies...',flush=True)
    # No controller is stopped or replaced while preparing OS dependencies.
    subprocess.run(['apt-get','update'],check=True,timeout=300)
    subprocess.run(['apt-get','install','-y','python3-venv','python3-pip','curl','openssl','nginx','sudo','libusb-1.0-0'],check=True,timeout=600)
    print('OS packages ready. Checking space for signed controller packages...',flush=True)
    host.preflight(sum(manifest['components'][n]['size'] for n in ['suite',*selected]))
    # Verify every selected, signed wheel lock before enrolling the updater.
    # A Bookworm/Python 3.11 hash failure must leave existing controllers untouched.
    print('Checking signed Python wheels for this OS before enrollment...',flush=True)
    with tempfile.TemporaryDirectory(prefix='fischer-wheel-preflight-') as scratch:
        work=Path(scratch)
        stages=engine.prepare(manifest,['suite',*selected],work)
        for name,stage in stages.items():
            wheels=work/(name+'-wheels')
            result=subprocess.run([sys.executable,'-m','pip','download',
                '--only-binary=:all:','--require-hashes','--dest',str(wheels),
                '-r',str(stage/'requirements.lock')],timeout=600)
            if result.returncode:
                raise MaintenanceError(name+': signed dependency wheels unavailable for this OS/Python; no updater or controller was enrolled')
    print('Signed Python wheels verified for this OS.',flush=True)
    # Enroll only the updater. Existing instruments remain untouched if apply blocks.
    source=Path(__file__).resolve().parents[1]
    engine_root=Path('/opt/fischer-suite-updater');engine_root.mkdir(mode=0o755,exist_ok=True)
    destination=engine_root/'engine-v1'
    if destination.exists():raise MaintenanceError('Existing engine preserved; attended recovery required')
    destination.mkdir(mode=0o755)
    shutil.copytree(source/'maintenance',destination/'maintenance',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for folder,dirs,files in os.walk(destination):
        os.chmod(folder,0o755)
        for name in files:os.chmod(Path(folder)/name,0o644)
    key=engine_root/'release-signing.pub';shutil.copy2(args.key,key);key.chmod(0o644)
    runner=destination/'runner.py';runner.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parent))\nfrom maintenance.cli import main\nraise SystemExit(main())\n');runner.chmod(0o644)
    command=Path('/usr/local/bin/instrument-suite')
    if command.exists():raise MaintenanceError('Existing instrument-suite command preserved; attended recovery required')
    (engine_root/'current').symlink_to(destination,target_is_directory=True)
    command.write_text('#!/bin/sh\nexec /usr/bin/python3 -I /opt/fischer-suite-updater/current/runner.py "$@"\n');command.chmod(0o755)
    atomic_json(cfg,{'schema':1,'key':str(key)})
    print('Installing verified controllers and Python environments; this may take several minutes...',flush=True)
    result=engine.apply(manifest,selected)
    # This source was authenticated by bootstrap and again by the shared engine.
    # Install only the catalog helper; preserve all controller/gateway services.
    print('Controller services passed health checks. Configuring the suite catalog...',flush=True)
    host.run(['/usr/bin/python3','-I',str(source/'deploy_manager.py'),'--signed-only'],timeout=180)
    from .web_policy import installation_choice
    print('Configuring web updates...',flush=True)
    installation_choice(args.web_updates,args.trusted_lan,args.update_origin)
    print(result)
    print('Dashboard: http://YOUR_PI_ADDRESS:8080/')
    print('Installed:',', '.join(selected))
    print('Status: sudo instrument-suite status')
    print('Logs: sudo journalctl -u fischer-suite-dashboard -n 60 --no-pager')
    print('Recovery: sudo instrument-suite rollback')
    print('For USB permissions, unplug/replug the GPIB adapter if required. Instrument connections begin disabled/unconfigured.')
    print('GPIB connection setup: https://github.com/RLF62/instrument-suite/blob/main/GPIB_SETUP.md')
    return 0
