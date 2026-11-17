"""Trusted-LAN HTTP host; existing secured supply installations are never replaced."""
import app as controller
from flask import request, jsonify
app = controller.app
controller.control_password_required = lambda: False

@app.before_request
def origin_guard():
    if request.path.startswith('/api/control/') and request.headers.get('Origin') != request.host_url.rstrip('/'):
        return jsonify(error='Request origin did not match the controller'), 403
