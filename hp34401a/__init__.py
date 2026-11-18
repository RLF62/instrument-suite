"""HP 34401A backend; Classic and Modern are presentation-only consumers."""
import math
import json
from pathlib import Path
import threading
import time
from flask import Blueprint, jsonify, render_template, request
from gpib_client import execute, AdapterError

bp = Blueprint('meter', __name__, url_prefix='/multimeter',
               template_folder='templates', static_folder='static', static_url_path='/assets')
state_lock = threading.Lock()
operation_lock = threading.Lock()
state = {'identity': None, 'configuration': None, 'value': None, 'reading': '—',
         'unit': '', 'sample_time': None, 'source': 'disconnected', 'polling': False,
         'pending_controls': 0, 'prepared': False, 'error': 'Connect and verify the HP 34401A to begin.',
         'display_digits': 6, 'acquisition': 'manual', 'hold_band': .1, 'hold_window': [],
         'local_requested': False, 'last_contact': None, 'menu_result': None,
         'hold_captured': False,
         'stats': {'count': 0, 'min': None, 'max': None, 'mean': None}}
poll_thread = None
thread_lock = threading.Lock()
try:
    state['read_only'] = json.loads(Path('/home/pi/instrument-suite/config.json').read_text()).get('meter_read_only', True)
except (OSError,ValueError):
    state['read_only'] = True


def format_reading(value, overloaded=False, digits=6):
    if overloaded:
        return 'OVLD'
    if value is None:
        return '—'
    if not math.isfinite(value):
        raise ValueError('Non-finite measurement')
    exponent = math.floor(math.log10(abs(value))) if value else 0
    if exponent < -6 or exponent > 7:
        return f'{value:+.{digits}E}'
    return f'{value:+.{max(0, digits-exponent)}f}'


def snapshot():
    with state_lock:
        result = {**state, 'stats': dict(state['stats'])}
    age = time.time()-result['sample_time'] if result['sample_time'] else None
    result['age_seconds'] = round(max(0, age), 1) if age is not None else None
    if result['acquisition'] == 'hold' and result['polling'] and not result['hold_captured']:
        result['source'] = 'waiting_hold'
    elif result['sample_time'] and result['acquisition'] == 'hold' and result['polling']:
        result['source'] = 'held'
    elif result['sample_time'] and (not result['polling'] or age > 4):
        result['source'] = 'stale'
    return result


def failed(exc):
    with state_lock:
        state.update(error=str(exc), polling=False, prepared=False,
                     source='stale' if state['sample_time'] else 'disconnected')


def sample(single=False):
    result = execute('meter', 'single' if single else 'sample')
    with state_lock:
        value = result['value']
        stats = state['stats']
        if value is not None:
            n = stats['count'] + 1
            stats.update(count=n, min=value if n == 1 else min(stats['min'], value),
                         max=value if n == 1 else max(stats['max'], value),
                         mean=value if n == 1 else stats['mean']+(value-stats['mean'])/n)
        state['last_contact'] = result['sample_time']
        state['local_requested'] = False
        window = state['hold_window']
        if value is not None:
            window.append(value); del window[:-3]
        stable = len(window)==3 and max(window)-min(window) <= max(abs(sum(window)/3)*state['hold_band']/100,1e-12)
        if state['acquisition'] != 'hold' or stable or result['overload']:
            if state['acquisition'] == 'hold':state['hold_captured']=stable
            state.update(value=value, reading=format_reading(value, result['overload'],state['display_digits']),
                         unit=result['unit'], sample_time=result['sample_time'], source='live', error=None)
    return result


def poll_loop():
    while True:
        time.sleep(1.5)
        with state_lock:
            enabled = state['polling'] and state['pending_controls'] == 0
        if enabled and operation_lock.acquire(blocking=False):
            try:
                # Check again after taking the operation lock so Pause cannot race the next poll.
                with state_lock:
                    enabled = state['polling'] and state['pending_controls'] == 0
                if enabled:
                    sample()
            except Exception as exc:
                failed(exc)
            finally:
                operation_lock.release()


def ensure_thread():
    global poll_thread
    with thread_lock:
        if poll_thread is None:
            poll_thread = threading.Thread(target=poll_loop, daemon=True, name='meter-poll')
            poll_thread.start()


@bp.get('/classic')
def classic():
    return render_template('meter.html', modern=False)


@bp.get('/modern')
def modern():
    return render_template('meter.html', modern=True)


