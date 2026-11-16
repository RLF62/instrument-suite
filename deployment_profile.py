"""Root-owned deployment policy for an existing HTTPS suite gateway."""
import json
from pathlib import Path
import shutil
PROFILE=Path('/etc/fischer-suite/profile.json')
SECURITY=Path('/home/pi/instrument-suite/security')
AUTH_NAMES=('.control_auth_mode','.control_htpasswd')

def secure_gateway():
    try:st=PROFILE.stat()
    except FileNotFoundError:
        if Path('/etc/systemd/system/fischer-suite-web.service').exists():raise RuntimeError('The HTTPS gateway policy is missing; refusing an unsecured activation')
        return False
    if st.st_uid!=0 or st.st_mode&0o022:raise RuntimeError('The HTTPS gateway policy must be root-owned and not writable by other users')
    try:valid=json.loads(PROFILE.read_text())=={'schema':1,'https_gateway':True}
    except (OSError,ValueError):valid=False
    if not valid:raise RuntimeError('Invalid HTTPS gateway policy; activation refused')
    return True

def bind_host(tool):
    return '127.0.0.1' if secure_gateway() and tool in ('meter','supply') else '0.0.0.0'

def public_records(records):
    if secure_gateway():
        for tool in ('meter','supply'):
            if tool in records:records[tool].update(scheme='https',port=None)
    return records

def sync_security(app):
    if not secure_gateway():return
    SECURITY.mkdir(parents=True,exist_ok=True);SECURITY.chmod(0o700)
    for name in AUTH_NAMES:
        p=app/name
        if p.is_file() and not p.is_symlink():
            shutil.copy2(p,SECURITY/name);(SECURITY/name).chmod(0o600)

def configure_app(tool,target):
    if not secure_gateway():return
    if tool=='meter':
        p=target/'standalone_app.py';t=p.read_text()
        if 'FISCHER_GATEWAY_PROXY' not in t:
            t+='\n# FISCHER_GATEWAY_PROXY: backend is bound to loopback by the root helper.\nfrom werkzeug.middleware.proxy_fix import ProxyFix\napp.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)\n'
            p.write_text(t)
    elif tool=='supply':
        for name in AUTH_NAMES:
            if not (target/name).exists() and (SECURITY/name).is_file():
                shutil.copy2(SECURITY/name,target/name)
        (target/'supply_standalone.py').write_text('''"""HTTPS gateway backend; retain the existing supply authentication behavior."""
import app as controller
from flask import request
from werkzeug.middleware.proxy_fix import ProxyFix
app=controller.app
app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)
controller.proxy_control_auth_mode=lambda: '2' if request.remote_addr=='127.0.0.1' and request.is_secure else None
''')
