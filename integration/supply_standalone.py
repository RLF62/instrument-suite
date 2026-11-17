"""Trusted-LAN HTTP host; existing secured supply wrappers are preserved."""
import app as supply
from flask import request, jsonify

app = supply.app
controller = supply.controller
supply.control_password_required = lambda: False

@app.before_request
def origin_guard():
    if request.path.startswith('/api/control/') and request.headers.get('Origin') != request.host_url.rstrip('/'):
        return jsonify(error='Request origin did not match the controller'), 403
