"""Only supported hardware entry point for suite applications."""
import json
import os
import socket

SOCKET = os.environ.get('FISCHER_GPIB_SOCKET', '/run/fischer-gpib/adapter.sock')


class AdapterError(RuntimeError):
    pass


def execute(target, action, **data):
    payload = {'target': target, 'action': action, 'data': data}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(7)
        try:
            sock.connect(SOCKET)
            sock.sendall(json.dumps(payload, allow_nan=False).encode() + b'\n')
            with sock.makefile('rb') as stream:
                response = json.loads(stream.readline(16384))
        except (OSError, ValueError) as exc:
            raise AdapterError('Shared GPIB service unavailable: ' + str(exc)) from exc
    if not response.get('ok'):
        raise AdapterError(response.get('error', 'Adapter transaction failed'))
    return response['result']
