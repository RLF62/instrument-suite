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
    return '127.0.0.1' if secure_gateway() and tool in ('meter','supply','generator','counter') else '0.0.0.0'

def public_records(records):
    if secure_gateway():
        for tool in ('meter','supply','generator','counter'):
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

def guarded_entry(tool):
    module={'meter':'standalone_app','supply':'supply_standalone','scope':'app','generator':'generator_app','counter':'counter_app'}[tool]
    text=f'import {module} as controller\nfrom maintenance.guard import install\napp=controller.app\n'
    if tool=='supply':text+='controller=controller.controller\n'
    extras=''
    if tool=='meter':text+='import hp34401a as meter\n';extras=', meter=meter'
    if tool=='scope':text+='import scope_io\n';extras=', scope_io=scope_io'
    return text+f'install(app,{tool!r},controller{extras})\n'

def standalone_service(tool,target,text,port,module):
    """Recognize an independent direct launcher or the exact signed guard wrapper."""
    target=Path(target)
    if f'WorkingDirectory={target}\n' not in text or f':{port}' not in text:
        return False
    starts=[line for line in text.splitlines() if line.startswith('ExecStart=')]
    if len(starts)!=1 or f'{target}/venv/bin/gunicorn ' not in starts[0]:
        return False
    if starts[0].split()[-1:]==[module+':app']:
        return True
    if starts[0].split()[-1:]!=['maintenance_entry:app']:
        return False
    entry=target/'maintenance_entry.py'
    try:return not entry.is_symlink() and entry.read_text()==guarded_entry(tool)
    except OSError:return False
