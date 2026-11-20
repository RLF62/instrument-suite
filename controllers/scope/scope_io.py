"""Serialized Ethernet access and validated Tektronix waveform/measurement data."""
import csv
import fcntl
import io
import ipaddress
import json
import math
import os
import re
import struct
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import vxi11
from ethernet_transport import BoundedInstrument

ROOT = Path(__file__).resolve().parent
DEFAULT = {'address': '192.168.1.78', 'timeout': 6.0}
THREAD_LOCK = threading.Lock()
class ScopeError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status

def validate_connection(data):
    if not isinstance(data, dict):
        raise ScopeError('Expected connection settings.', 400)
    address = str(data.get('address', '')).strip()
    if not address or len(address) > 253:
        raise ScopeError('Enter an IPv4 address or hostname.', 400)
    try:
        ipaddress.IPv4Address(address)
    except ValueError:
        labels = address.rstrip('.').split('.')
        if all(c.isdigit() or c == '.' for c in address) or not all(
            re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p) for p in labels
        ):
            raise ScopeError('Use an IPv4 address or hostname without http://, a port, or a path.', 400)
    try:
        timeout = float(data.get('timeout', DEFAULT['timeout']))
    except (ValueError, TypeError):
        raise ScopeError('Timeout must be a number from 1 to 30 seconds.', 400)
    if not math.isfinite(timeout) or not 1 <= timeout <= 30:
        raise ScopeError('Timeout must be from 1 to 30 seconds.', 400)
    return {'address': address, 'timeout': timeout}

def config():
    p = ROOT / 'connection.json'
    return validate_connection(json.loads(p.read_text())) if p.exists() else DEFAULT.copy()

def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        os.chmod(tmp, 0o600)
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def value(text):
    text = text.strip()
    return re.sub(r'^:?[A-Za-z][A-Za-z0-9_:]*\s+', '', text)

def ask(s, command):
    return value(s.ask(command))

@contextmanager
def serialized():
    if not THREAD_LOCK.acquire(timeout=35):
        raise ScopeError('Scope is busy. Please try again shortly.', 503)
    try:
        with open('/tmp/fischer-tektronix-controller.lock', 'a') as f:
            deadline = time.monotonic() + 35
            while True:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ScopeError('Scope is busy. Please try again shortly.', 503)
                    time.sleep(.05)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        THREAD_LOCK.release()

@contextmanager
def scope(override=None):
    with serialized():
        c = override or config()
        if c['address']=='scope-not-configured.invalid':raise ScopeError('Open Setup and enter the scope IP address before connecting.',409)
        s = BoundedInstrument(c['address'])
        s.timeout = c['timeout']
        broken = False
        try:
            yield s, c
        except BaseException as exc:
            # A timed-out RPC stream must not be reused for destroy_link.
            seen = set()
            current = exc
            while current is not None and id(current) not in seen:
                seen.add(id(current))
                broken = broken or isinstance(current, (TimeoutError, OSError))
                current = current.__cause__ or current.__context__
            raise
        finally:
            if not broken:
                try:
                    s.close()
                except Exception:
                    broken = True
            if broken:
                for attr in ('client', 'abort_client'):
                    client = getattr(s, attr, None)
                    if client is not None:
                        try:
                            client.close()
                        except Exception:
                            pass
                        setattr(s, attr, None)
                s.link = None

def same(a, b):
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-15)
    except (ValueError, TypeError):
        return a.upper() == b.upper()

def restore(s, saved):
    errors = []
    # Attempt every restoration, even if one fails; no success response on failure.
    for command, setting in saved.items():
        try:
            s.write(command + ' ' + setting)
        except Exception as e:
            errors.append(command + ': ' + str(e))
    for command, setting in saved.items():
        try:
            actual = ask(s, command + '?')
            if not same(actual, setting):
                errors.append(command + ': expected ' + setting + ', got ' + actual)
        except Exception as e:
            errors.append(command + ': ' + str(e))
    if errors:
        raise ScopeError('Settings restoration could not be verified: ' + '; '.join(errors))

MEASUREMENTS = [('frequency', 'FREQUENCY', 'Hz'), ('period', 'PERIOD', 's'),
                ('pk2pk', 'PK2PK', 'V'), ('rms', 'RMS', 'V'), ('mean', 'MEAN', 'V')]
