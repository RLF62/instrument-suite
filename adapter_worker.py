"""One bounded transaction. Only the broker is permitted to launch this worker.

UsbGpib V2.4+: internal-command pulse + !addr precede every transaction.
No *RST, bus reset, nonvolatile adapter writes, or unaddressed instrument writes.
"""
import json
import math
import re
import sys
from pathlib import Path
import time
import traceback
CURRENT_PHASE = 'worker startup'


def trace(operation):
    global CURRENT_PHASE
    CURRENT_PHASE = operation
    print('PHASE ' + operation, file=sys.stderr, flush=True)


class TracedDevice:
    def __init__(self, device, target):
        self.device, self.target = device, target

    def query(self, command):
        trace(self.target + ' query: ' + command)
        return self.device.query(command)

    def write(self, command):
        trace(self.target + ' write: ' + command)
        return self.device.write(command)

    def __getattr__(self, name):
        return getattr(self.device, name)

FUNCTIONS = {
    'dcv': ('VOLT:DC', 'V'), 'acv': ('VOLT:AC', 'V'),
    'dci': ('CURR:DC', 'A'), 'aci': ('CURR:AC', 'A'),
    'ohm2': ('RES', 'Ω'), 'ohm4': ('FRES', 'Ω'),
    'freq': ('FREQ', 'Hz'), 'period': ('PER', 's'),
    'continuity': ('CONT', 'Ω'), 'diode': ('DIOD', 'V'),
    'ratio': ('VOLT:DC:RAT', 'ratio'),
}
CANONICAL = {'VOLTAGE:DC': 'dcv', 'VOLTAGE:AC': 'acv',
             'CURRENT:DC': 'dci', 'CURRENT:AC': 'aci',
             'RESISTANCE': 'ohm2', 'FRESISTANCE': 'ohm4',
             'FREQUENCY': 'freq', 'PERIOD': 'period',
             'CONTINUITY': 'continuity', 'DIODE': 'diode'}
CANONICAL['VOLTAGE:DC:RATIO'] = 'ratio'
CANONICAL.update({'VOLT':'dcv','VOLTAGE':'dcv','CURR':'dci','CURRENT':'dci',
                  'VOLT:RAT':'ratio','VOLT:RATIO':'ratio','VOLTAGE:RATIO':'ratio'})
RANGES = {'dcv': [.1, 1, 10, 100, 1000], 'acv': [.1, 1, 10, 100, 750],
          'dci': [.01, .1, 1, 3], 'aci': [1, 3],
          'ohm2': [100, 1000, 10000, 100000, 1000000, 10000000, 100000000],
          'ohm4': [100, 1000, 10000, 100000, 1000000, 10000000, 100000000],
          'freq': [.1, 1, 10, 100, 750], 'period': [.1, 1, 10, 100, 750]}


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Instrument returned a non-finite number')
    return result


def function_key(reply):
    text = reply.strip().strip('"').upper()
    if text in CANONICAL:
        return CANONICAL[text]
    for key, (command, _) in FUNCTIONS.items():
        if text == command:
            return key
    raise ValueError('Unsupported meter function: ' + text)


def range_command(key):
    cmd = FUNCTIONS[key][0]
    return cmd + ':VOLT' if key in ('freq', 'period') else cmd


