"""Shared Classic/Modern generator web API; never opens a hardware connection."""
import threading
from flask import Blueprint, jsonify, render_template, request
from gpib_client import execute, AdapterError
from .protocol import validate, validate_sweep

bp = Blueprint('generator', __name__, url_prefix='/generator', template_folder='templates', static_folder='static', static_url_path='/assets')
@bp.get('/classic')
def classic(): return render_template('generator.html', modern=False)
@bp.get('/modern')
def modern(): return render_template('generator.html', modern=True)

def install(app, transport=execute, simulated=False):
    app.register_blueprint(bp)
    from suite_navigation import install as navigation
    navigation(app,current='generator',default=('generator',))
    lock = threading.Lock()
    state = {'configuration':None, 'error':None, 'source':'simulated' if simulated else 'disconnected'}
    @app.get('/api/generator/status')
    def status():
        with lock: return jsonify(state), 200, {'Cache-Control':'no-store'}
    @app.post('/api/control/generator/<action>')
    def control(action):
        data = request.get_json(silent=True)
        if action not in ('identify','configuration','apply','sweep_configuration','sweep_apply','sweep_start','sweep_stop') or not isinstance(data,dict):
            return jsonify(error='Unsupported action or invalid JSON object'),400
        if action in ('apply','sweep_apply'):
            try: (validate_sweep if action=='sweep_apply' else validate)(data.get('settings'))
            except ValueError as exc: return jsonify(error=str(exc)),400
            if data.get('confirm_output_change') is not True:
                return jsonify(error='Explicit output-change acknowledgment required'),400
        if not lock.acquire(blocking=False): return jsonify(error='Generator request in progress'),409
        try:
            result = transport('generator',action,**data)
            if action == 'identify':
                state.update(configuration=None, identity=result['identity'])
            else: state.update(configuration=result)
            state.update(error=None,source='simulated' if simulated else 'readback')
            return jsonify(state)
        except (AdapterError,ValueError,RuntimeError) as exc:
            state.update(error=str(exc),source='unknown',configuration=None)
            return jsonify(state),503
        finally: lock.release()
