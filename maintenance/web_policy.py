"""Opt-in web maintenance policy; terminal maintenance never uses this policy."""
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from .security import MaintenanceError,atomic_json

POLICY=Path('/etc/fischer-suite-updater-web.json')
CREDENTIAL_FILES={'/home/pi/hp6033a/.control_htpasswd','/etc/nginx/hp6033a.htpasswd',
                  '/home/pi/instrument-suite/security/.control_htpasswd'}
RFC1918=[ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','fc00::/7')]

def disabled():return {'schema':1,'mode':'disabled','origins':[],'trusted_lans':[],'trusted_proxies':[],'credential_file':None}

def validate(value):
    if not isinstance(value,dict) or set(value)!=set(disabled()) or value['schema']!=1 or value['mode'] not in ('disabled','trusted-lan','dashboard'):
        raise MaintenanceError('Invalid web-update policy; access is disabled')
    for key in ('origins','trusted_lans','trusted_proxies'):
        if not isinstance(value[key],list) or any(not isinstance(s,str) for s in value[key]):raise MaintenanceError('Invalid web-update policy list')
    for origin in value['origins']:
        p=urlsplit(origin)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.path or p.query or p.fragment or p.netloc!=p.netloc.lower():
            raise MaintenanceError('Configure exact web-update origins such as http://192.168.1.108:8080')
        if value['mode']=='trusted-lan' and p.scheme!='http':raise MaintenanceError('Password-free mode is explicitly for trusted-LAN HTTP installations')
        if value['mode']=='dashboard' and p.scheme!='https':raise MaintenanceError('Dashboard credential reuse requires HTTPS')
    for text in value['trusted_lans']:
        try:n=ipaddress.ip_network(text,strict=True)
        except ValueError:raise MaintenanceError('Enter a specific trusted LAN CIDR') from None
        if not any(n.version==private.version and n.subnet_of(private) for private in RFC1918):raise MaintenanceError('Password-free updates require explicit RFC1918/ULA LAN ranges, not public/default routes')
    for text in value['trusted_proxies']:
        try:n=ipaddress.ip_network(text,strict=True)
        except ValueError:raise MaintenanceError('Invalid trusted proxy') from None
        if not n.is_loopback:raise MaintenanceError('Only explicitly configured local reverse proxies are supported')
    if value['mode']!='disabled' and not value['origins']:raise MaintenanceError('Configure at least one exact allowed origin')
    if value['mode']=='trusted-lan' and not value['trusted_lans']:raise MaintenanceError('Configure the trusted LAN before enabling password-free web updates')
    if value['mode']=='dashboard' and value['credential_file'] not in CREDENTIAL_FILES:raise MaintenanceError('Reuse a known existing dashboard credential file')
    if value['mode']!='dashboard' and value['credential_file'] is not None:raise MaintenanceError('A separate update credential is not supported')
    return value

def read_policy(path=POLICY):
    try:st=path.stat()
    except FileNotFoundError:return disabled()
    if path.is_symlink() or st.st_uid!=0 or st.st_mode&0o022:raise MaintenanceError('Web-update policy must be root-owned and protected')
    try:return validate(json.loads(path.read_text()))
    except (OSError,ValueError,KeyError,TypeError):raise MaintenanceError('Web-update policy is unreadable; access is disabled') from None

def configure(mode,origins,networks,credential_file=None,replace=False,path=POLICY):
    if os.geteuid()!=0:raise MaintenanceError('Linux sudo authorization is required to configure web updates')
    if path.exists() and not replace:
        read_policy(path);return {'preserved_existing_policy':True}
    value=disabled();value.update(mode=mode,origins=origins,trusted_lans=networks,
                                  trusted_proxies=['127.0.0.1/32','::1/128'],credential_file=credential_file)
    validate(value)
    if mode=='dashboard' and not Path(credential_file).is_file():raise MaintenanceError('Existing dashboard credentials were not found; no new password is requested')
    # Choosing HTTP mode must not create an unauthenticated side door on a known
    # HTTPS gateway installation. That deployment requires credential reuse.
    if mode=='trusted-lan' and Path('/etc/fischer-suite/profile.json').exists():
        raise MaintenanceError('Existing HTTPS gateway policy preserved. Use dashboard credential reuse for web updates')
    atomic_json(path,value)
    import grp
    os.chown(path,0,grp.getgrnam('www-data').gr_gid);path.chmod(0o640)
    return {'web_updates':mode,'origins':origins,'trusted_lans':networks}

def address(value):
    ip=ipaddress.ip_address(value)
    return ip.ipv4_mapped if getattr(ip,'ipv4_mapped',None) else ip

def within(ip,networks):
    return any(ip.version==n.version and ip in n for n in map(ipaddress.ip_network,networks))

def authorize(request,policy):
    if policy['mode']=='disabled':raise PermissionError('Dashboard updates are disabled; use sudo instrument-suite update or explicitly configure web updates')
    try:
        peer=address(request.remote_addr)
        scheme=request.scheme
        if within(peer,policy['trusted_proxies']):
            real=request.headers.get('X-Real-IP','')
            if not real or ',' in real:raise ValueError('Missing verified client address')
            peer=address(real)
            forwarded=request.headers.get('X-Forwarded-Proto','')
            if forwarded not in ('http','https'):raise ValueError('Missing verified proxy scheme')
            scheme=forwarded
        origin=scheme+'://'+request.host.lower()
        if origin not in policy['origins']:raise ValueError('Unapproved update host/origin')
        supplied=request.headers.get('Origin')
        if supplied and supplied!=origin:raise ValueError('Request origin did not match the dashboard')
        if request.method not in ('GET','HEAD') and supplied!=origin:raise ValueError('Same-origin request required')
        if request.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):raise ValueError('Cross-site update request rejected')
        if policy['mode']=='trusted-lan' and (scheme!='http' or not within(peer,policy['trusted_lans'])):raise ValueError('Client is outside the explicitly configured trusted LAN')
        if policy['mode']=='dashboard':
            if scheme!='https':raise ValueError('HTTPS is required for dashboard credential reuse')
            auth=request.authorization
            if auth is None or auth.type.lower()!='basic' or not verify_dashboard(auth.username,auth.password,policy['credential_file']):raise PermissionError('Use the existing dashboard username and password')
        return origin
    except (ValueError,TypeError):raise PermissionError('Web update access denied: verify trusted LAN, origin and reverse-proxy settings') from None