def config_readback(dev):
    key = function_key(dev.query('FUNC?'))
    result = {'function': key, 'unit': FUNCTIONS[key][1],
              'trigger_source': dev.query('TRIG:SOUR?').strip(),
              'trigger_count': number(dev.query('TRIG:COUN?')),
              'sample_count': number(dev.query('SAMP:COUN?')),
              'trigger_delay': number(dev.query('TRIG:DEL?')),
              'math': dev.query('CALC:FUNC?').strip().upper(),
              'math_enabled': bool(int(dev.query('CALC:STAT?')))}
    result['terminals'] = dev.query('ROUT:TERM?').strip()
    if key in RANGES:
        cmd = range_command(key)
        result.update(range=number(dev.query(cmd + ':RANG?')),
                      autorange=bool(int(dev.query(cmd + ':RANG:AUTO?'))))
    if key in ('dcv', 'dci', 'ohm2', 'ohm4', 'ratio'):
        result['nplc'] = number(dev.query(('VOLT:DC' if key=='ratio' else FUNCTIONS[key][0]) + ':NPLC?'))
    if key in ('dcv', 'acv', 'dci', 'aci', 'ohm2', 'ohm4'):
        result['resolution'] = number(dev.query(FUNCTIONS[key][0] + ':RES?'))
    if key in ('freq', 'period'):
        result['aperture'] = number(dev.query(FUNCTIONS[key][0] + ':APER?'))
    if result['math_enabled']:
        query = {'NULL': 'CALC:NULL:OFFS?', 'DB': 'CALC:DB:REF?', 'DBM': 'CALC:DBM:REF?'}
        if result['math'] in query:
            result['math_reference'] = number(dev.query(query[result['math']]))
    return result


def check_error(dev):
    error = dev.query('SYST:ERR?').strip()
    try:
        code = int(error.split(',', 1)[0])
    except ValueError:
        raise RuntimeError('Invalid error readback: ' + error)
    if code:
        raise RuntimeError('Meter reports ' + error)


