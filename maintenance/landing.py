"""Read-only shared dashboard; privileged web actions are not enabled here."""
import html
import json
from pathlib import Path
from flask import Flask, Response, request

app=Flask(__name__)
ROOT=Path('/var/lib/fischer-suite-updater/public-status.json')
from .web_updates import install as install_web_updates
install_web_updates(app)
from .firmware_web import install as install_firmware
install_firmware(app)

@app.get('/')
def home():
    try:data=json.loads(ROOT.read_text())
    except (OSError,ValueError):data={'components':{}}
    # Use the browser's host without inserting it into executable markup.
    host=request.host.split(':',1)[0]
    items=[]
    for tool,title,port,path in [('meter','HP 34401A Multimeter',8082,'/multimeter/classic'),('supply','HP 6033A Supply',8083,'/'),('scope','Tektronix Scope',8081,'/'),('generator','HP 33120A Function Generator',8084,'/generator/classic'),('counter','HP 5385A Frequency Counter',8085,'/classic')]:
        if tool in data['components']:
            url='http://'+host+':'+str(port)+path
            items.append('<li><a href="'+html.escape(url,quote=True)+'">'+title+'</a> '+html.escape(data['components'][tool]['version'])+'</li>')
    return Response('<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Fischer Instrument Suite</title><style>body{font:18px system-ui;max-width:800px;margin:3rem auto;padding:1rem;background:#101c29;color:#eee}a{color:#62d6ce}li{margin:1rem 0}code{color:#8fe2dc}</style></head><body><h1>Fischer Instrument Suite</h1><ul>'+''.join(items)+'</ul><h2>Adapter firmware</h2><p><a href="/gpib-firmware">USB-GPIB Firmware</a></p><h2>Software maintenance</h2><p><a href="/software-updates">Software Updates</a></p><p>Check: <code>sudo instrument-suite check</code></p><p>Update: <code>sudo instrument-suite update</code></p><p>Recovery: <code>sudo instrument-suite rollback</code></p><p>Instrument controls remain in their individual dashboards.</p></body></html>',mimetype='text/html',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'"})