def verify_dashboard(username,password,path):
    if not username or not password or len(password.encode())>72:return False
    try:
        import bcrypt
        for line in Path(path).read_text().splitlines():
            user,separator,digest=line.partition(':')
            if separator and hmac.compare_digest(user,username) and digest.startswith(('$2a$','$2b$','$2y$')):
                return bcrypt.checkpw(password.encode(),digest.encode())
    except (OSError,ValueError,TypeError):pass
    return False

def csrf_valid(cookie,header):
    return bool(isinstance(cookie,str) and isinstance(header,str) and re.fullmatch('[a-f0-9]{64}',cookie) and hmac.compare_digest(cookie,header))

def install_helper():
    if os.geteuid()!=0:raise MaintenanceError('Linux sudo authorization required')
    import subprocess
    runner=Path('/opt/fischer-suite-updater/helper_runner.py')
    if not runner.exists():
        runner.write_text('import sys\nsys.path.insert(0,"/opt/fischer-suite-updater/current")\nfrom maintenance.helper import main\nmain()\n');runner.chmod(0o644)
    unit=Path('/etc/systemd/system/fischer-suite-updater-web.service')
    if not unit.exists():
        unit.write_text('[Unit]\nDescription=Fischer fixed-action software update helper\nAfter=network.target\n[Service]\nUser=root\nGroup=www-data\nRuntimeDirectory=fischer-suite-updater-web\nRuntimeDirectoryMode=0750\nUMask=0007\nExecStart=/usr/bin/python3 -I /opt/fischer-suite-updater/helper_runner.py\nNoNewPrivileges=true\nProtectSystem=true\nPrivateTmp=true\nRestrictSUIDSGID=true\nRestrictAddressFamilies=AF_UNIX AF_INET AF_INET6\nRestart=on-failure\nTimeoutStopSec=30\n[Install]\nWantedBy=multi-user.target\n');unit.chmod(0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','reset-failed','fischer-suite-updater-web'],check=False)
    subprocess.run(['systemctl','enable','--now','fischer-suite-updater-web'],check=True)

def installation_choice(mode=None,networks=None,origins=None,credential=None):
    if POLICY.exists():return {'preserved_existing_policy':True}
    if mode is None:
        print('Dashboard updates: 1 disabled (default), 2 password-free trusted-LAN HTTP, 3 reuse HTTPS dashboard credentials')
        answer=input('Choose 1, 2 or 3 [1]: ').strip() or '1'
        if answer not in ('1','2','3'):raise MaintenanceError('Choose 1, 2 or 3')
        mode={'1':'disabled','2':'trusted-lan','3':'dashboard'}[answer]
    networks=list(networks or []);origins=list(origins or [])
    if mode!='disabled' and not origins:origins=[input('Exact dashboard origin (scheme://host:port): ').strip()]
    if mode=='trusted-lan' and not networks:networks=[input('Trusted private LAN CIDR (for example 192.168.1.0/24): ').strip()]
    if mode=='dashboard' and not credential:
        files=[p for p in sorted(CREDENTIAL_FILES) if Path(p).is_file()]
        if not files:raise MaintenanceError('Existing dashboard credentials not found; no separate update password is requested')
        credential=files[0]
    result=configure(mode,origins,networks,credential)
    if mode!='disabled':install_helper()
    return result