def meter(dev, action, data):
    if action == 'identify':
        identity = dev.query('*IDN?').strip()
        fields = identity.split(',')
        if len(fields) < 3 or fields[1].strip().upper() != '34401A':
            raise RuntimeError('Expected HP 34401A; received ' + identity)
        return {'identity': identity}
    if action == 'configuration':
        return config_readback(dev)
    if action == 'prepare':
        # Explicit operator action; identity and initial configuration precede this.
        dev.write('TRIG:SOUR IMM;:TRIG:COUN 1;:SAMP:COUN 1;:TRIG:DEL 0')
        check_error(dev)
        return config_readback(dev)
    if action in ('sample', 'single'):
        # Recheck trigger settings in the SAME transaction before READ?.
        key = function_key(dev.query('FUNC?'))
        source = dev.query('TRIG:SOUR?').strip().upper()
        count = number(dev.query('TRIG:COUN?'))
        samples = number(dev.query('SAMP:COUN?'))
        delay = number(dev.query('TRIG:DEL?'))
        if count != 1 or samples != 1 or delay > .2:
            raise RuntimeError('Web acquisition requires one trigger, one sample and delay ≤0.2 s; use the Trigger menu')
        if action == 'sample' and source != 'IMM':
            raise RuntimeError('Automatic web updates require immediate triggering')
        if source == 'BUS' and action == 'single':
            dev.write('INIT'); time.sleep(.025); dev.write('*TRG')
            value = number(dev.query('FETC?'))
        elif source == 'EXT' and action == 'single':
            dev.write('INIT')
            value = number(dev.query('FETC?'))  # Bounded wait; requires a real external pulse.
        elif source == 'IMM':
            value = number(dev.query('READ?'))
        else:
            raise RuntimeError('Unsupported trigger source')
        math_enabled = bool(int(dev.query('CALC:STAT?')))
        math_mode = dev.query('CALC:FUNC?').strip().upper()
        unit = math_mode.lower().replace('dbm', 'dBm').replace('db', 'dB') if math_enabled and math_mode in ('DB','DBM') else FUNCTIONS[key][1]
        overloaded = abs(value) >= 9e37
        return {'value': None if overloaded else value, 'overload': overloaded,
                'function': key, 'unit': unit, 'math_enabled': math_enabled,
                'math': math_mode, 'sample_time': time.time()}
    if action == 'function':
        key = data.get('function')
        if key not in FUNCTIONS:
            raise ValueError('Unsupported function')
        dev.write('FUNC "' + FUNCTIONS[key][0] + '"')
    elif action == 'range':
        key = function_key(dev.query('FUNC?'))
        if key not in RANGES:
            raise ValueError('This function has a fixed range')
        cmd = range_command(key)
        direction = data.get('direction')
        if direction == 'toggle':
            enabled = bool(int(dev.query(cmd + ':RANG:AUTO?')))
            dev.write(cmd + ':RANG:AUTO ' + ('OFF' if enabled else 'ON'))
        elif direction == 'auto':
            dev.write(cmd + ':RANG:AUTO ON')
        elif direction in ('up', 'down'):
            old = number(dev.query(cmd + ':RANG?'))
            ranges = RANGES[key]
            index = min(range(len(ranges)), key=lambda i: abs(ranges[i] - old))
            index = max(0, min(len(ranges)-1, index + (1 if direction == 'up' else -1)))
            dev.write(cmd + ':RANG ' + str(ranges[index]))
        else:
            raise ValueError('Invalid range direction')
    elif action == 'digits':
        key = function_key(dev.query('FUNC?'))
        digits = str(data.get('digits'))
        if digits not in ('4','5','6'):
            raise ValueError('Choose 4½, 5½ or 6½ digits')
        cmd = FUNCTIONS[key][0]
        if key in ('dcv', 'dci', 'ohm2', 'ohm4', 'ratio'):
            # Manual pp.54–56: the panel DIGITS shortcuts are 1, 10, 10 PLC.
            # Five and six digits share 10 PLC; the web display masks digits separately.
            dev.write(('VOLT:DC' if key=='ratio' else cmd) + ':NPLC ' + {'4':'1','5':'10','6':'10'}[digits])
        elif key in ('acv', 'aci'):
            # This connected HP firmware rejects the coarse AC RES requests
            # with -221. AC integration is fixed; expose an explicit web mask.
            pass
        elif key in ('freq','period'):
            dev.write(cmd + ':APER ' + {'4':'.01','5':'.1','6':'1'}[digits])
        else:
            raise ValueError('Continuity and diode resolution are fixed at 5½ digits')
    elif action == 'math':
        mode = data.get('mode')
        if mode == 'off':
            dev.write('CALC:STAT OFF')
        elif mode in ('null', 'minmax', 'db', 'dbm', 'limit'):
            key = function_key(dev.query('FUNC?'))
            if key in ('continuity', 'diode', 'ratio'):
                raise ValueError('This web math control is unavailable in continuity, diode and ratio functions')
            if mode in ('db','dbm') and key not in ('dcv','acv'):
                raise ValueError('dB and dBm require DC or AC voltage')
            if mode in ('db','dbm','minmax') and key == 'ratio':
                raise ValueError('This math function is unavailable for ratio')
            requested = {'null':'NULL','minmax':'AVER','db':'DB','dbm':'DBM','limit':'LIM'}[mode]
            current = dev.query('CALC:FUNC?').strip().upper()
            enabled = bool(int(dev.query('CALC:STAT?')))
            if current == requested and enabled and data.get('toggle', True):
                dev.write('CALC:STAT OFF')
            else:
                dev.write('CALC:FUNC ' + requested + ';:CALC:STAT ON')
        else:
            raise ValueError('Unsupported math mode')
    elif action == 'menu-read':
        return menu_read(dev, data.get('item'))
    elif action == 'menu-set':
        return menu_set(dev, data.get('item'), data.get('value'))
    else:
        raise ValueError('Unsupported meter action')
    check_error(dev)
    result = config_readback(dev)
    if action == 'digits':
        result['digits_effect'] = 'web display mask only; AC conversion unchanged' if key in ('acv','aci') else 'instrument timing read back; web display mask selected separately'
    return result


