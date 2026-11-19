"""HP/Agilent 33120A User's Guide, pp.62, 138–151. No direct hardware access."""
import hashlib
import json
import math

FUNCTIONS = {'SIN': 15e6, 'SQU': 15e6, 'TRI': 100e3, 'RAMP': 100e3}
MODES = ('AM', 'FM', 'BM', 'FSK', 'SWE')

def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Use finite numeric values')
    return float(value)

def validate(data):
    if not isinstance(data, dict) or set(data) != {'function','frequency','amplitude','offset','load'}:
        raise ValueError('Provide exactly function, frequency, amplitude, offset and load')
    function = data['function']
    if not isinstance(function, str) or function not in FUNCTIONS:
        raise ValueError('Supported waveforms: SIN, SQU, TRI, RAMP')
    if data['load'] not in ('50', 'INF'):
        raise ValueError('Choose a 50 ohm or high impedance assumed load')
    f, a, o = (numeric(data[k]) for k in ('frequency','amplitude','offset'))
    scale = 1 if data['load'] == '50' else 2
    if not .0001 <= f <= FUNCTIONS[function]:
        raise ValueError('Frequency outside documented waveform limits')
    if not .05 * scale <= a <= 10 * scale:
        raise ValueError('Amplitude outside documented load limits')
    # Printed p.62 explicitly defines Vmax as 5 V (50 ohms), 10 V (open).
    if abs(o) + a/2 > 5*scale or abs(o) > 2*a:
        raise ValueError('Offset must satisfy |offset| + Vpp/2 <= 5 V (50 ohm) or 10 V (high Z), and |offset| <= 2*Vpp')
    return dict(function=function, frequency=f, amplitude=a, offset=o, load=data['load'])

def readback_tolerance(key, requested):
    # Printed p.298: frequency 10 microhertz or 10 digits; voltage 3 digits.
    # Half a setting-resolution step, not the much looser analog accuracy spec.
    if key=='frequency':
        step=max(1e-5,10**(math.floor(math.log10(abs(requested)))-9))
    elif requested:
        step=10**(math.floor(math.log10(abs(requested)))-2)
    else:
        return 1e-12  # Do not invent a nonzero offset tolerance at zero.
    return step/2 + max(1e-12,abs(requested)*1e-14)

def identity(dev):
    value = dev.query('*IDN?').strip()
    parts = value.upper().split(',')
    if len(parts) != 4 or parts[1].strip() != '33120A' or parts[0].strip() not in ('HEWLETT-PACKARD','AGILENT TECHNOLOGIES','KEYSIGHT TECHNOLOGIES'):
        raise RuntimeError('Expected an HP/Agilent/Keysight 33120A; no settings written')
    return value

def read_number(dev, command):
    return numeric(float(dev.query(command)))

def snapshot(dev):
    result = {'identity': identity(dev), 'function': dev.query('FUNC:SHAP?').strip(),
              'frequency': read_number(dev,'FREQ?'), 'amplitude': read_number(dev,'VOLT?'),
              'offset': read_number(dev,'VOLT:OFFS?'), 'unit': dev.query('VOLT:UNIT?').strip()}
    load = read_number(dev, 'OUTP:LOAD?')
    if load != 50 and load != 9.9e37:
        raise RuntimeError('Unexpected load readback')
    result['load'] = '50' if load == 50 else 'INF'
    result['modes'] = {mode: dev.query(mode+':STAT?').strip() for mode in MODES}
    if any(v not in ('0','1') for v in result['modes'].values()):
        raise RuntimeError('Unexpected mode readback')
    result['trigger'] = dev.query('TRIG:SOUR?').strip()
    result['duty'] = read_number(dev, 'PULS:DCYC?')
    result['token'] = hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return result

def check_error(dev):
    error = dev.query('SYST:ERR?').strip()
    if error.split(',')[0].strip() not in ('0','+0'):
        raise RuntimeError('Instrument error (oldest error consumed): '+error)

