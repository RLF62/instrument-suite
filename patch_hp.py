"""Patch only hardware entry points; preserve auth, settings, presets and dashboards."""
import ast
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()
if 'FISCHER_SHARED_ADAPTER_V1' in source:
    print('HP adapter integration already installed')
    raise SystemExit(0)
tree = ast.parse(source)
replacements = {
 'read_gpib': '''def read_gpib():
    return suite_execute('supply', 'snapshot')
''',
 'write_gpib_setting': '''def write_gpib_setting(key, value):
    with control_lock:
        if not remote_control_enabled and not (key == 'output' and value is False):
            raise PermissionError('Remote control is disabled')
        if key in ('voltage', 'current'):
            if isinstance(value, bool):
                raise ValueError('Invalid numeric setting')
            value = float(value)
            maximum = MAX_REMOTE_VOLTAGE if key == 'voltage' else MAX_REMOTE_CURRENT
            if not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError('Setting exceeds remote-control safety limit')
        elif key != 'output' or type(value) is not bool:
            raise ValueError('Unsupported supply setting')
        return suite_execute('supply', 'set', key=key, value=value)
''',
 'output_off_only': '''def output_off_only():
    global remote_control_enabled
    with control_lock:
        try:
            suite_execute('supply', 'output_off')
        except Exception as exc:
            remote_control_enabled = False
            return jsonify(error=str(exc)[:180]), 503
    return jsonify(success=True, output=False, message='Power supply output confirmed OFF')
''',
 'arduino_probe': '''def arduino_probe():
    try:
        return suite_execute('arduino', 'probe')
    except Exception as exc:
        return {'connected':False,'port':SERIAL_PORT,'firmware':None,'response_ms':None,'error':str(exc)[:180]}
''',
}
lines = source.splitlines(keepends=True)
found = set()
for node in sorted((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
                   key=lambda n: n.lineno, reverse=True):
    if node.name in replacements:
        lines[node.lineno-1:node.end_lineno] = [replacements[node.name]]
        found.add(node.name)
if found != set(replacements):
    raise RuntimeError('Unexpected HP source; missing ' + repr(set(replacements)-found))
source = ''.join(lines)
header = '''# FISCHER_SHARED_ADAPTER_V1
import sys
sys.path.insert(0, '/home/pi/instrument-suite')
from gpib_client import execute as suite_execute
'''
source = header + source
# Timestamp successful supply snapshots without changing instrument commands.
source = source.replace("'measured_power':0.0}", "'measured_power':0.0, 'sample_time':time.time()}")
# DMM authentication uses the existing policy, without holding the supply's control mutex.
needle = "    # Serialize authorization and instrument operations with mode changes."
assert source.count(needle) == 1
source = source.replace(needle, '''    if request.path.startswith('/api/control/meter/'):
        if request.headers.get('Origin') != request.host_url.rstrip('/'):
            return jsonify(error='Request origin did not match the controller'), 403
        if control_password_required() and not valid_control_credentials():
            return jsonify(error='Invalid or missing credentials'), 401
        return None

''' + needle)
needle = "if __name__=='__main__':"
assert source.count(needle) == 1
source = source.replace(needle, "from hp34401a import install as install_meter\ninstall_meter(app)\n\n" + needle)
ast.parse(source)
assert 'ResourceManager' not in source and 'serial.Serial' not in source
path.write_text(source)
print('Patched HP app: all hardware access goes through shared adapter service')