# Explicit web menu: a finite command allowlist, never arbitrary SCPI input.
MENU = {
    'ac-filter': ('DET:BAND', [3,20,200]),
    'input-r': ('INP:IMP:AUTO', [0,1]), 'autozero': ('ZERO:AUTO', [0,1]),
    'trigger-source': ('TRIG:SOUR', ['IMM','BUS','EXT']),
    'trigger-delay': ('TRIG:DEL', (0,3600)),
    'trigger-auto-delay': ('TRIG:DEL:AUTO', [0,1]),
    'sample-count': ('SAMP:COUN', (1,50000)), 'trigger-count': ('TRIG:COUN', (1,50000)),
    'null-offset': ('CALC:NULL:OFFS', None), 'db-reference': ('CALC:DB:REF', (-200,200)),
    'dbm-reference': ('CALC:DBM:REF', [50,75,93,110,124,125,135,150,250,300,500,600,800,900,1000,1200,8000]),
    'limit-low': ('CALC:LIM:LOW', None), 'limit-high': ('CALC:LIM:UPP', None),
    'beeper': ('SYST:BEEP:STAT', [0,1]), 'display': ('DISP', [0,1]),
}


def menu_read(dev, item):
    if item == 'minmax':
        count = int(number(dev.query('CALC:AVER:COUN?')))
        if not count:
            return {'item':item, 'value': {'count':0}}
        return {'item':item, 'value': {'count':count, 'min':number(dev.query('CALC:AVER:MIN?')),
                                     'max':number(dev.query('CALC:AVER:MAX?')), 'mean':number(dev.query('CALC:AVER:AVER?'))}}
    if item == 'error':
        return {'item':item, 'value':dev.query('SYST:ERR?').strip(), 'note':'Reads and removes the oldest meter error.'}
    if item == 'revision':
        return {'item':item, 'value':dev.query('*IDN?').strip()}
    if item == 'scpi-version':
        return {'item':item, 'value':dev.query('SYST:VERS?').strip()}
    if item == 'terminals':
        return {'item':item, 'value':dev.query('ROUT:TERM?').strip(), 'note':'Physical selector readback only.'}
    if item not in MENU:
        raise ValueError('Unsupported web menu item')
    cmd,_ = MENU[item]
    value = dev.query(cmd+'?').strip()
    return {'item':item, 'value': value}


def menu_set(dev, item, value):
    if item not in MENU:
        raise ValueError('This menu item is read-only')
    cmd, limits = MENU[item]
    if isinstance(limits,list) and isinstance(limits[0],str):
        if value not in limits:
            raise ValueError('Invalid menu choice')
    else:
        value = number(value)
        if isinstance(limits,list) and value not in limits:
            raise ValueError('Invalid menu choice')
        if isinstance(limits,tuple) and not limits[0] <= value <= limits[1]:
            raise ValueError('Value outside the documented range')
        if item in ('sample-count','trigger-count') and value != int(value):
            raise ValueError('Count must be an integer')
    if item == 'null-offset' and dev.query('CALC:FUNC?').strip() != 'NULL':
        raise ValueError('Enable Null before changing its offset')
    if item == 'db-reference' and dev.query('CALC:FUNC?').strip() != 'DB':
        raise ValueError('Enable dB before changing its reference')
    dev.write(cmd+' '+str(value))
    check_error(dev)
    result = menu_read(dev,item)
    if isinstance(value,(int,float)):
        if not math.isclose(number(result['value']),value,rel_tol=1e-6,abs_tol=1e-12):
            raise RuntimeError('Meter menu readback does not match requested value')
    elif result['value'].strip() != value:
        raise RuntimeError('Meter menu readback does not match requested choice')
    result['configuration'] = config_readback(dev)
    return result


def supply(dev, action, data):
    def ask(name):
        parts = dev.query(name + '?').strip().split()
        if len(parts) != 2 or parts[0].upper() != name:
            raise RuntimeError('Invalid supply ' + name + ' readback')
        return number(parts[1])
    if action == 'snapshot':
        return {key: ask(key) for key in ('VSET', 'ISET', 'VOUT', 'IOUT', 'OUT', 'STS')}
    if action in ('set', 'output_off'):
        key, value = ('output', False) if action == 'output_off' else (data.get('key'), data.get('value'))
        if key in ('voltage', 'current'):
            maximum = 20 if key == 'voltage' else 30
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError('Supply setting out of bounds')
            if ask('OUT') != 0:
                raise RuntimeError('Supply output must be confirmed OFF before programming')
            name = 'VSET' if key == 'voltage' else 'ISET'
            instruction, expected = f'{name} {value:.3f}', value
        elif key == 'output' and type(value) is bool:
            if value:
                if not 0 <= ask('VSET') <= 20 or not .001 <= ask('ISET') <= 30 or ask('OUT') != 0:
                    raise RuntimeError('Supply output-on prerequisites failed')
            name, instruction, expected = 'OUT', 'OUT ON' if value else 'OUT OFF', int(value)
        else:
            raise ValueError('Unsupported supply control')
        dev.write(instruction)
        actual = ask(name)
        if abs(actual - expected) > .005:
            raise RuntimeError('Supply readback mismatch')
        return actual
    raise ValueError('Unsupported supply action')