def execute(dev, action, data):
    if action in ('sweep_start','sweep_stop'):
        return sweep_switch(dev,action,data)
    if action in ('sweep_configuration','sweep_apply'):
        return sweep_execute(dev, action, data)
    if action == 'identify':
        return {'identity': identity(dev)}
    if action == 'configuration':
        return snapshot(dev)
    if action != 'apply':
        raise ValueError('Unsupported generator action')
    if data.get('confirm_output_change') is not True:
        raise ValueError('Explicit output-change acknowledgment required')
    desired = validate(data.get('settings'))  # Validate before any I/O.
    before = snapshot(dev)  # Identity and safety state are always checked inside the broker lock.
    expected_token = data.get('expected_token')
    if expected_token is not None and expected_token != before['token']:
        raise RuntimeError('Configuration changed since the last read; Apply stopped before writing. Review and click Apply again')
    if any(v != '0' for v in before['modes'].values()) or before['trigger'] != 'IMM':
        raise RuntimeError('First version requires modulation, burst and sweep off and immediate triggering; no settings written')
    check_error(dev)  # Do not clear pre-existing errors silently.
    try:
        dev.write('OUTP:LOAD '+desired['load'])
        check_error(dev)
        dev.write('VOLT:UNIT VPP')
        check_error(dev)
        dev.write('APPL:{function} {frequency:.12g},{amplitude:.12g},{offset:.12g}'.format(**desired))
        check_error(dev)
        actual = snapshot(dev)
        if actual['function'] != desired['function'] or actual['load'] != desired['load'] or actual['unit'] != 'VPP':
            raise RuntimeError('Configuration readback mismatch')
        validate({key:actual[key] for key in desired})
        for key in ('frequency','amplitude','offset'):
            if abs(actual[key]-desired[key]) > readback_tolerance(key,desired[key]):
                raise RuntimeError(key+' readback mismatch')
        if any(v != '0' for v in actual['modes'].values()) or actual['trigger'] != 'IMM' or (desired['function']=='SQU' and actual['duty'] != 50):
            raise RuntimeError('Mode or duty readback mismatch')
        return actual
    except Exception as exc:
        raise RuntimeError('Apply may have partially changed the active output; no automatic retry or rollback. Read configuration. '+str(exc)) from exc


def validate_sweep(data, function='SIN'):
    if not isinstance(data, dict) or set(data) != {'start','stop','time','spacing'}:
        raise ValueError('Provide exactly start, stop, time and spacing')
    if function not in FUNCTIONS or data['spacing'] not in ('LIN','LOG'):
        raise ValueError('Supported waveform and LIN or LOG spacing required')
    result={k:numeric(data[k]) for k in ('start','stop','time')}
    if not all(.01 <= result[k] <= FUNCTIONS[function] for k in ('start','stop')):
        raise ValueError('Sweep frequencies require 0.01 Hz to waveform maximum')
    if result['start']==result['stop']:
        raise ValueError('Sweep start and stop must differ')
    if not .001 <= result['time'] <= 500:
        raise ValueError('Sweep time must be 0.001 to 500 seconds')
    return dict(result,spacing=data['spacing'])

def sweep_snapshot(dev):
    result=snapshot(dev)
    result['configuration_token']=result['token']
    result['sweep']={k:read_number(dev,c) for k,c in [('start','FREQ:STAR?'),('stop','FREQ:STOP?'),('time','SWE:TIME?')]}
    result['sweep']['spacing']=dev.query('SWE:SPAC?').strip()
    del result['token']
    result['token']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    if result['modes']['SWE']=='1':
        # Manual does not specify FREQ? stability during sweep. Only Stop may
        # ignore this potentially dynamic value; all configured settings remain.
        stable={k:v for k,v in result.items() if k not in ('token','frequency')}
        result['stop_token']=hashlib.sha256(b'sweep-stop-v1:'+json.dumps(stable,sort_keys=True).encode()).hexdigest()
    return result

