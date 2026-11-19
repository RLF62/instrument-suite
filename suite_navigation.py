"""Explicit installed-tool navigation; never probes instruments or changes hardware."""
import json
import os
import re
from html import escape
from urllib.parse import urlsplit
from pathlib import Path
from flask import Response, request

CONFIG = Path(os.environ.get('FISCHER_SUITE_TOOLS', '/home/pi/instrument-suite/tools.json'))
TOOLS = ('meter', 'supply', 'scope', 'generator', 'counter')
REGISTRY=Path('/home/pi/instrument-suite/registry.json')

def installed_records():
    try:
        records=json.loads(REGISTRY.read_text())['instruments']
        if not isinstance(records,dict) or any(k not in TOOLS for k in records):return {}
        for record in records.values():
            if not isinstance(record,dict):return {}
            if record.get('scheme') not in ('http','https') or (record.get('port') is not None and (type(record['port']) is not int or not 1<=record['port']<=65535)):
                return {}
        return records
    except (OSError,ValueError,KeyError,TypeError):return {}

def selected(default=('meter',)):
    records=installed_records()
    if records:return list(records)
    try:
        value = json.loads(CONFIG.read_text())['instruments']
        if not isinstance(value, list) or not value or any(x not in TOOLS for x in value):
            raise ValueError('Invalid instrument list')
        return list(dict.fromkeys(value))
    except FileNotFoundError:
        return list(default)

TITLES = {'supply':'HP 6033A POWER SUPPLY','meter':'HP 34401A MULTIMETER',
          'scope':'TEKTRONIX TDS 3032B','generator':'HP 33120A FUNCTION GENERATOR',
          'counter':'HP 5385A FREQUENCY COUNTER'}
LABELS = {'supply':'HP 6033A','meter':'HP 34401A','scope':'Tektronix',
          'generator':'HP 33120A','counter':'HP 5385A'}
VIEWS = {'supply':('/classic-dual','/'),'meter':('/multimeter/classic','/multimeter/modern'),
         'generator':('/generator/classic','/generator/modern'),'counter':('/classic','/modern')}
DOCS = {'supply':'/docs/','meter':'/multimeter/assets/docs/index.html','scope':'/docs/',
        'generator':'/generator/assets/docs.html','counter':'/docs/'}
HEADER_CSS = """<style>
#suite-unified-header{box-sizing:border-box;position:sticky;top:0;z-index:10000;width:100vw!important;max-width:none!important;
display:grid!important;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;
gap:16px;min-height:76px;padding:14px max(20px,2vw);margin:0 0 14px;margin-left:calc(50% - 50vw)!important;
background:#1e2226;border-top:2px solid #d0d6d9;border-bottom:1px solid #394550;
color:#f2f6f8;font:14px system-ui,sans-serif}
#suite-unified-header strong{text-align:center;white-space:nowrap;letter-spacing:.04em;font:700 15px system-ui,sans-serif}
#suite-unified-header .suite-links,#suite-unified-header .suite-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
#suite-unified-header .suite-links{justify-content:flex-start}
#suite-unified-header .suite-actions{justify-content:flex-end}
#suite-unified-header a{display:inline-flex;align-items:center;min-height:40px;padding:7px 12px;
border:1px solid #466b71;border-radius:5px;background:transparent;color:#a7e9eb;
text-decoration:none;font:13px system-ui,sans-serif;white-space:nowrap}
#suite-unified-header a[aria-current=page],#suite-unified-header a:hover{background:#31494f;border-color:#8de0e6;color:#fff}
body[data-suite-page=scope]>header:first-of-type{display:none!important}
body[data-suite-page=supply] nav:not(#suite-unified-header),
body[data-suite-page=meter] nav[aria-label="Instrument navigation"]:not(#suite-unified-header),
body[data-suite-page=generator] nav[aria-label="Instrument navigation"]:not(#suite-unified-header),
body[data-suite-page=counter] nav.suite-topbar:not(#suite-unified-header){display:none!important}
body[data-suite-page=supply] main.wrap>header.head>div:first-child{display:none!important}
@media(max-width:1349px){#suite-unified-header{display:flex;flex-direction:column;align-items:stretch}
#suite-unified-header strong{order:-1;align-self:center;white-space:normal}
#suite-unified-header .suite-actions{justify-content:flex-end}}
</style>"""

