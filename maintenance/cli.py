"""Fixed-command interface for signed Fischer releases."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
from .engine import Engine
from .linux import LinuxHost
from .security import MaintenanceError

ROOT = Path('/var/lib/fischer-suite-updater')
CONFIG = Path('/etc/fischer-suite-updater.json')
ACTIONS = ('install','update','status','check','backup','rollback','configure-web-updates','audit')

def config():
    if not CONFIG.is_file() or CONFIG.is_symlink(): raise MaintenanceError('Updater is not enrolled. Use the signed bootstrap or attended enrollment guide')
    st = CONFIG.stat()
    if st.st_uid != 0 or st.st_mode & 0o022: raise MaintenanceError('Updater configuration must be root-owned and protected')
    value = json.loads(CONFIG.read_text())
    if set(value) != {'schema','key'} or value['schema'] != 1: raise MaintenanceError('Invalid updater configuration')
    key = Path(value['key'])
    if not key.is_file() or key.is_symlink() or key.stat().st_uid != 0 or key.stat().st_mode & 0o022:
        raise MaintenanceError('Release trust key must be root-owned and protected')
    return value

def latest_url():
    request = urllib.request.Request('https://api.github.com/repos/RLF62/instrument-suite/releases/latest',
                                    headers={'User-Agent':'Fischer-Instrument-Suite/1','Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(1024*1024+1)
        if len(raw)>1024*1024:raise MaintenanceError('Release discovery response is too large')
        release = json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code==404:raise MaintenanceError('No approved signed suite release has been published yet') from None
        raise MaintenanceError('GitHub release discovery failed; retry later') from None
    if release.get('draft') or release.get('prerelease'):raise MaintenanceError('Only approved stable releases may be installed')
    urls={x['name']:x['browser_download_url'] for x in release.get('assets',[])}
    if 'manifest.json' not in urls or 'manifest.json.sig' not in urls:
        raise MaintenanceError('Latest release has no signed updater manifest; no installation performed')
    if urls['manifest.json.sig']!=urls['manifest.json']+'.sig':raise MaintenanceError('Unexpected manifest signature asset')
    return urls['manifest.json']

def selection(text):
    names=list(dict.fromkeys(text.split(',')))
    if not names or any(x not in ('meter','supply','scope') for x in names):
        raise argparse.ArgumentTypeError('Choose meter,supply,scope, separated by commas')
    return names

def menu():
    if not sys.stdin.isatty():raise MaintenanceError('Choose --instruments meter,supply,scope when input is not interactive')
    print('Choose instruments (connections begin disabled/unconfigured):\n  1 HP 34401A multimeter\n  2 HP 6033A supply\n  3 Tektronix scope')
    answer=input('Numbers separated by commas: ').strip().split(',')
    mapping={'1':'meter','2':'supply','3':'scope'}
    if not answer or any(x.strip() not in mapping for x in answer):raise MaintenanceError('Choose 1, 2 and/or 3')
    return list(dict.fromkeys(mapping[x.strip()] for x in answer))

def execute(action, instruments=None, dry_run=False, release_url=None):
    if action not in ACTIONS:raise MaintenanceError('Unsupported maintenance action')
    host=LinuxHost(ROOT);engine=Engine(ROOT,host)
    if action=='audit':
        return host.audit(engine.state(),engine.pending.exists())
    if action=='status':
        gateway=host.https_gateway()
        dashboard_service=host.service('suite')
        state=engine.state()
        return {'installed':state['components'],'discovered':sorted(host.discover()),
                'services':{n:('active' if host.active(n) else 'inactive') for n in host.discover()},
                'recovery_pending':engine.pending.exists(),
                'local_candidate':(ROOT/'candidate-mode.json').exists(),
                'dashboard':('https://RASPBERRY_PI_ADDRESS/' if gateway else 'http://RASPBERRY_PI_ADDRESS:8080/'),
                'troubleshooting':['sudo instrument-suite status','sudo instrument-suite rollback','sudo journalctl -u '+dashboard_service+' -n 60 --no-pager']}
    if os.geteuid()!=0:raise MaintenanceError('Run sudo instrument-suite '+action)
    if action=='backup':return engine.backup(dry_run)
    if action=='rollback':return engine.rollback(dry_run)
    cfg=config();manifest=engine.release(release_url or latest_url(),cfg['key'])
    if action=='check':return engine.describe(manifest,instruments)
    if action=='install' and instruments is None:instruments=menu()
    report=engine.describe(manifest,instruments)
    print('Installed:',', '.join(n+' '+v['version'] for n,v in report['installed'].items()) or 'not enrolled',flush=True)
    print('Approved release:',manifest['release'],'; changed components:',', '.join(report['changes']) or 'none',flush=True)
    return engine.apply(manifest,instruments,dry_run)

def main(argv=None):
    parser=argparse.ArgumentParser(description='Install and maintain signed Fischer Instrument Suite releases without programming instruments.')
    parser.add_argument('action',choices=ACTIONS)
    parser.add_argument('--instruments',type=selection,help='Install/add selected controllers, e.g. meter,scope')
    parser.add_argument('--dry-run',action='store_true',help='Report plan without downloading controller packages, installing dependencies or changing services')
    parser.add_argument('--release-url',help='Explicit immutable signed manifest URL (administrator CLI only)')
    parser.add_argument('--mode',choices=('disabled','trusted-lan','dashboard'),help='Explicit web-update authorization policy')
    parser.add_argument('--trusted-lan',action='append',default=[],help='Explicit private LAN CIDR; repeat as needed')
    parser.add_argument('--origin',action='append',default=[],help='Exact allowed dashboard origin')
    parser.add_argument('--dashboard-credentials',help='Existing dashboard credential file; never a new password')
    parser.add_argument('--replace-policy',action='store_true',help='Explicitly replace an existing web-update policy')
    args=parser.parse_args(argv)
    if args.instruments and args.action not in ('install','check'):parser.error('--instruments is supported by install and check')
    try:
        if args.action=='configure-web-updates':
            if not args.mode:parser.error('configure-web-updates requires --mode')
            from .web_policy import configure,install_helper,read_policy
            if args.dry_run:
                from .web_policy import disabled,validate
                value=disabled();value.update(mode=args.mode,origins=args.origin,trusted_lans=args.trusted_lan,trusted_proxies=['127.0.0.1/32','::1/128'],credential_file=args.dashboard_credentials)
                validate(value);print(json.dumps({'dry_run':True,'proposed_policy':value,'existing_policy_preserved':not args.replace_policy},indent=2));return 0
            result=configure(args.mode,args.origin,args.trusted_lan,args.dashboard_credentials,args.replace_policy)
            if read_policy()['mode']!='disabled':install_helper()
            print(json.dumps(result,indent=2));return 0
        if args.mode or args.trusted_lan or args.origin or args.dashboard_credentials or args.replace_policy:parser.error('Web policy arguments require configure-web-updates')
        result=execute(args.action,args.instruments,args.dry_run,args.release_url)
        print(json.dumps(result,indent=2));return 0
    except (MaintenanceError,OSError,ValueError,KeyError,TimeoutError) as exc:
        print('Instrument Suite: '+str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
