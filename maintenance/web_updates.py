"""Same-origin, CSRF-protected web bridge to the fixed-action root helper."""
import json
import secrets
import socket
from flask import Response,jsonify,request
from .web_policy import read_policy,authorize,csrf_valid
from .security import MaintenanceError

SOCKET='/run/fischer-suite-updater-web/control.sock'

def helper(action):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(5);client.connect(SOCKET)
        client.sendall(json.dumps({'schema':1,'action':action}).encode()+b'\n')
        raw=client.makefile('rb').readline(65537)
        if len(raw)>65536:raise RuntimeError('Unexpected helper response')
        result=json.loads(raw)
        if not result.get('ok'):raise RuntimeError(result.get('error','Update helper unavailable'))
        return result['result']

def install(app):
    @app.route('/api/software-updates',methods=['GET','POST'])
    def software_updates():
        try:
            policy=read_policy();origin=authorize(request,policy)
            if request.method=='POST':
                if not request.is_json or not csrf_valid(request.cookies.get('fischer-update-csrf'),request.headers.get('X-CSRF-Token')):
                    return jsonify(error='CSRF verification failed; reload the Software Updates page'),403
                data=request.get_json(silent=True)
                if not isinstance(data,dict) or set(data)!={'action'} or data['action'] not in ('check','update','backup','rollback'):
                    return jsonify(error='Choose Check, Update, Backup or Rollback'),400
                return jsonify(helper(data['action'])),202
            token=request.cookies.get('fischer-update-csrf')
            if not csrf_valid(token,token):token=secrets.token_hex(32)
            response=jsonify(csrf=token,mode=policy['mode'],status=helper('status'))
            response.set_cookie('fischer-update-csrf',token,httponly=True,secure=origin.startswith('https:'),samesite='Strict',path='/api/software-updates')
            response.headers['Cache-Control']='no-store';return response
        except PermissionError as exc:
            response=jsonify(error=str(exc));response.status_code=401 if 'username and password' in str(exc) else 403
            if response.status_code==401:response.headers['WWW-Authenticate']='Basic realm="Fischer dashboard"'
            return response
        except (MaintenanceError,OSError,ValueError,RuntimeError) as exc:return jsonify(error=str(exc)),503

    @app.get('/software-updates')
    def update_page():
        return Response('''<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Fischer Software Updates</title><style>body{font:18px system-ui;max-width:900px;margin:2rem auto;padding:1rem;background:#101c29;color:#eee}a{color:#62d6ce}button{padding:.8rem;margin:.3rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}#mode{color:#8fe2dc}</style></head><body><a href="/">Instrument Suite</a><h1>Software Updates</h1><p id="mode"></p><p>Updates retain signature verification, instrument safety checks, backups and automatic rollback.</p><button data-action="check">Check for Updates</button><button data-action="update">Download and Install</button><button data-action="backup">Create Backup</button><button data-action="rollback">Rollback</button><pre id="status">Loading…</pre><script>
let csrf='';async function refresh(){try{const r=await fetch('/api/software-updates',{cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(d.error);csrf=d.csrf;document.getElementById('mode').textContent=d.mode==='trusted-lan'?'Password-free updates enabled for the configured trusted LAN.':'Uses your existing dashboard credentials.';document.getElementById('status').textContent=JSON.stringify(d.status,null,2)}catch(e){document.getElementById('status').textContent=e.message}}document.querySelectorAll('[data-action]').forEach(b=>b.onclick=async()=>{if(['update','rollback'].includes(b.dataset.action)&&!confirm('Proceed with '+b.dataset.action+'? Instrument safety checks must pass.'))return;try{const r=await fetch('/api/software-updates',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({action:b.dataset.action})});const d=await r.json();if(!r.ok)throw Error(d.error);await refresh()}catch(e){document.getElementById('status').textContent=e.message}});refresh();setInterval(refresh,3000);
</script></body></html>''',mimetype='text/html',headers={'Cache-Control':'no-store','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'; frame-ancestors 'none'"})