def usb_interface(rm, dev):
    # PyVISA-py 0.8 does not implement viUsbControlIn or viClear for USB.
    # Reuse its already-owned PyUSB handle; never open a competing USB handle.
    return rm.visalib.sessions[dev.session].interface


def pulse(rm, dev):
    interface = usb_interface(rm, dev)
    return interface.usb_dev.ctrl_transfer(0xa1, 0x40, 0, interface.usb_intf.index, 1, timeout=600)


def recover_usb(rm, dev):
    interface = usb_interface(rm, dev)
    usb = interface.usb_dev
    index = interface.usb_intf.index
    reply = usb.ctrl_transfer(0xa1, 5, 0, index, 1, timeout=400)
    if not reply or reply[0] != 1:
        raise RuntimeError('Adapter refused USBTMC recovery')
    deadline = time.monotonic() + .6
    while time.monotonic() < deadline:
        status = usb.ctrl_transfer(0xa1, 6, 0, index, 2, timeout=100)
        if len(status) < 2:
            raise RuntimeError('Invalid USBTMC recovery status')
        if status[1] & 1:
            try:
                interface.usb_recv_ep.read(interface.usb_recv_ep.wMaxPacketSize, timeout=100)
            except Exception:
                pass
        if status[0] == 1:
            usb.clear_halt(interface.usb_recv_ep.bEndpointAddress)
            usb.clear_halt(interface.usb_send_ep.bEndpointAddress)
            return
        if status[0] != 2:
            raise RuntimeError('USBTMC recovery failed')
        time.sleep(.01)
    raise TimeoutError('USBTMC recovery exceeded its deadline')


def counter_line(dev):
    # The 5385A sends at most 17 data characters plus CR/LF. Requesting the
    # default large PyVISA chunk makes UsbGpib wait past the instrument reply.
    parts = bytearray()
    for _ in range(32):
        chunk = dev.read_bytes(1)
        parts.extend(chunk)
        if chunk == b'\n':
            break
    else:
        raise RuntimeError('Counter reply exceeded 32 bytes without LF')
    return parts.decode('ascii').strip()


