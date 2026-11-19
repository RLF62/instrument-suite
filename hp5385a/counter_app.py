"""HP 5385A controller on the suite's single shared GPIB broker."""
from flask import Flask, jsonify, request, send_from_directory, redirect
from gpib_client import AdapterError, execute
from suite_navigation import install as install_navigation

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4096
state = {'mode': 'unknown', 'gate': 'unknown', 'attenuation': 'unknown', 'filter': 'unknown'}

@app.before_request
def protect_controls():
    if request.path.startswith('/api/control/'):
        if request.headers.get('Origin') != request.host_url.rstrip('/'):
            return jsonify(error='Request origin did not match the controller'), 403
        if not request.is_json:
            return jsonify(error='Expected application/json'), 415

@app.get('/')
def entry():
    return redirect('/classic')

@app.get('/classic')
@app.get('/modern')
def home():
    return send_from_directory('static', 'index.html')

@app.get('/static/<path:name>')
def static_asset(name):
    return send_from_directory('static', name)

@app.get('/docs/')
def docs():
    return send_from_directory('static', 'docs.html')

@app.get('/api/counter/identity')
def identity():
    try:
        return jsonify(execute('counter', 'identify'))
    except AdapterError as exc:
        return jsonify(error=str(exc)), 503

@app.get('/api/counter/reading')
def reading():
    try:
        return jsonify(execute('counter', 'sample', mode=state['mode']))
    except AdapterError as exc:
        return jsonify(error=str(exc)), 503

@app.get('/api/counter/state')
def configuration():
    return jsonify(state=state, note='Selections made in this page; physical front-panel changes are not read back.')

@app.post('/api/control/counter')
def control():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {'control', 'value'} or not all(isinstance(v, str) for v in body.values()):
        return jsonify(error='Expected a control and value'), 400
    try:
        result = execute('counter', 'control', **body)
    except AdapterError as exc:
        return jsonify(error=str(exc)), 503
    if body['control'] == 'reset':
        for key in state: state[key] = 'unknown'
    else:
        state[body['control']] = body['value']
    return jsonify(result=result, state=state)

install_navigation(app, current='counter', default=('counter',))
