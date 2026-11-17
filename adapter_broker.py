"""Single shared adapter owner with hard process deadlines and bounded admission."""
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
OPERATIONS = {'adapter': {'inspect', 'discover', 'usb-recover'}, 'supply': {'snapshot', 'set', 'output_off'},
              'meter': {'identify', 'configuration', 'prepare', 'sample', 'single', 'function', 'range', 'digits', 'math', 'menu-read', 'menu-set', 'local'},
              'arduino': {'probe'}}


class Coordinator:
    def __init__(self, config, runner=None):
        self.config = config
        self.lock = threading.Lock()
        self.runner = runner or self.run_worker
        self.stuck_worker = None
        self.usb_generation = self.current_usb_generation()
        self.recover = False
        self.identified = False
        self.configured = False
        self.cooldown_until = 0
        self.last_error = None

    @staticmethod
    def current_usb_generation():
        result = []
        for path in Path('/sys/bus/usb/devices').glob('*'):
            try:
                if ((path/'idVendor').read_text().strip() == '03eb' and
                        (path/'idProduct').read_text().strip() == '2065'):
                    result.append(((path/'busnum').read_text().strip(),
                                   (path/'devnum').read_text().strip()))
            except OSError:
                continue
        return tuple(sorted(result))

    def run_worker(self, payload, timeout):
        proc = subprocess.Popen([sys.executable, str(ROOT/'adapter_worker.py')],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = proc.communicate(json.dumps(payload), timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                _, stderr = proc.communicate(timeout=.3)
            except subprocess.TimeoutExpired:
                # A task in kernel D state cannot be killed yet. Keep its
                # ownership quarantined, but return promptly to all clients.
                self.stuck_worker = proc
                raise TimeoutError('USB driver is stuck; reconnect adapter. Hardware access suspended until the old worker exits.')
            markers = [line for line in stderr.splitlines() if line.startswith('PHASE ')]
            where = markers[-1] if markers else 'worker startup (no I/O phase reached)'
            raise TimeoutError('Transaction deadline exceeded at ' + where)
        if proc.returncode:
            raise RuntimeError('Adapter worker exited unexpectedly')
        response = json.loads(stdout)
        if not response.get('ok') and stderr:
            print(stderr[-3000:], file=sys.stderr, flush=True)
        return response

    def execute(self, req):
        if not isinstance(req, dict):
            return {'ok': False, 'error': 'Expected a transaction object'}
        target, action = req.get('target'), req.get('action')
        if target == 'service' and action == 'status':
            return {'ok': True, 'result': {'hardware_enabled': self.config.get('hardware_enabled', False),
                    'busy': self.lock.locked(), 'identified': self.identified,
                    'configured': self.configured, 'last_error': self.last_error,
                    'meter_read_only': self.config.get('meter_read_only', True),
                    'meter_retry_after': max(0, round(self.cooldown_until-time.monotonic(), 1))}}
        gate=Path('/var/lib/fischer-suite-updater/pending.flag')
        try:
            if gate.exists() and 'firmware' in json.loads(gate.read_text()):
                return {'ok':False,'error':'USB-GPIB firmware maintenance in progress; finish verification before instrument access'}
        except (OSError,ValueError,TypeError):
            return {'ok':False,'error':'Maintenance gate unreadable; hardware access paused'}
        if target not in OPERATIONS or action not in OPERATIONS[target] or not isinstance(req.get('data', {}), dict):
            return {'ok': False, 'error': 'Unsupported transaction'}
        if not self.config.get('hardware_enabled'):
            return {'ok': False, 'error': 'Hardware access is disabled pending coordination checks'}
        if target == 'supply' and not self.config.get('supply_enabled', True):
            return {'ok': False, 'error': 'Supply queries are paused until the supply is connected to the test bus'}
        wait = 3.2 if target == 'supply' else .05
        if not self.lock.acquire(timeout=wait):
            return {'ok': False, 'error': 'Shared adapter busy; try again shortly'}
        try:
            if self.stuck_worker is not None:
                if self.stuck_worker.poll() is None:
                    return {'ok': False, 'error': 'USB driver is stuck; reconnect adapter. No competing hardware connection will be opened.'}
                self.stuck_worker.communicate(timeout=.1)
                self.stuck_worker = None
            generation = self.current_usb_generation()
            if generation != self.usb_generation:
                self.usb_generation = generation
                self.recover = False
                self.identified = self.configured = False
                self.cooldown_until = 0
            if target == 'meter':
                if self.config.get('meter_read_only', False) and action not in ('identify','configuration'):
                    return {'ok': False, 'error': 'Read-only meter verification is active; measurements and configuration changes are not enabled'}
                if time.monotonic() < self.cooldown_until:
                    return {'ok': False, 'error': 'Meter is in a ten-second recovery pause; supply remains available'}
                if action not in ('identify',) and not self.identified:
                    return {'ok': False, 'error': 'Verify meter identity first'}
                if action not in ('identify', 'configuration') and not self.configured:
                    return {'ok': False, 'error': 'Read initial meter configuration first'}
            # Includes a fresh Python/PyVISA startup on the Pi Zero 2 W.
            deadline = 3.0
            response = self.runner({'request': req, 'config': self.config, 'recover': self.recover}, deadline)
            self.recover = not response.get('ok') and response.get('io_failed', True)
            if response.get('ok'):
                self.last_error = None
                if target == 'adapter' and action == 'usb-recover':
                    self.identified = self.configured = False
                    self.cooldown_until = 0
                if target == 'meter':
                    if action == 'identify':
                        self.identified, self.configured = True, False
                    elif action == 'configuration':
                        self.configured = True
            else:
                self.failed(target, response.get('error', 'Adapter transaction failed'), response.get('io_failed', True))
            return response
        except Exception as exc:
            self.failed(target, str(exc))
            return {'ok': False, 'error': str(exc)[:500]}
        finally:
            self.lock.release()

    def failed(self, target, error, needs_recovery=True):
        self.recover = needs_recovery
        self.last_error = error
        if target in ('meter', 'adapter'):
            self.identified = self.configured = False
            self.cooldown_until = time.monotonic() + 10


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(1)
        try:
            raw = self.rfile.readline(4097)
            if len(raw) > 4096 or not raw.endswith(b'\n'):
                raise ValueError('Invalid request size')
            response = self.server.coordinator.execute(json.loads(raw))
        except Exception as exc:
            response = {'ok': False, 'error': str(exc)[:200]}
        self.wfile.write(json.dumps(response, allow_nan=False).encode() + b'\n')


class Server(socketserver.ThreadingMixIn, getattr(socketserver, 'UnixStreamServer', socketserver.TCPServer)):
    daemon_threads = True
    request_queue_size = 8


def main():
    if not hasattr(socketserver, 'UnixStreamServer'):
        raise RuntimeError('The adapter service requires Linux; coordination tests are portable')
    import fcntl
    config = json.loads((ROOT/'config.json').read_text())
    addresses = config['addresses']
    if any(type(v) is not int or not 1 <= v <= 30 for v in addresses.values()) or len(set(addresses.values())) != len(addresses):
        raise ValueError('Every instrument needs a unique GPIB address from 1 to 30')
    path = os.environ.get('FISCHER_GPIB_SOCKET', '/run/fischer-gpib/adapter.sock')
    # Prevent a second service/process from ever opening the same adapter.
    with open(str(Path(path).parent/'owner.lock'), 'a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        Path(path).unlink(missing_ok=True)
        with Server(path, Handler) as server:
            os.chmod(path, 0o660)
            server.coordinator = Coordinator(config)
            server.serve_forever()


if __name__ == '__main__':
    main()