def dispatch_instrument(dev, target, action, data):
    if target == 'counter' and action == 'control':
        choices = {'mode': {'check': 'CK', 'freq_a': 'FU1', 'period_a': 'FU2', 'freq_b': 'FU3'},
                   'gate': {'0.1': 'GA1', '1': 'GA2', '10': 'GA3'},
                   'attenuation': {'off': 'AT0', 'on': 'AT1'},
                   'filter': {'off': 'FI0', 'on': 'FI1'},
                   'reset': {'now': 'RE'}, 'initialize': {'now': 'IN'}}
        if set(data) != {'control', 'value'} or data['control'] not in choices or data['value'] not in choices[data['control']]:
            raise ValueError('Unsupported counter control')
        command = choices[data['control']][data['value']]
        interface = dev.device.visalib.sessions[dev.device.session].interface
        before = interface.usb_dev.ctrl_transfer(0xa1, 0x80, 1, interface.usb_intf.index, 3, timeout=1800)
        if len(before) != 3 or before[0] != 1 or before[1] != 1:
            raise RuntimeError('Counter status unavailable before command')
        if int(before[2]) & 4:
            raise RuntimeError('Counter ERROR is on; press physical RESET/LOCAL before sending commands')
        # CHECK twice enters a diagnostic sequence on this model. Select a
        # measurement function first so every web CHECK is a single CHECK.
        commands = ('FU1', 'CK') if command == 'CK' else (command,)
        for item in commands:
            dev.write(item)
            time.sleep(.2)
            poll = interface.usb_dev.ctrl_transfer(0xa1, 0x80, 1, interface.usb_intf.index, 3, timeout=1800)
            if len(poll) != 3 or poll[0] != 1 or poll[1] != 1:
                raise RuntimeError('Counter status unavailable after command')
            if int(poll[2]) & 4:
                raise RuntimeError('Counter rejected ' + item + '; press physical RESET/LOCAL and inspect the displayed error')
        return {'command': ', '.join(commands), 'control': data['control'], 'value': data['value']}
    if target == 'counter' and action == 'error':
        dev.write('SE')
        return {'error_code': counter_line(dev)}
    if target == 'counter' and action == 'id_request':
        dev.write('ID')
        return {'id_requested': True}
    if target == 'counter' and action == 'status':
        import usb.core
        interface = dev.device.visalib.sessions[dev.device.session].interface
        reply = interface.usb_dev.ctrl_transfer(0xa1, 0x80, 1, interface.usb_intf.index, 3, timeout=1800)
        if len(reply) != 3 or reply[0] != 1 or reply[1] != 1:
            raise RuntimeError('Unexpected USB488 status response: ' + repr(list(reply)))
        return {'status_byte': int(reply[2])}
    if target == 'counter' and action == 'check':
        dev.write('CK')
        return {'check_requested': True}
    if target == 'counter' and action == 'sample':
        interface = dev.device.visalib.sessions[dev.device.session].interface
        poll = interface.usb_dev.ctrl_transfer(0xa1, 0x80, 1, interface.usb_intf.index, 3, timeout=1800)
        if len(poll) != 3 or poll[0] != 1 or poll[1] != 1:
            raise RuntimeError('Unexpected counter status response')
        status = int(poll[2])
        if status & 4:
            return {'ready': False, 'status_byte': status, 'error': 'Counter ERROR is on; press physical RESET/LOCAL and check the display'}
        # The 5385A can return a current measurement even with DATA READY clear.
        # A direct addressed read follows the manual's measurement example.
        if data.get('mode') == 'freq_b' and not status & 1:
            return {'ready': False, 'status_byte': status, 'message': 'Waiting for Input B measurement'}
        try:
            raw = counter_line(dev)
        except Exception as exc:
            import pyvisa
            if isinstance(exc, pyvisa.errors.VisaIOError) and exc.error_code == pyvisa.constants.StatusCode.error_timeout:
                return {'ready': False, 'status_byte': status, 'message': 'Waiting for counter measurement'}
            raise
        match = re.fullmatch(r'([FP])\s*([+-]\d+(?:\.\d+)?E[+-]\d+)', raw)
        if not match:
            raise RuntimeError('Unexpected counter reading: ' + repr(raw))
        value = float(match.group(2))
        if not math.isfinite(value):
            raise RuntimeError('Counter returned a non-finite reading')
        return {'ready': True, 'status_byte': status, 'raw': raw, 'kind': 'frequency' if match.group(1) == 'F' else 'period',
                'value': value, 'unit': 'Hz' if match.group(1) == 'F' else 's'}
    if target == 'counter' and action == 'identify':
        dev.write('ID')
        identity = counter_line(dev)
        if identity.replace(' ', '').upper() != 'HP5385A':
            raise RuntimeError('Unexpected counter identity: ' + repr(identity))
        return {'identity': identity}
    if target == 'meter': return meter(dev, action, data)
    if target == 'supply': return supply(dev, action, data)
    if target == 'generator':
        component_root = Path(__file__).resolve().parent.parent / 'hp33120a'
        component_protocol = component_root / 'hp33120a' / 'protocol.py'
        if component_protocol.is_file():
            component_path = str(component_root)
            if component_path not in sys.path:
                sys.path.insert(0, component_path)
        from hp33120a.protocol import execute
        return execute(dev, action, data)
    raise ValueError('Unsupported instrument target')