def sweep_execute(dev, action, data):
    if action=='sweep_configuration':return sweep_snapshot(dev)
    if data.get('confirm_output_change') is not True:
        raise ValueError('Explicit sweep setup acknowledgment required')
    desired=validate_sweep(data.get('settings'))
    before=sweep_snapshot(dev)
    expected_token=data.get('expected_token')
    if expected_token is not None and expected_token!=before['token']:
        raise RuntimeError('Configuration changed; read sweep configuration and review again')
    if any(v!='0' for v in before['modes'].values()) or before['trigger']!='IMM' or before['unit']!='VPP':
        raise RuntimeError('Sweep setup requires all modes OFF, immediate trigger and Vpp; no settings written')
    validate({k:before[k] for k in ('function','frequency','amplitude','offset','load')})
    validate_sweep(desired,before['function'])
    check_error(dev)
    try:
        for command,value in [('FREQ:STAR',desired['start']),('FREQ:STOP',desired['stop']),('SWE:TIME',desired['time']),('SWE:SPAC',desired['spacing'])]:
            dev.write(command+' '+(value if isinstance(value,str) else format(value,'.12g')))
            check_error(dev)
        actual=sweep_snapshot(dev)
        # Setup must not alter waveform, amplitude, load, mode or trigger state.
        for key in before.keys()-{'token','sweep'}:
            if actual[key]!=before[key]:raise RuntimeError(key+' changed during sweep setup')
        validate_sweep(actual['sweep'],actual['function'])
        for key in desired:
            wanted=desired[key];got=actual['sweep'][key]
            tolerance=readback_tolerance('frequency',wanted) if key in ('start','stop') else 1e-12
            if (got!=wanted if isinstance(wanted,str) else abs(got-wanted)>tolerance):
                raise RuntimeError('Sweep '+key+' readback mismatch')
        return actual
    except Exception as exc:
        raise RuntimeError('Sweep setup may be partial; no automatic retry or rollback. Read configuration. '+str(exc)) from exc


def sweep_switch(dev, action, data):
    if data.get('confirm_output_change') is not True:
        raise ValueError('Explicit sweep action acknowledgment required')
    before=sweep_snapshot(dev)
    starting=action=='sweep_start'
    expected=before['token'] if starting else before.get('stop_token')
    if not starting and before['modes']['SWE']=='0':
        return before
    expected_token=data.get('expected_token')
    if expected_token is not None and (expected is None or expected_token!=expected):
        raise RuntimeError('Configuration changed; read sweep configuration and review again')
    if before['modes']['SWE']!=('0' if starting else '1'):
        raise RuntimeError('Sweep is not in the expected state; no command sent')
    if starting:
        if any(v!='0' for v in before['modes'].values()) or before['trigger']!='IMM' or before['unit']!='VPP':
            raise RuntimeError('Start requires all modes OFF, IMM trigger and Vpp; no command sent')
        validate({k:before[k] for k in ('function','frequency','amplitude','offset','load')})
        validate_sweep(before['sweep'],before['function'])
    check_error(dev)
    try:
        dev.write('SWE:STAT '+('ON' if starting else 'OFF'))
        check_error(dev)
        actual=sweep_snapshot(dev)
        expected=dict(before['modes'],SWE='1' if starting else '0')
        if actual['modes']!=expected:raise RuntimeError('Sweep state readback mismatch')
        for key in ('identity','function','amplitude','offset','load','unit','trigger','duty','sweep'):
            if actual[key]!=before[key]:raise RuntimeError(key+' changed during sweep action')
        return actual
    except Exception as exc:
        raise RuntimeError('Sweep/output state unknown after possible write; no automatic retry or rollback. Read sweep configuration; physically isolate output if needed. '+str(exc)) from exc
