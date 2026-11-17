"""Attended adapter firmware workflow using the existing dashboard policy."""
import secrets
from flask import Response, jsonify, request, send_from_directory
from pathlib import Path
from .web_updates import helper
from .web_policy import read_policy, authorize, csrf_valid
from .security import MaintenanceError

def install(app):
    @app.get('/gpib-firmware/photo')
    def photo():
        return send_from_directory(Path(__file__).parent/'assets','gpib-v2-bootloader.jpg')

    @app.route('/api/gpib-firmware', methods=['GET','POST'])
    def api():
        try:
            origin=authorize(request,read_policy())
            if request.method=='POST':
                if not request.is_json or not csrf_valid(request.cookies.get('fischer-firmware-csrf'),request.headers.get('X-CSRF-Token')):
                    return jsonify(error='Reload the firmware page before continuing'),403
                data=request.get_json(silent=True)
                if not isinstance(data,dict) or set(data)!={'action'} or not isinstance(data['action'],str) or data['action'] not in ('prepare','flash','resume','cancel'):
                    return jsonify(error='Choose a firmware workflow action'),400
                return jsonify(helper('firmware-'+data['action'])),202
            token=request.cookies.get('fischer-firmware-csrf')
            if not csrf_valid(token,token):token=secrets.token_hex(32)
            response=jsonify(csrf=token,status=helper('firmware-status'))
            response.set_cookie('fischer-firmware-csrf',token,httponly=True,secure=origin.startswith('https:'),samesite='Strict',path='/api/gpib-firmware')
            response.headers['Cache-Control']='no-store'
            return response
        except PermissionError as exc:
            response=jsonify(error=str(exc));response.status_code=401 if 'username and password' in str(exc) else 403
            if response.status_code==401:response.headers['WWW-Authenticate']='Basic realm="Fischer dashboard"'
            return response
        except (MaintenanceError,OSError,ValueError,RuntimeError) as exc:return jsonify(error=str(exc)),503

    @app.get('/gpib-firmware')
    def page():
        return Response(PAGE,mimetype='text/html',headers={'Cache-Control':'no-store','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"})

PAGE='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>USB-GPIB Firmware</title><style>
body{font:18px system-ui;max-width:900px;margin:2rem auto;padding:1rem;background:#101c29;color:#eee}a{color:#62d6ce}section{background:#1b2c3d;padding:1rem;border-radius:12px;margin:1rem 0}button{padding:.9rem;margin:.3rem;font:inherit;cursor:pointer}button:disabled{opacity:.4;cursor:default}li{margin:.8rem 0}#error{color:#ffb4a8}#progress{font-weight:bold;color:#8fe2dc}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}
</style></head><body><a href="/">Instrument Suite</a><h1>USB-GPIB V2 Firmware</h1><p>Install Kai's corrected V2.5 application firmware from the verified GitHub revision. Adapter settings are backed up and checked after writing.</p>
<section><h2>1. Prepare</h2><p>Pause multimeter acquisition. If the supply is connected, turn its output OFF and disable remote programming. Preparation checks the controllers, downloads and verifies the firmware, then pauses shared GPIB access.</p><button data-action="prepare">Prepare Firmware Update</button></section>
<section><h2>2. Enter bootloader</h2><figure><a href="/gpib-firmware/photo" target="_blank" rel="noopener" style="position:relative;display:block;width:fit-content;max-width:100%;margin:auto"><img src="/gpib-firmware/photo" alt="UsbGpib V2 adapter: bootloader button is the upper white rectangular button in the enclosure notch" style="display:block;max-width:100%;max-height:520px;object-fit:contain"><span aria-hidden="true" style="position:absolute;left:42%;top:18%;width:20%;height:9%;border:3px solid #f22;border-radius:50%;box-shadow:0 0 0 1px white;box-sizing:border-box"></span></a><figcaption>Bootloader button: the upper white rectangular button in the notch. Tap the photo to enlarge.</figcaption></figure><ol><li>Disconnect every GPIB cable from the adapter. Keep USB connected to this Raspberry Pi.</li><li>Press and hold the <strong>upper white rectangular button in the enclosure notch</strong> for a few seconds. The two small round parts below it are indicators.</li><li>Wait for "Bootloader detected" below, then write the firmware.</li></ol><button data-action="flash">Write and Verify Firmware</button></section>
<section><h2>3. Restart and verify</h2><p>After the write is verified, unplug BOTH USB and GPIB to remove all power. With USB still unplugged, connect the adapter to the instrument's GPIB connector first, then reconnect USB to the same Raspberry Pi port without holding the button. Connecting GPIB before USB may be needed to drain residual power and take the V2 adapter out of bootloader mode. Keep the instrument output OFF. Then verify the running version and resume the controllers.</p><button data-action="resume">Verify Version and Resume</button><button data-action="cancel">Cancel Before Writing</button></section>
<section aria-live="polite"><p id="progress">Loading…</p><p id="device"></p><p id="error" role="alert"></p><details><summary>Verification details</summary><pre id="details"></pre></details></section>
<p><a href="https://github.com/xyphro/UsbGpib/blob/master/Tutorials/UsbGpibV2_manual.md#firmware-update-procedure" target="_blank" rel="noopener">Kai's firmware update instructions</a></p>
<script>
let csrf='',busy=false;
const error=document.getElementById('error');
async function refresh(){try{
 const r=await fetch('/api/gpib-firmware',{cache:'no-store'}),d=await r.json();if(!r.ok)throw Error(d.error);csrf=d.csrf;
 const s=d.status.firmware,j=d.status.job,p=s.session?.phase,working=j?.state==='running';busy=working;
 document.getElementById('progress').textContent=s.session?.message||(s.last_session?.phase==='completed'?'Last update completed and verified.':'Ready to prepare an update.');
 document.getElementById('device').textContent=s.device_error||((s.bootloaders.length===1?'Bootloader detected.':s.normal_adapters.length===1?'Adapter connected in normal mode.':'No single adapter detected.'));
 error.textContent=j?.state==='failed'?j.message:'';
 document.getElementById('details').textContent=JSON.stringify({approved:s.approved,session:s.session,last_session:s.last_session,job:j},null,2);
 for(const b of document.querySelectorAll('[data-action]')){
 const a=b.dataset.action;
 b.disabled=working||(a==='prepare'?!!p:a==='flash'?!(['awaiting_bootloader','write_failed','writing'].includes(p)&&s.bootloaders.length===1):a==='resume'?p!=='awaiting_power_cycle':!['preparing','awaiting_bootloader'].includes(p));
 }
}catch(e){error.textContent=e.message;document.querySelectorAll('[data-action]').forEach(b=>b.disabled=true)}}
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=async()=>{
 if(busy)return;const a=b.dataset.action;if(a==='flash'&&!confirm('Write the verified V2.5 firmware now? Keep USB connected until verification finishes.'))return;
 busy=true;document.querySelectorAll('[data-action]').forEach(x=>x.disabled=true);
 try{const r=await fetch('/api/gpib-firmware',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({action:a})}),d=await r.json();if(!r.ok)throw Error(d.error);await refresh()}catch(e){busy=false;error.textContent=e.message}
});refresh();setInterval(refresh,2500);
</script></body></html>'''