def hardware(payload):
    trace('import PyVISA')
    import pyvisa
    import usb.core
    original_control_transfer = usb.core.Device.ctrl_transfer

    def traced_control_transfer(device, bmRequestType, bRequest, wValue=0, wIndex=0,
                                data_or_wLength=None, timeout=None):
        trace(f'USB control transfer type=0x{bmRequestType:02x} request=0x{bRequest:02x} value=0x{wValue:04x} index={wIndex}')
        return original_control_transfer(device, bmRequestType, bRequest, wValue, wIndex,
                                         data_or_wLength, timeout=600 if timeout is None else timeout)

    usb.core.Device.ctrl_transfer = traced_control_transfer
    # Read only Linux-cached identity for this exact USB bus/address. Avoid the
    # adapter's unreliable repeated USB string/language descriptor requests.
    from pathlib import Path
    original_serial = usb.core.Device.serial_number
    def cached_serial(device):
        if device.idVendor == 0x03eb and device.idProduct == 0x2065:
            for path in Path('/sys/bus/usb/devices').iterdir():
                try:
                    if (int((path/'busnum').read_text()) == device.bus and
                            int((path/'devnum').read_text()) == device.address and
                            (path/'idVendor').read_text().strip() == '03eb' and
                            (path/'idProduct').read_text().strip() == '2065'):
                        value = (path/'serial').read_text().strip()
                        if value:
                            return value
                except (OSError, ValueError):
                    continue
            raise RuntimeError('USB adapter no longer enumerated; reconnect its USB cable')
        return original_serial.fget(device)
    usb.core.Device.serial_number = property(cached_serial)
    cfg, req = payload['config'], payload['request']
    target, action, data = req['target'], req['action'], req.get('data', {})
    if target == 'arduino':
        import serial
        started = time.monotonic()
        with serial.Serial(cfg.get('arduino_port', '/dev/ttyACM0'), 115200,
                           timeout=.6, write_timeout=.6) as dev:
            dev.reset_input_buffer()
            dev.write(b'PING\n'); dev.flush()
            if dev.readline().strip() != b'PONG':
                raise RuntimeError('Unexpected diagnostics response')
            dev.write(b'VERSION?\n'); dev.flush()
            version = dev.readline().decode('ascii').strip()
            if not version.startswith('HP6033A-GPIB '):
                raise RuntimeError('Unexpected diagnostics firmware')
            return {'connected': True, 'port': dev.port, 'firmware': version,
                    'response_ms': round((time.monotonic()-started)*1000, 1), 'error': None}
    if target == 'adapter' and action == 'usb-recover':
        import usb.core
        import usb.util
        devices = list(usb.core.find(find_all=True, idVendor=0x03eb, idProduct=0x2065))
        if len(devices) != 1:
            raise RuntimeError('USB-side recovery requires exactly one Xyphro adapter')
        raise RuntimeError('Software USB reset is disabled: this adapter can block in the kernel. Unplug/reconnect USB instead.')
    trace('create PyVISA ResourceManager(@py)')
    rm = pyvisa.ResourceManager('@py')
    dev = None
    try:
        if target == 'adapter' and action == 'discover':
            import usb.core
            devices = []
            trace('usb.core.find for adapter discovery')
            for usbdev in usb.core.find(find_all=True, idVendor=0x03eb, idProduct=0x2065):
                try:
                    trace('read adapter USB serial descriptor: usbdev.serial_number')
                    devices.append({'serial': usbdev.serial_number})
                except Exception as exc:
                    devices.append({'error': type(exc).__name__ + ': ' + str(exc)})
            trace('enumerate USB VISA resources: rm.list_resources')
            return {'resources': list(rm.list_resources('USB?*::INSTR')), 'devices': devices}
        resource = cfg['resource']
        # The adapter changes its USB serial prefix when its detected first GPIB
        # address changes. Match the stable adapter suffix using cached sysfs data.
        from pathlib import Path
        serial = resource.split('::')[3]
        suffix = re.sub(r'^GPIB_\d+_', '', serial)
        matches = []
        candidates = []
        trace('read cached sysfs USB adapter identity')
        for p in Path('/sys/bus/usb/devices').iterdir():
            try:
                if (p/'idVendor').read_text().strip() == '03eb' and (p/'idProduct').read_text().strip() == '2065':
                    observed = (p/'serial').read_text().strip()
                    candidates.append(observed)
                    if re.sub(r'^GPIB_\d+_', '', observed) == suffix:
                        matches.append(observed)
            except OSError:
                pass
        if len(candidates) == 1:
            # AutoID may replace GPIB_<address>_<adapter-id> with the meter's
            # *IDN-derived USB serial after reconnecting or changing language.
            resource = resource.replace('::'+serial+'::','::'+candidates[0]+'::')
        elif len(matches) == 1:
            resource = resource.replace('::'+serial+'::','::'+matches[0]+'::')
        elif len(matches) > 1:
            raise RuntimeError('Ambiguous USB adapter identity; refusing hardware access')
        trace('open VISA resource: rm.open_resource')
        dev = rm.open_resource(resource, open_timeout=600)
        dev.timeout = 3000 if target == 'counter' else (1800 if target == 'meter' and action in ('sample', 'single') else 600)
        dev.query_delay = .25 if target == 'counter' else .005
        dev.write_termination = '\r' if target == 'counter' else '\n'
        dev.read_termination = '\r' if target == 'counter' else '\n'
        if target == 'counter':
            dev.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR, ord('\r'))
            dev.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR_EN, True)
        if payload.get('recover'):
            trace('recover existing USBTMC transfer')
            trace('retry with fresh session; no USB reset or device clear')
        trace('adapter internal-command pulse: ctrl_transfer 0xA1/0x40')
        pulse(rm, dev)
        trace('query adapter firmware: !ver?')
        version = dev.query('!ver?').strip()
        match = re.search(r'V?(\d+)\.(\d+)', version)
        if not match or tuple(map(int, match.groups())) < (2, 4):
            raise RuntimeError('Shared adapter requires UsbGpib firmware 2.4 or later; got ' + version)
        if target == 'counter':
            trace('set adapter volatile CR read termination for counter')
            pulse(rm, dev)
            dev.write('!term cr')
            pulse(rm, dev)
            trace('adapter read termination: ' + dev.query('!term?').strip())
        if target == 'adapter':
            return {'firmware': version, 'resource': resource}
        address = cfg['addresses'][target]
        trace('select GPIB address: !addr ' + str(address))
        pulse(rm, dev)
        dev.write('!addr ' + str(address))
        if target == 'meter' and action == 'local':
            interface = usb_interface(rm, dev)
            reply = interface.usb_dev.ctrl_transfer(0xa1, 0xa1, 0, interface.usb_intf.index, 1, timeout=600)
            if not reply or reply[0] != 1:
                raise RuntimeError('Adapter did not acknowledge addressed Go To Local')
            # No SCPI readback here: it would address the meter and undo Local.
            return {'local_requested':True, 'adapter_acknowledged':True, 'instrument_mode_verified':False}
        trace('run ' + target + ' action ' + action)
        traced = TracedDevice(dev,target)
        return dispatch_instrument(traced, target, action, data)
    finally:
        try:
            if dev is not None:
                dev.close()
        finally:
            rm.close()


if __name__ == '__main__':
    try:
        result = hardware(json.load(sys.stdin))
        print(json.dumps({'ok': True, 'result': result}, allow_nan=False))
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'ok': False, 'error': type(exc).__name__ + ' during ' + CURRENT_PHASE + ': ' + str(exc)[:350],
                          'io_failed': type(exc).__name__ in ('USBTimeoutError','USBError','VisaIOError','TimeoutError','OSError')}))
