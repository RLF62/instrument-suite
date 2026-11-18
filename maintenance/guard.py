"""Controller-side maintenance lease. No reset, stop or setting commands."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import struct
import threading
import time

class Guard:
    def __init__(self, tool, controller, meter=None, scope_io=None,
                 gate=Path('/var/lib/fischer-suite-updater/pending.flag')):
        self.tool, self.controller, self.meter, self.scope_io = tool, controller, meter, scope_io
        self.gate = Path(gate)
        self.condition = threading.Condition(); self.frozen = False; self.requests = 0

    def gated(self):
        try: return self.tool in json.loads(self.gate.read_text())['components']
        except FileNotFoundError: return False
        except (OSError, ValueError, KeyError, TypeError): return True

    def wrap(self, application):
        def wsgi(environ, start_response):
            with self.condition:
                if self.frozen or self.gated():
                    start_response('503 Service Unavailable', [('Content-Type', 'application/json'), ('Retry-After', '10')])
                    return [b'{"error":"Software maintenance in progress; instrument controls are locked"}']
                self.requests += 1
            try:
                # Materialize responses so streaming hardware operations finish
                # before the maintenance lease acknowledges quiescence.
                response = application(environ, start_response)
                try: return list(response)
                finally:
                    if hasattr(response, 'close'): response.close()
            finally:
                with self.condition:
                    self.requests -= 1; self.condition.notify_all()
        return wsgi

    def check(self):
        if self.tool == 'supply':
            if getattr(self.controller, 'remote_control_enabled', None) is not False:
                raise RuntimeError('In the live HP 6033A dashboard, turn OUTPUT OFF, then disable remote programming and retry. The updater never switches output')
            # Same read-only path used by the controller; a cached display is insufficient.
            try:
                values = self.controller.read_gpib()
            except RuntimeError as error:
                if str(error) == 'Supply queries are paused until the supply is connected to the test bus':
                    return {'connected': False, 'remote_control_enabled': False, 'verified': True}
                raise
            output = values.get('OUT')
            if type(output) not in (int, float) or output != 0:
                raise RuntimeError('In the live HP 6033A dashboard, turn OUTPUT OFF, then disable remote programming and retry. The updater never switches output')
            return {'output': False, 'remote_control_enabled': False, 'verified': True}
        if self.tool == 'meter':
            state = self.meter.snapshot()
            if state.get('polling') is not False or state.get('pending_controls') != 0:
                raise RuntimeError('Pause multimeter acquisition and wait for queued operations to finish')
            if not self.meter.operation_lock.acquire(blocking=False):
                raise RuntimeError('Wait for the current multimeter operation to finish')
            self.meter.operation_lock.release()
            return {'polling': False, 'pending_controls': 0, 'verified': True}
        if self.tool == 'generator':
            # The guard has already drained all controller requests. Updating the
            # web controller must not alter the generator's persistent output state.
            return {'requests': 0, 'verified': True}
        if self.tool == 'scope':
            with self.scope_io.scope() as (instrument, config):
                running = self.scope_io.ask(instrument, 'ACQUIRE:STATE?')
                busy = self.scope_io.ask(instrument, 'BUSY?')
            if running != '0' or busy != '0':
                raise RuntimeError('Stop scope acquisition and finish capture/setup operations, then retry. No scope commands were changed')
            return {'running': False, 'busy': False, 'verified': True}
        raise RuntimeError('Unknown controller maintenance protocol')

    def lease(self, connection):
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        if struct.unpack('3i', credentials)[1] != 0:
            raise RuntimeError('Maintenance lease requires the local root helper')
        connection.settimeout(20)
        stream = connection.makefile('rwb', buffering=0)
        request = stream.readline(256)
        if request == b'{"action":"health","schema":1}\n':
            stream.write(json.dumps({'ok': True, 'schema': 1, 'tool': self.tool, 'gated': self.gated()}).encode()+b'\n')
            return
        if request != b'{"action":"quiesce","schema":1}\n': raise RuntimeError('Invalid maintenance request')
        with self.condition:
            if self.frozen: raise RuntimeError('Another maintenance lease is active')
            self.frozen = True
        try:
            deadline = time.monotonic()+12
            with self.condition:
                while self.requests:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0: raise RuntimeError('Controller operations are still active; wait and retry')
                    self.condition.wait(remaining)
            state = self.check()
            stream.write(json.dumps({'ok': True, 'schema': 1, 'tool': self.tool, 'state': state}).encode()+b'\n')
            # Root keeps the socket open; software restart closes it. No expiry
            # silently opens controls during a slow transaction.
            connection.settimeout(None)
            stream.readline(256)
        finally:
            with self.condition: self.frozen = False; self.condition.notify_all()

    def serve(self, path):
        path = Path(path)
        if path.exists(): path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path)); path.chmod(0o600); server.listen(2)
        def loop():
            while True:
                connection, address = server.accept()
                def work(connection=connection):
                    try: self.lease(connection)
                    except Exception as error:
                        try: connection.sendall(json.dumps({'ok': False, 'error': str(error)}).encode()+b'\n')
                        except OSError: pass
                    finally: connection.close()
                threading.Thread(target=work, daemon=True).start()
        threading.Thread(target=loop, daemon=True).start()

def install(app, tool, controller, meter=None, scope_io=None):
    if 'fischer_maintenance' in app.extensions: raise RuntimeError('Maintenance guard installed twice')
    guard = Guard(tool, controller, meter, scope_io)
    app.wsgi_app = guard.wrap(app.wsgi_app)
    guard.serve('/run/fischer-maintenance-'+tool+'/control.sock')
    app.extensions['fischer_maintenance'] = guard
    return guard