WARNINGS = {540: 'The scope reports a measurement warning; treat this value as uncertain.',
    541: 'Low signal amplitude; this reading may be unreliable.',
    542: 'The waveform distribution is unstable; this reading may be unreliable.',
    543: 'Low measurement resolution; this reading has limited precision.'}
QUALIFIERS = {
    2200: 'Measurement system error', 2201: 'Zero period', 2202: 'No period found',
    2204: 'Signal amplitude too low', 2206: 'Invalid measurement gate',
    2207: 'Measurement overflow', 2208: 'No mid-reference crossing',
    2209: 'No second mid-reference crossing', 2212: 'No negative crossing',
    2213: 'No positive crossing', 2214: 'No crossing', 2217: 'Constant waveform',
    2219: 'No valid edge', 2220: 'No valid edge', 2221: 'No valid trigger crossing',
    2222: 'No second crossing', 2223: 'Waveform mismatch', 2224: 'Still calculating',
    2225: 'No waveform to measure', 2226: 'Null waveform',
    2227: 'Positive and negative clipping', 2228: 'Positive clipping',
    2229: 'Negative clipping', 2230: 'Invalid reference levels',
    2231: 'Measurement not enabled', 2232: 'Frequency out of range',
    2241: 'Invalid waveform', 2244: 'Channel is off'
}
def channel(ch):
    if ch not in ('CH1', 'CH2'):
        raise ScopeError('Choose CH1 or CH2.', 400)
    return ch

def measurement_result(raw, unit):
    try:
        fields = raw.split(',')
        if len(fields) != 2:
            raise ValueError()
        number, code = float(fields[0]), int(fields[1])
        finite = math.isfinite(number) and abs(number) < 1e30
        numeric_ok = finite and not (unit in ('Hz','s') and number <= 0)
        warning = code in WARNINGS
        valid = numeric_ok and (code == 0 or warning)
        if not numeric_ok:
            reason = QUALIFIERS.get(code, 'No valid numeric result was returned by the scope.')
        elif warning:
            reason = WARNINGS[code]
        elif code:
            reason = QUALIFIERS.get(code, 'The scope could not confirm this reading. See reading details.')
        else:
            reason = ''
        return {'value': number if valid else None, 'reported_value': number if finite else None,
                'valid': valid, 'quality': 'warning' if valid and warning else 'valid' if valid else 'unavailable',
                'unit': unit, 'qualifier': code, 'reason': reason, 'raw_response': raw.strip()}
    except (ValueError, OverflowError, AttributeError, TypeError):
        return {'value': None, 'reported_value': None, 'valid': False, 'quality':'unavailable',
                'unit': unit, 'qualifier': None, 'reason': 'Unrecognized instrument response',
                'raw_response':str(raw)[:512]}

def measurements(s, ch):
    channel(ch)
    enabled = ask(s, 'SELECT:' + ch + '?') == '1'
    if not enabled:
        return {'channel': ch, 'updated': time.time(), 'readings': {
            k: {'value': None, 'valid': False, 'unit': u, 'qualifier': 2244, 'reason': 'Channel is off'}
            for k, _, u in MEASUREMENTS}}
    saved = {k: ask(s, k + '?') for k in ('MEASUREMENT:IMMED:SOURCE1', 'MEASUREMENT:IMMED:TYPE')}
    results = {}
    try:
        s.write('MEASUREMENT:IMMED:SOURCE1 ' + ch)
        for key, kind, unit in MEASUREMENTS:
            s.write('MEASUREMENT:IMMED:TYPE ' + kind)
            raw = ask(s, 'MEASUREMENT:IMMED:DATA?')
            actual_unit = ask(s, 'MEASUREMENT:IMMED:UNITS?').strip('"')
            results[key] = measurement_result(raw, unit)
            if actual_unit != unit:
                results[key].update(value=None, valid=False, reason='Unexpected measurement units: ' + actual_unit)
    finally:
        restore(s, saved)
    return {'channel': ch, 'updated': time.time(), 'readings': results,
            'note': 'Sequential scope measurements; uses the scope measurement gate and reference levels.'}

PREAMBLE_KEYS = ['byte_width','bit_width','encoding','binary_format','byte_order','points',
                 'waveform_id','point_format','xincr','pt_off','xzero','xunit','ymult','yzero','yoff','yunit']
