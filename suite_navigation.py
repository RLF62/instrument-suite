"""Explicit installed-tool navigation; never probes instruments or changes hardware."""
import json
import os
from pathlib import Path
from flask import Response

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
            if '</body>' in body:
                body = body.replace('</body>', '<script defer src="/api/suite/navigation.js?v=20261119-header7"></script></body>')
                response.set_data(body)
                response.headers.pop('ETag', None)
                response.headers['Cache-Control'] = 'no-cache'
        return response
