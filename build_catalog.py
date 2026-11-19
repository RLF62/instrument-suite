"""Build pinned local catalog packages from reviewed repository checkouts."""
import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

SOURCE=Path(__file__).resolve().parent

def bundle(root,target):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(root.rglob('*')):
            if not p.is_file() or any(x in p.parts for x in ('__pycache__','.git','venv','approved')) or p.suffix=='.zip' or p.name=='front-panel.png':continue
            archive.write(p,p.relative_to(root).as_posix())
    return hashlib.sha256(target.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--supply-source',type=Path,default=SOURCE/'controllers/supply')
    p.add_argument('--scope-source',type=Path,default=SOURCE/'controllers/scope')
    args=p.parse_args()
    output=SOURCE/'approved';(output/'packages').mkdir(parents=True,exist_ok=True)
    rows={}
    with tempfile.TemporaryDirectory() as d:
        staging=Path(d);meter=staging/'meter';meter.mkdir()
        for path in SOURCE.iterdir():
            if path.is_file() and path.suffix in ('.py','.js','.html','.txt','.json','.md','.sh'):shutil.copy2(path,meter/path.name)
        shutil.copytree(SOURCE/'hp34401a',meter/'hp34401a',ignore=shutil.ignore_patterns('__pycache__'))
        (meter/'integration/templates').mkdir(parents=True);shutil.copytree(SOURCE/'integration/templates',meter/'integration/templates',dirs_exist_ok=True)
        supply=staging/'supply';shutil.copytree(args.supply_source,supply,ignore=shutil.ignore_patterns('__pycache__','.git','venv'))
        subprocess.run([sys.executable,str(SOURCE/'patch_hp.py'),str(supply/'app.py')],check=True)
        text=(supply/'app.py').read_text();text=text.replace('from hp34401a import install as install_meter\ninstall_meter(app)','from suite_navigation import install as install_navigation\ninstall_navigation(app,current="supply",default=("supply",))')
        text=re.sub(r'# Optional shared instrument menu\.\ntry:.*?install_suite_navigation\(app, \'supply\'\)\n', '', text, flags=re.S)
        ast.parse(text)
        if 'ResourceManager' in text or 'serial.Serial' in text or 'install_meter(app)' in text:raise RuntimeError('Supply package is not isolated/coordinated')
        (supply/'app.py').write_text(text)
        (supply/'supply_standalone.py').write_text('''"""Trusted-LAN HTTP host; existing secured supply installations are never replaced."""
import app as controller
from flask import request,jsonify
app=controller.app
controller.control_password_required=lambda:False
@app.before_request
def origin_guard():
    if request.path.startswith('/api/control/') and request.headers.get('Origin')!=request.host_url.rstrip('/'):
        return jsonify(error='Request origin did not match the controller'),403
''')
        shutil.copytree(SOURCE/'integration/templates',supply/'templates',dirs_exist_ok=True)
        scope=staging/'scope';shutil.copytree(args.scope_source,scope,ignore=shutil.ignore_patterns('__pycache__','.git','venv'))
        s=(scope/'scope_io.py').read_text();s=s.replace("        s = BoundedInstrument(c['address'])","        if c['address']=='scope-not-configured.invalid':raise ScopeError('Open Setup and enter the scope IP address before connecting.',409)\n        s = BoundedInstrument(c['address'])")
        (scope/'scope_io.py').write_text(s)
        generator=staging/'generator';generator.mkdir()
        for name in ('generator_app.py','gpib_client.py','suite_navigation.py','navigation.js','catalog_web.py','catalog.html','test_generator.py'):
            shutil.copy2(SOURCE/name,generator/name)
        shutil.copy2(SOURCE/'hp33120a-requirements.txt',generator/'requirements.txt')
        shutil.copytree(SOURCE/'hp33120a',generator/'hp33120a',ignore=shutil.ignore_patterns('__pycache__','*.orig','*.before-*','*.pre-*','hp33120a-panel-updated.png','front-panel-original.jpg'))
        shutil.copy2(SOURCE/'tool_registration.py',generator/'tool_registration.py')
        for target in (supply,scope):shutil.copy2(SOURCE/'tool_registration.py',target/'tool_registration.py')
        for key,root,name,description in [('meter',meter,'HP 34401A Multimeter','Photographic Classic and Modern meter views, shared GPIB backend and local manual.'),('supply',supply,'HP 6033A Supply','Classic and Modern supply views with coordinated GPIB access. Hardware control stays disabled until configured.'),('scope',scope,'Tektronix Ethernet','Scope dashboard, captures and setup over Ethernet. Enter the scope IP after installing.'),('generator',generator,'HP 33120A Function Generator','Photographic Classic and Modern views, verified waveform readback, staged rotary control, and sweep setup.')]:
            rows[key]={'name':name,'description':description,'sha256':bundle(root,output/'packages'/(key+'.zip'))}
    (output/'catalog.json').write_text(json.dumps({'version':'development-2026-11-18','tools':rows},indent=2)+'\n')
    print('Built checksum-pinned catalog:',json.dumps({k:v['sha256'] for k,v in rows.items()}))

if __name__=='__main__':main()