def parse_waveform(raw):
    # WAVFRM? supplies labeled headers on this firmware even when HEADER is OFF.
    m = re.search(rb';(?::?CURV(?:E)?\s*)?#([1-9])', raw)
    if not m:
        raise ScopeError('Scope returned no binary waveform. Enable the channel and acquire a record first.', 409)
    prefix = raw[:m.start()].decode('ascii')
    fields = next(csv.reader([prefix], delimiter=';', skipinitialspace=True))
    if len(fields) != 16:
        raise ScopeError('Unexpected waveform preamble field count.')
    vals = []
    for field in fields:
        field = re.sub(r'^:?[A-Za-z][A-Za-z0-9_:]*\s+', '', field.strip())
        vals.append(field.strip('"'))
    p = dict(zip(PREAMBLE_KEYS, vals))
    for k in ('byte_width','bit_width','points','pt_off'):
        p[k] = int(p[k])
    for k in ('xincr','xzero','ymult','yzero','yoff'):
        p[k] = float(p[k])
        if not math.isfinite(p[k]):
            raise ScopeError('Nonfinite waveform scaling in preamble.')
    if (p['byte_width'], p['encoding'], p['binary_format'], p['byte_order']) != (2, 'BIN', 'RI', 'MSB'):
        raise ScopeError('Scope did not accept signed 16-bit big-endian waveform encoding.')
    if p['xunit'] != 's' or p['yunit'] != 'V':
        raise ScopeError('Waveform units must be seconds and volts; got ' + p['xunit'] + '/' + p['yunit'], 409)
    if p['xincr'] <= 0 or p['ymult'] <= 0 or p['points'] not in (500,10000):
        raise ScopeError('Invalid waveform scale or record length.')
    ndigits = int(m.group(1))
    start = m.end()
    length = int(raw[start:start+ndigits])
    start += ndigits
    payload = raw[start:start+length]
    if len(payload) != length or raw[start+length:].strip(b'\r\n'):
        raise ScopeError('Incomplete waveform binary block.')
    if length % 2:
        raise ScopeError('Odd byte count in 16-bit waveform.')
    samples = list(struct.unpack('>' + str(length//2) + 'h', payload))
    fmt = p['point_format']
    if fmt not in ('Y','ENV'):
        raise ScopeError('Unsupported point format: ' + fmt)
    # Peak Detect's 10000 transferred values represent 5000 min/max pairs.
    expected = p['points']
    if len(samples) != expected:
        raise ScopeError('Waveform sample count does not match its preamble.')
    if fmt == 'ENV' and len(samples) % 2:
        raise ScopeError('Incomplete envelope min/max pair.')
    return p, samples

TRANSFER_KEYS = ('DATA:SOURCE','DATA:START','DATA:STOP','DATA:WIDTH',
                 'WFMPRE:BN_FMT','WFMPRE:BYT_OR','DATA:ENCDG')
def waveform_csv(s, ch):
    channel(ch)
    if ask(s, 'SELECT:' + ch + '?') != '1':
        raise ScopeError(ch + ' is off. Enable it and acquire a waveform before downloading.', 409)
    saved = {k: ask(s, k + '?') for k in TRANSFER_KEYS}
    before = {'running': ask(s, 'ACQUIRE:STATE?'), 'stop_after': ask(s, 'ACQUIRE:STOPAFTER?')}
    try:
        s.write('DATA:SOURCE ' + ch)
        s.write('DATA:START 1')
        s.write('DATA:STOP 10000')
        s.write('DATA:WIDTH 2')
        s.write('DATA:ENCDG RIBINARY')
        identity = ask(s, '*IDN?')
        s.write('WAVFRM?')
        raw = s.read_raw()
        timestamp = datetime.now(timezone.utc).isoformat()
        p, samples = parse_waveform(raw)
    finally:
        restore(s, saved)
    after = {'running': ask(s, 'ACQUIRE:STATE?'), 'stop_after': ask(s, 'ACQUIRE:STOPAFTER?')}
    # No acquisition commands are sent by this path, including while Single is armed.
    out = io.StringIO(newline='')
    w = csv.writer(out)
    meta = {'channel': ch, 'capture_read_timestamp_utc': timestamp,
            'timestamp_note': 'Host waveform-read time, not instrument trigger time',
            'reported_identity': identity, 'acquisition_before': json.dumps(before),
            'acquisition_after': json.dumps(after),
            'transfer_settings_restored': 'verified',
            'capture_note': 'Latest stored record; export does not trigger, stop, or restart acquisition',
            'time_formula': 'xzero + xincr * (zero_based_point_index - pt_off)',
            'voltage_formula': 'yzero + ymult * (raw_sample - yoff)', **p}
    for k, v in meta.items():
        w.writerow(['# ' + k, v])
    y = lambda n: format(p['yzero'] + p['ymult'] * (n - p['yoff']), '.17g')
    t = lambda n: format(p['xzero'] + p['xincr'] * (n - p['pt_off']), '.17g')
    if p['point_format'] == 'Y':
        w.writerow(['time_seconds','voltage_volts','raw_sample'])
        for i, n in enumerate(samples):
            w.writerow([t(i), y(n), n])
    else:
        w.writerow(['time_seconds','voltage_min_volts','voltage_max_volts','raw_min','raw_max'])
        for i in range(0,len(samples),2):
            a, b = sorted(samples[i:i+2])
            w.writerow([t(i//2), y(a), y(b), a, b])
    return out.getvalue(), p, timestamp


MEASUREMENT_TYPES = {k:(kind,unit) for k,kind,unit in MEASUREMENTS}
def validate_entries(entries):
    if not isinstance(entries,list) or len(entries)>20:
        raise ScopeError('Choose up to 20 dashboard measurement entries.',400)
    seen = set()
    result = []
    for row in entries:
        if not isinstance(row,dict) or set(row)!={'id','channel','type','on_scope'}:
            raise ScopeError('Invalid measurement entry.',400)
        ident = row['id']
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',ident) or ident in seen:
            raise ScopeError('Measurement entry IDs must be unique.',400)
        seen.add(ident)
        channel(row['channel'])
        if not isinstance(row['type'],str) or row['type'] not in MEASUREMENT_TYPES or not isinstance(row['on_scope'],bool):
            raise ScopeError('Choose a supported measurement type.',400)
        result.append(dict(row))
    if sum(r['on_scope'] for r in result)>4:
        raise ScopeError('The scope supports four on-screen measurement slots. Select at most four entries.',400)
    return result

def display_slots(s):
    return [{'slot':n,'channel':ask(s,f'MEASUREMENT:MEAS{n}:SOURCE1?'),
             'type':ask(s,f'MEASUREMENT:MEAS{n}:TYPE?'),
             'enabled':ask(s,f'MEASUREMENT:MEAS{n}:STATE?')=='1'} for n in range(1,5)]

def measurement_entries(s, entries):
    entries = validate_entries(entries)
    results = []
    started = time.time()
    if not entries:
        return {'entries': [], 'started':started, 'updated':time.time()}
    enabled = {ch:ask(s,'SELECT:'+ch+'?')=='1' for ch in {r['channel'] for r in entries}}
    slots = display_slots(s)
    saved = {}
    try:
        for row in entries:
            kind,unit = MEASUREMENT_TYPES[row['type']]
            matching = next((slot for slot in slots if slot['enabled'] and slot['channel']==row['channel']
                             and kind.startswith(slot['type'])),None)
            basis = 'Scope display slot '+str(matching['slot']) if matching else 'Immediate measurement'
            if not enabled[row['channel']]:
                reading = {'value':None,'reported_value':None,'valid':False,'quality':'unavailable',
                           'unit':unit,'qualifier':2244,'reason':'Channel is off','raw_response':''}
            else:
                if matching:
                    prefix = f"MEASUREMENT:MEAS{matching['slot']}"
                else:
                    if not saved:
                        saved = {k:ask(s,k+'?') for k in ('MEASUREMENT:IMMED:SOURCE1','MEASUREMENT:IMMED:TYPE')}
                    s.write('MEASUREMENT:IMMED:SOURCE1 '+row['channel'])
                    s.write('MEASUREMENT:IMMED:TYPE '+kind)
                    prefix = 'MEASUREMENT:IMMED'
                raw = ask(s,prefix+':DATA?')
                reading = measurement_result(raw,unit)
                actual_unit = ask(s,prefix+':UNITS?').strip('"')
                if actual_unit != unit:
                    reading.update(value=None,valid=False,quality='unavailable',
                                   reason='Unexpected measurement units: '+actual_unit)
            results.append({**row, **reading,'measured_at':time.time(),'basis':basis,
                            'scope_slot':matching['slot'] if matching else None})
    finally:
        if saved:
            restore(s,saved)
    return {'entries':results,'started':started,'updated':time.time(),
            'note':'Matching on-screen slots are read directly. Images and readings are acquired separately and can show different instants.'}
