"""Loopback-only generator host. Simulation is explicit and never opens VISA/USB."""
from flask import Flask, jsonify, redirect, request
from werkzeug.middleware.proxy_fix import ProxyFix
from hp33120a import install

def create_app(simulated=False):
    app=Flask(__name__)
    app.config['MAX_CONTENT_LENGTH']=4096
    app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)
    @app.before_request
    def origin():
        if request.path.startswith('/api/control/'):
            if request.headers.get('Origin') != request.host_url.rstrip('/'):
                return jsonify(error='Request origin did not match the controller'),403
            if not request.is_json: return jsonify(error='Expected application/json'),415
    @app.get('/')
    def home(): return redirect('/generator/classic')
    if simulated:
        from hp33120a.simulator import Device
        device=Device(); app.config['SIMULATOR']=device
        install(app,device.transport,simulated=True)
    else: install(app)
    return app
app=create_app()
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--simulate',action='store_true',required=True)
    args=parser.parse_args()
    create_app(simulated=True).run(host='127.0.0.1',port=8084)