def install(app):
    app.register_blueprint(bp)
    from suite_navigation import install as install_navigation
    standalone = app.config.get('SUITE_STANDALONE', False)
    install_navigation(app, current='meter' if standalone else 'auto',
                       default=('meter',) if standalone else ('meter','supply','scope','generator'))

    @app.get('/api/multimeter/status')
    def meter_status():
        return jsonify(snapshot()), 200, {'Cache-Control': 'no-store'}

    @app.post('/api/control/meter/<action>')
    def meter_control(action):
        ensure_thread()
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Expected a JSON object'), 400
        if action == 'pause':
            with state_lock:
                state['polling'] = False
            return jsonify(snapshot())
        if action == 'web-digits':
            digits = data.get('digits')
            if type(digits) is not int or digits not in (4,5,6):
                return jsonify(error='Choose 4½, 5½ or 6½ web display digits'),400
            with state_lock:
                state['display_digits']=digits
                state['reading']=format_reading(state['value'],state['reading']=='OVLD',digits)
            return jsonify(snapshot())
        if action == 'hold-band':
            if data.get('value') not in (.01,.1,1,10):
                return jsonify(error='Choose a hold band of 0.01%, 0.1%, 1% or 10%'),400
            with state_lock:state['hold_band']=data['value']
            return jsonify(snapshot())
        if action == 'stats-reset':
            with state_lock:
                state['stats'] = {'count': 0, 'min': None, 'max': None, 'mean': None}
            return jsonify(snapshot())
        if action not in ('identify', 'configuration', 'prepare', 'sample', 'single', 'poll', 'web-auto-hold', 'function', 'range', 'digits', 'math', 'menu-read', 'menu-set', 'local'):
            return jsonify(error='Unsupported meter action'), 400
        with state_lock:
            state['pending_controls'] += 1
        if not operation_lock.acquire(timeout=3.5):
            with state_lock:
                state['pending_controls'] -= 1
            return jsonify(error='Meter control queue timed out; current transaction has not finished'), 409
        try:
            if action == 'identify':
                identity = execute('meter', 'identify')
                with state_lock:
                    state.update(identity=identity['identity'], configuration=None,
                                 polling=False, prepared=False, error=None,local_requested=False,
                                 value=None,reading='—',unit='',sample_time=None,source='disconnected')
                configuration = execute('meter', 'configuration')
                with state_lock:
                    state['configuration'] = configuration
            elif action == 'configuration':
                configuration = execute('meter', action)
                with state_lock:
                    state.update(configuration=configuration, error=None)
            elif action == 'prepare':
                configuration = execute('meter', action)
                with state_lock:
                    state.update(configuration=configuration, prepared=True, error=None)
            elif action == 'local':
                with state_lock:state.update(polling=False,prepared=False,acquisition='manual')
                result = execute('meter','local')
                with state_lock:state.update(local_requested=result['local_requested'],error=None,menu_result=result)
            elif action in ('menu-read','menu-set'):
                result = execute('meter',action,**data)
                with state_lock:
                    state['menu_result']=result
                    if 'configuration' in result:
                        state['configuration']=result['configuration']
                    state['local_requested']=False
            elif action in ('poll', 'sample', 'single','web-auto-hold'):
                with state_lock:
                    prepared = state['prepared']
                if not prepared:
                    return jsonify(error='Verify identity, then enable measurements first'), 409
                if action in ('sample','single'):
                    with state_lock:state.update(polling=False,acquisition='manual')
                    sample(single=action=='single')
                else:
                    if state['configuration'].get('trigger_source') != 'IMM':
                        return jsonify(error='Auto/Hold web updates require immediate trigger; choose IMM in the web Trigger menu'),409
                    with state_lock:
                        mode = ('auto' if state['acquisition']=='hold' else 'hold') if action=='web-auto-hold' and state['polling'] else 'auto'
                        state.update(polling=True, error=None, acquisition=mode,local_requested=False,hold_window=[],hold_captured=False)
                        if mode=='hold':state.update(value=None,reading='—',unit='',sample_time=None)
            else:
                configuration = execute('meter', action, **data)
                with state_lock:
                    # A changed function must not leave a previous-function reading on the display.
                    state.update(configuration=configuration, value=None, reading='—', unit='',
                                 sample_time=None, source='disconnected', error=None,local_requested=False)
                    if action == 'digits':state['display_digits']=int(data['digits'])
                    state['stats'] = {'count': 0, 'min': None, 'max': None, 'mean': None}
            return jsonify(snapshot())
        except (AdapterError, ValueError) as exc:
            failed(exc)
            return jsonify(error=str(exc), state=snapshot()), 503
        finally:
            with state_lock:
                state['pending_controls'] -= 1
            operation_lock.release()
