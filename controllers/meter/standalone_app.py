"""Meter-only web host. No HP supply code or direct USB/VISA access."""
from flask import Flask, jsonify, redirect, request
from hp34401a import install as install_meter

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4096
app.config['SUITE_STANDALONE'] = True

@app.before_request
def same_origin_controls():
    if request.path.startswith('/api/control/'):
        if request.headers.get('Origin') != request.host_url.rstrip('/'):
            return jsonify(error='Request origin did not match the controller'), 403
        if not request.is_json:
            return jsonify(error='Expected application/json'), 415

@app.get('/')
def home():
    return redirect('/multimeter/classic')

install_meter(app)
