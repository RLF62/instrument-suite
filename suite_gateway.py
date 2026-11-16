"""Stable HTTPS web host; controllers remain independent and removable.
Only proxies HTTP requests. Does not import controller code or access GPIB.
"""
import base64,bcrypt,hmac,json,urllib.request,urllib.error
from pathlib import Path
from flask import Flask,Response,jsonify,request
from werkzeug.middleware.proxy_fix import ProxyFix
from catalog_web import install as install_catalog
from suite_navigation import installed_records,selected

HOME=Path('/home/pi')
SUITE=HOME/'instrument-suite'
SECURITY=SUITE/'security'
PORTS={'meter':8082,'supply':8083}
app=Flask(__name__,static_folder=None)
app.config['MAX_CONTENT_LENGTH']=262144
app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)
install_catalog(app)

def auth_path(name):
    live=HOME/'hp6033a'/name
    return live if live.is_file() and not live.is_symlink() else SECURITY/name

def password_required():
    try:return auth_path('.control_auth_mode').read_text().strip()!='password-free' or not auth_path('.control_htpasswd').is_file()
    except (OSError,UnicodeError):return True

def credentials_valid():
    auth=request.authorization
    if not auth or auth.type.lower()!='basic':return False
    try:
        user,digest=auth_path('.control_htpasswd').read_text().strip().split(':',1)
        valid_user=hmac.compare_digest((auth.username or '').encode(),user.encode())
        valid_password=bcrypt.checkpw((auth.password or '').encode(),digest.encode('ascii'))
        return valid_user and valid_password
    except (OSError,UnicodeError,ValueError):return False

@app.before_request
def authorize():
    control=request.path.startswith('/api/control/')
    admin=request.path=='/api/admin/control-auth'
    if not (control or admin):return
    if request.headers.get('Origin')!=request.host_url.rstrip('/'):
        return jsonify(error='Request origin did not match the controller'),403
    if (admin or password_required()) and not credentials_valid():
        return jsonify(error='Invalid or missing credentials'),401

@app.get('/api/suite/navigation.js')
def navigation():
    records=installed_records()
    cfg={'current':'auto','instruments':list(records),'records':records,'meterPort':None,'basePort':None}
    return Response('window.fischerSuite='+json.dumps(cfg)+';\n'+(SUITE/'navigation.js').read_text(),mimetype='application/javascript',headers={'Cache-Control':'no-store'})

def target_for(path):
    return 'meter' if path=='multimeter' or path.startswith(('multimeter/','api/multimeter/','api/control/meter/')) else 'supply'

def forward(tool,path):
    headers={k:v for k,v in request.headers.items() if k.lower() in ('authorization','content-type','accept','origin','user-agent')}
    headers.update({'Host':request.host,'X-Forwarded-Proto':request.scheme})
    url='http://127.0.0.1:'+str(PORTS[tool])+'/'+path
    if request.query_string:url+='?'+request.query_string.decode('ascii')
    data=request.get_data() if request.method not in ('GET','HEAD') else None
    req=urllib.request.Request(url,data=data,headers=headers,method=request.method)
    try:
        try:upstream=urllib.request.urlopen(req,timeout=30)
        except urllib.error.HTTPError as exc:upstream=exc
        with upstream:
            body=upstream.read()
            response_headers=[(k,v) for k,v in upstream.headers.items() if k.lower() not in ('content-length','transfer-encoding','connection','server','date')]
            return Response(body,status=upstream.status,headers=response_headers)
    except (OSError,ValueError):
        if request.path=='/':
            return Response('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fischer Instrument Suite</title><style>body{background:#202326;color:#eee;font:16px system-ui;padding:24px}a{color:#73e3d1;margin-right:16px}.suite-topbar{display:flex;gap:12px;flex-wrap:wrap}</style></head><body><nav class="suite-topbar"><h1>Fischer Instrument Suite</h1></nav><p>The power supply controller is not currently installed or available. Other installed instruments remain accessible from the menu.</p><a href="/api/suite/manager">Manage instruments</a><script defer src="/api/suite/navigation.js"></script></body></html>''',mimetype='text/html')
        return jsonify(error='This controller is not currently installed or available. Open Manage instruments to reinstall it.'),503

@app.route('/',defaults={'path':''},methods=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'])
@app.route('/<path:path>',methods=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'])
def proxy(path):
    return forward(target_for(path),path)
