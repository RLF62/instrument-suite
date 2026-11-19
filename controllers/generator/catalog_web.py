"""Unprivileged UI: only fixed catalog actions cross the local helper socket."""
import json
import socket
import sys
from pathlib import Path
from flask import Response, jsonify, request

SOCKET='/run/fischer-suite-manager/install.sock'

def helper(payload):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(SOCKET)
        client.sendall(json.dumps(payload).encode()+b'\n')
        with client.makefile('rb') as stream:
            result=json.loads(stream.readline(65536))
    if not result.get('ok'):raise RuntimeError(result.get('error','Manager request failed'))
    return result['result']

def install(app):
    @app.get('/api/suite/removal-state')
    def instrument_removal_state():
        module=sys.modules.get(app.import_name)
        meter=sys.modules.get('hp34401a')
        return jsonify(polling=bool(meter and meter.snapshot().get('polling')),
                       remote_control_enabled=bool(getattr(module,'remote_control_enabled',False)))

    @app.get('/api/suite/manager')
    def instrument_manager_page():
        return Response((Path(__file__).parent/'catalog.html').read_text(),mimetype='text/html',headers={'Cache-Control':'no-store'})

    @app.get('/api/suite/catalog')
    def instrument_catalog():
        try:return jsonify(helper({'action':'status'}))
        except (OSError,ValueError,RuntimeError) as exc:return jsonify(error='Instrument manager unavailable: '+str(exc)),503

    @app.post('/api/control/suite/install')
    def instrument_catalog_install():
        if request.headers.get('Origin')!=request.host_url.rstrip('/'):
            return jsonify(error='Request origin did not match the controller'),403
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'tool'} or data['tool'] not in ('meter','supply','scope','generator'):
            return jsonify(error='Choose one approved instrument'),400
        try:return jsonify(helper({'action':'install','tool':data['tool']})),202
        except (OSError,ValueError,RuntimeError) as exc:return jsonify(error=str(exc)),409

    @app.post('/api/control/suite/remove')
    def instrument_catalog_remove():
        if request.headers.get('Origin')!=request.host_url.rstrip('/'):
            return jsonify(error='Request origin did not match the controller'),403
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'tool','keep_settings','confirm'} or data['tool'] not in ('meter','supply','scope','generator') or type(data['keep_settings']) is not bool or data['confirm'] is not True:
            return jsonify(error='Choose an approved instrument and explicitly confirm removal'),400
        try:return jsonify(helper({'action':'remove',**data})),202
        except (OSError,ValueError,RuntimeError) as exc:return jsonify(error=str(exc)),409