def header_html(current, path, hostname, records):
    if current not in TITLES:return ''
    classic=path=='/classic-dual' or path=='/classic' or path.endswith('/classic')
    def origin(record):
        scheme=record.get('scheme','http')
        port=record.get('port')
        return scheme+'://'+hostname+(':'+str(port) if port else '')
    def link(label,href,active=False):
        return '<a href="'+escape(href,quote=True)+'"'+(' aria-current="page"' if active else '')+'>'+escape(label)+'</a>'
    left=[]
    for tool,record in records.items():
        if tool==current or tool not in TITLES:continue
        target=VIEWS.get(tool,('/', '/'))[0 if classic else 1]
        left.append(link(LABELS[tool],origin(record)+target))
    here=urlsplit(request.host_url)
    base=here.scheme+'://'+hostname+(':'+str(here.port) if here.port else '')
    left.append(link('Add instruments',base+'/api/suite/manager'))
    right=[link('Suite Home',here.scheme+'://'+hostname+':8080/')]
    if current in VIEWS:
        right.extend(link(label,base+view,path==view) for label,view in zip(('Classic','Modern'),VIEWS[current]))
    elif current=='scope':right.append(link('Setup',base+'/setup'))
    right.append(link('Documentation',base+DOCS[current]))
    return HEADER_CSS+'<div id="suite-unified-header" role="navigation" aria-label="Instrument navigation"><div class="suite-links">'+''.join(left)+'</div><strong>'+TITLES[current]+'</strong><div class="suite-actions">'+''.join(right)+'</div></div>'

def install(app, current='meter', default=('meter',)):
    from catalog_web import install as install_catalog
    install_catalog(app)
    @app.get('/api/suite/navigation.js')
    def suite_navigation_script():
        try:
            instruments = selected(default)
        except (OSError, ValueError, KeyError, TypeError):
            instruments = []  # Invalid configuration must not advertise unknown tools.
        source = (Path(__file__).parent/'navigation.js').read_text()
        config = {'current': current, 'instruments': instruments,
                  'records':installed_records(),
                  'meterPort': app.config.get('SUITE_METER_PORT'),
                  'basePort': app.config.get('SUITE_BASE_PORT')}
        return Response('window.fischerSuite='+json.dumps(config)+';\n'+source,
                        mimetype='application/javascript', headers={'Cache-Control':'no-store'})

    @app.after_request
    def add_navigation(response):
        if response.mimetype == 'text/html' and response.status_code == 200:
            response.direct_passthrough = False  # Scope pages are served with send_file.
            body = response.get_data(as_text=True)
            if '</body>' in body and re.search(r'<body(?:\s[^>]*)?>',body,re.I) and request.path not in ('/setup',) and not request.path.startswith(('/docs','/api/','/gpib-firmware')):
                records=installed_records()
                tool=current if current!='auto' else ('meter' if request.path.startswith('/multimeter/') else 'generator' if request.path.startswith('/generator/') else 'supply')
                host=urlsplit(request.host_url).hostname or request.host.split(':')[0]
                top=header_html(tool,request.path,host,records)
                body=re.sub(r'<body(\s[^>]*)?>',lambda m:m.group(0)[:-1]+' data-suite-page="'+tool+'">'+top,body,count=1,flags=re.I)
                body = body.replace('</body>', '<script defer src="/api/suite/navigation.js?v=20261119-header9"></script></body>')
                response.set_data(body)
                response.headers.pop('ETag', None)
                response.headers['Cache-Control'] = 'no-cache'
        return response
