"""Fischer Lab Tektronix controller, v0.3.8. One worker; threaded requests serialized."""
import gzip
import json
import logging
import math
import re
import struct
import time
import urllib.request
import zlib
from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from scope_io import (ROOT, ScopeError, ask, atomic_json, channel, config, measurements,
                      same, scope, serialized, validate_connection, waveform_csv)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 262144
VERSION = '0.3.8'
FIELDS = {
 'timebase': ('HORIZONTAL:MAIN:SCALE', 1e-9, 10),
 'acq_mode': ('ACQUIRE:MODE', ('SAMPLE','PEAKDETECT','AVERAGE','ENVELOPE')),
 'average_count': ('ACQUIRE:NUMAVG', tuple(str(2**i) for i in range(1,10))),
 'trigger_type': ('TRIGGER:A:TYPE', ('EDGE',)),
 'trigger_mode': ('TRIGGER:A:MODE', ('AUTO','NORMAL')),
 'trigger_source': ('TRIGGER:A:EDGE:SOURCE', ('CH1','CH2','EXT','EXT10','LINE','VERTICAL','ALTERNATING')),
 'trigger_slope': ('TRIGGER:A:EDGE:SLOPE', ('RISE','FALL')),
 'trigger_level': ('TRIGGER:A:LEVEL', -1000, 1000)
}
for n in (1,2):
    FIELDS.update({
        f'ch{n}_on': (f'SELECT:CH{n}', ('0','1')),
        f'ch{n}_probe': (f'CH{n}:PROBE', .001, 1000),
        f'ch{n}_scale': (f'CH{n}:SCALE', 1e-6, 10000),
        f'ch{n}_position': (f'CH{n}:POSITION', -5, 5),
        f'ch{n}_offset': (f'CH{n}:OFFSET', -100000, 100000),
        f'ch{n}_coupling': (f'CH{n}:COUPLING', ('DC','AC','GND')),
        f'ch{n}_bandwidth': (f'CH{n}:BANDWIDTH', ('FULL','TWENTY','ONEFIFTY')),
        f'ch{n}_invert': (f'CH{n}:INVERT', ('0','1'))
    })

def normalize(key, val):
    if key in FIELDS and len(FIELDS[key]) == 2:
        for choice in FIELDS[key][1]:
            if choice.startswith(val.upper()):
                return choice
    return val

def read_fields(s):
    return {k: normalize(k, ask(s, f[0]+'?')) for k, f in FIELDS.items()}

def acquisition(s):
    trigger = ask(s, 'TRIGGER:STATE?')
    stop_after = ask(s, 'ACQUIRE:STOPAFTER?')
    running = ask(s, 'ACQUIRE:STATE?')
    if running == '0':
        label = 'Stopped'
    elif trigger.startswith('READY'):
        label = 'Waiting for trigger'
    elif trigger.startswith('ARM'):
        label = 'Running · pretrigger'
    elif trigger.startswith('TRIG'):
        label = 'Running · capturing'
    elif trigger.startswith('AUTO'):
        label = 'Running · Auto'
    elif trigger.startswith('SAV'):
        label = 'Running · no active capture'
    else:
        label = 'Running · ' + trigger
    return {'running': running, 'trigger_state': trigger, 'stop_after': stop_after, 'acquisition_label': label, 'trigger_source': normalize('trigger_source',ask(s,'TRIGGER:A:EDGE:SOURCE?')), 'trigger_type': normalize('trigger_type',ask(s,'TRIGGER:A:TYPE?'))}

def read_state(s, c):
    return {**read_fields(s), **acquisition(s), 'identity': ask(s,'*IDN?'),
            'host': c['address'], 'label': 'TDS 3032B', 'connected': True,
            'updated': time.time(), 'version': VERSION}

def command_for(key, val):
    if not isinstance(key, str) or key not in FIELDS:
        raise ScopeError('Unknown control.', 400)
    field = FIELDS[key]
    if len(field) == 2:
        if not isinstance(val,str) or val not in field[1]:
            raise ScopeError('Invalid option for ' + key, 400)
        return field[0] + ' ' + val
    if isinstance(val, (bool, list, dict)) or val is None or val == '':
        raise ScopeError('Enter a number.', 400)
    try:
        number = float(val)
    except (ValueError,TypeError):
        raise ScopeError('Enter a number.', 400)
    if not math.isfinite(number) or not field[1] <= number <= field[2]:
        raise ScopeError(f'Value must be between {field[1]:g} and {field[2]:g}.', 400)
    return field[0] + ' ' + format(number,'.12g')

def require_post():
    if urlsplit(request.headers.get('Origin','')).netloc != request.host or not request.is_json:
        raise ScopeError('Same-origin JSON request required.',403)

@app.before_request
def protect():
    if request.method in ('POST','PUT','DELETE'):
        require_post()

@app.after_request
def headers(r):
    r.headers['Cache-Control'] = 'no-store'
    r.headers['X-Content-Type-Options'] = 'nosniff'
    r.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return r

@app.errorhandler(Exception)
def error(e):
    if isinstance(e, HTTPException):
        return jsonify(error=e.description), e.code
    status = e.status if isinstance(e,ScopeError) else 502
    logging.exception('Controller request failed')
    return jsonify(error=str(e), connected=False), status

@app.get('/')
def home():
    return send_file(ROOT/'index.html')

@app.get('/setup')
def setup():
    return send_file(ROOT/'setup.html')

@app.get('/docs/')
def docs():
    return Response((ROOT/'docs'/'index.html').read_text().replace('__CONTROLLER_VERSION__',VERSION),mimetype='text/html')

@app.get('/api/config')
def get_config():
    return jsonify(config())

@app.post('/api/config/test')
def test_config():
    c = validate_connection(request.get_json())
    with scope(c) as (s,_):
        identity = ask(s,'*IDN?')
        if not identity.startswith('TEKTRONIX,TDS '):
            raise ScopeError('A device answered, but did not identify as a Tektronix TDS scope.',409)
        return jsonify(connected=True, identity=identity, address=c['address'])

@app.post('/api/config')
def save_config():
    c = validate_connection(request.get_json())
    with serialized():
        atomic_json(ROOT/'connection.json',c)
    return jsonify(saved=True, **c)

@app.get('/api/state')
def state():
    with scope() as (s,c):
        return jsonify(read_state(s,c))

@app.get('/api/acquisition')
def status():
    with scope() as (s,c):
        return jsonify(**acquisition(s), updated=time.time())

@app.get('/api/measurements')
def measure():
    ch = channel(request.args.get('channel','CH1'))
    with scope() as (s,_):
        return jsonify(measurements(s,ch))

@app.get('/api/waveform.csv')
def waveform():
    ch = channel(request.args.get('channel','CH1'))
    with scope() as (s,_):
        text,p,ts = waveform_csv(s,ch)
    name = ch + '-' + re.sub(r'[^0-9]', '', ts)[:14] + '.csv'
    return Response(text, mimetype='text/csv', headers={
        'Content-Disposition': 'attachment; filename="'+name+'"',
        'X-Waveform-Point-Format': p['point_format']})

@app.get('/api/waveform.preview.csv')
def waveform_preview():
    # Read-only test endpoint. Browser transparently decompresses the CSV.
    ch = channel(request.args.get('channel', 'CH1'))
    with scope() as (s, _):
        text, preamble, _ = waveform_csv(s, ch)
    return Response(gzip.compress(text.encode('utf-8'), compresslevel=1),
                    mimetype='text/csv',
                    headers={'Content-Encoding': 'gzip',
                             'Cache-Control': 'no-store',
                             'X-Waveform-Point-Format': preamble['point_format']})


@app.post('/api/control')
def control():
    d = request.get_json()
    if not isinstance(d,dict) or set(d) != {'key','value'}:
        raise ScopeError('Expected key and value.',400)
    key,val = d['key'],d['value']
    if key in ('running','single','menu_off','autoset'):
        if (key == 'running' and val not in ('0','1')) or (key != 'running' and val != '1'):
            raise ScopeError('Invalid action.',400)
        command = None
    else:
        command = command_for(key,val)
    with scope() as (s,c):
        if key == 'autoset':
            s.write('AUTOSET EXECUTE')
            return jsonify(ok=True, message='Autoset requested; reading scope status and resulting settings.')
        if key == 'single':
            s.write('ACQUIRE:STATE OFF')
            s.write('ACQUIRE:STOPAFTER SEQUENCE')
            s.write('ACQUIRE:STATE ON')
            return jsonify(ok=True, **acquisition(s), message='Single sequence requested; state read from scope.')
        if key == 'running':
            if val == '1':
                s.write('ACQUIRE:STOPAFTER RUNSTOP')
            s.write('ACQUIRE:STATE '+val)
            return jsonify(ok=True, **acquisition(s), message='Acquisition state read from scope.')
        if key == 'menu_off':
            s.write('CLEARMENU')
            ask(s,'*IDN?')
            return jsonify(ok=True, message='Menu Off sent. The scope screen shows the result.')
        if key in ('trigger_source','trigger_slope','trigger_level') and not ask(s,'TRIGGER:A:TYPE?').startswith('EDG'):
            raise ScopeError('Select Edge trigger on the scope before using these controls.',409)
        if key == 'average_count' and not ask(s,'ACQUIRE:MODE?').startswith('AVE'):
            raise ScopeError('Select Average acquisition mode before setting its count.',409)
        s.write(command)
        actual = normalize(key,ask(s,FIELDS[key][0]+'?'))
        matched = same(actual,val)
        return jsonify(ok=True,key=key,actual=actual,matched=matched,
                       message=('Applied' if matched else 'Scope accepted a different value') + ' · readback: ' + actual)

def validate_png(b):
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        raise ScopeError('Scope did not return a PNG.')
    pos = 8
    while pos+12 <= len(b):
        n = struct.unpack('>I',b[pos:pos+4])[0]
        end = pos+12+n
        if end > len(b):
            break
        chunk = b[pos+4:pos+8+n]
        if zlib.crc32(chunk)&0xffffffff != struct.unpack('>I',b[pos+8+n:end])[0]:
            raise ScopeError('Scope image checksum failed.')
        if chunk[:4] == b'IEND':
            return b[:end]
        pos = end
    raise ScopeError('Incomplete scope screen image; refresh to retry.')

@app.get('/classic')
def classic_front_panel():
    return send_file(ROOT/'static'/'classic-front-panel-test.html')

@app.get('/api/screen')
def screen():
    with scope() as (_,c):
        with urllib.request.urlopen('http://'+c['address']+'/Image.png',timeout=c['timeout']) as r:
            b = validate_png(r.read(200000))
    return Response(b,mimetype='image/png')

# Presets deliberately cover a declared subset, not an opaque entire-instrument setup.
PRESET_KEYS = list(FIELDS)
def preset_store():
    p = ROOT/'presets.json'
    return json.loads(p.read_text()) if p.exists() else {}

@app.get('/api/presets')
def list_presets():
    with serialized():
        return jsonify(presets=preset_store(), includes=PRESET_KEYS,
                       excludes=['Run/Stop state','Single arm state','waveform data','network settings',
                                 'advanced trigger parameters','measurement gates/references','panel layout'])

@app.post('/api/presets/save')
def save_preset():
    d = request.get_json()
    name = d.get('name','') if isinstance(d,dict) else ''
    if not isinstance(name,str) or not 1 <= len(name.strip()) <= 64 or any(ord(c)<32 for c in name):
        raise ScopeError('Use a preset name from 1 to 64 characters.',400)
    name = name.strip()
    with scope() as (s,_):
        settings = read_fields(s)
        if settings['trigger_type'] != 'EDGE':
            raise ScopeError('Presets currently support Edge trigger setups only. Select Edge and save again.',409)
        for k,v in settings.items():
            command_for(k,v)
        store = preset_store()
        if len(store) >= 50 and name not in store:
            raise ScopeError('Up to 50 named presets can be saved.',400)
        if d.get('save_as_new') and name in store:
            raise ScopeError('A personal setup already has that name. Choose a new name.',409)
        store[name] = {'settings': settings, 'saved_utc': datetime.now(timezone.utc).isoformat(),
                       'identity': ask(s,'*IDN?')}
        if d.get('example_id'):
            example=example_by_id(d['example_id'])
            store[name]['origin_example']=example['id']
            store[name]['notes']='Personal scope readback based on '+example['name']+'. Not a reproduction or independently verified capture of the prior session. Physical probes and wiring must be checked separately.'
        atomic_json(ROOT/'presets.json',store)
    return jsonify(saved=True,name=name)

def apply_settings(s, settings):
    # Probe factor can change scale, so restore probe before scale/position/offset.
    order = [k for k in settings if k.endswith('_probe')]
    order += [k for k in settings if k not in order and k != 'trigger_type']
    if 'trigger_type' in settings:
        order.insert(0,'trigger_type')
    for k in order:
        s.write(command_for(k,settings[k]))

@app.post('/api/presets/recall')
def recall_preset():
    d = request.get_json()
    name = d.get('name') if isinstance(d,dict) else None
    if not isinstance(name,str):
        raise ScopeError('Choose a named preset.',400)
    with scope() as (s,c):
        store = preset_store()
        if name not in store:
            raise ScopeError('Preset not found.',404)
        wanted = store[name]['settings']
        if set(wanted) != set(PRESET_KEYS):
            raise ScopeError('Preset schema does not match this controller version.',409)
        for k,v in wanted.items():
            command_for(k,v)
        old = read_fields(s)
        try:
            apply_settings(s,wanted)
            actual = read_fields(s)
            differences = {k: {'requested':wanted[k], 'actual':actual[k]}
                           for k in wanted if not same(wanted[k],actual[k])}
        except Exception as exc:
            # Roll back the declared subset without touching model identity or run/stop.
            # Non-Edge original triggers are restored using their returned type.
            try:
                rollback = dict(old)
                trigger = rollback.pop('trigger_type')
                apply_settings(s,rollback)
                s.write('TRIGGER:A:TYPE '+trigger)
                checked = read_fields(s)
                if any(not same(old[k],checked[k]) for k in old):
                    raise ScopeError('Rollback readback mismatch.')
            except Exception as restore_error:
                raise ScopeError('Preset recall failed; rollback could not be verified: '+str(restore_error)) from exc
            raise ScopeError('Preset recall failed; previous included settings restored: '+str(exc)) from exc
        return jsonify(ok=True,name=name,settings=actual,differences=differences, **acquisition(s))


DEFAULT_COLORS = {'ch1': '#f2d56a', 'ch2': '#79b8ff'}
def appearance():
    p = ROOT/'appearance.json'
    return json.loads(p.read_text()) if p.exists() else DEFAULT_COLORS.copy()

@app.get('/api/appearance')
def get_appearance():
    return jsonify(appearance())

@app.post('/api/appearance')
def save_appearance():
    d = request.get_json()
    if not isinstance(d,dict) or set(d) != {'ch1','ch2'} or any(
        not isinstance(d[k],str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',d[k]) for k in ('ch1','ch2')
    ):
        raise ScopeError('Choose a six-digit color for both CH1 and CH2.',400)
    colors = {k:d[k].lower() for k in ('ch1','ch2')}
    with serialized():
        atomic_json(ROOT/'appearance.json',colors)
    return jsonify(saved=True, **colors)


from scope_io import MEASUREMENT_TYPES, measurement_entries, validate_entries, restore
DEFAULT_ENTRIES = [{'id':'default-'+key,'channel':'CH1','type':key,'on_scope':False}
                   for key,_,_ in __import__('scope_io').MEASUREMENTS]
def saved_entries():
    p = ROOT/'measurement-selection.json'
    return validate_entries(json.loads(p.read_text())) if p.exists() else DEFAULT_ENTRIES

@app.get('/api/measurement-selection')
def get_selection():
    return jsonify(entries=saved_entries(),scope_slot_limit=4,dashboard_limit=20)

@app.post('/api/measurement-selection')
def save_selection():
    d = request.get_json()
    entries = validate_entries(d.get('entries') if isinstance(d,dict) else None)
    with serialized():
        atomic_json(ROOT/'measurement-selection.json',entries)
    return jsonify(saved=True,entries=entries)

@app.post('/api/measurements')
def measure_list():
    d = request.get_json()
    entries = validate_entries(d.get('entries') if isinstance(d,dict) else None)
    with scope() as (s,_):
        return jsonify(measurement_entries(s,entries))

def scope_slots(s):
    return [{'slot':n, **{k.lower():ask(s,f'MEASUREMENT:MEAS{n}:{k}?')
                         for k in ('SOURCE1','TYPE','STATE')}} for n in range(1,5)]

@app.get('/api/measurement-slots')
def get_slots():
    with scope() as (s,_):
        return jsonify(slots=scope_slots(s),limit=4)

@app.post('/api/measurement-slots')
def apply_slots():
    d = request.get_json()
    entries = validate_entries(d.get('entries') if isinstance(d,dict) else None)
    selected = [r for r in entries if r['on_scope']]
    with scope() as (s,_):
        # A source must already be active. Do not silently change channel/acquisition state.
        for row in selected:
            if ask(s,'SELECT:'+row['channel']+'?')!='1':
                raise ScopeError('Enable '+row['channel']+' before applying it to the scope display.',409)
        saved = {f'MEASUREMENT:MEAS{n}:{k}':ask(s,f'MEASUREMENT:MEAS{n}:{k}?')
                 for n in range(1,5) for k in ('SOURCE1','TYPE','STATE')}
        try:
            for n in range(1,5):
                prefix = f'MEASUREMENT:MEAS{n}:'
                if n <= len(selected):
                    row = selected[n-1]
                    s.write(prefix+'SOURCE1 '+row['channel'])
                    s.write(prefix+'TYPE '+MEASUREMENT_TYPES[row['type']][0])
                    s.write(prefix+'STATE ON')
                else:
                    s.write(prefix+'STATE OFF')
            actual = scope_slots(s)
            for n,row in enumerate(actual):
                if n < len(selected):
                    wanted = selected[n]
                    kind = MEASUREMENT_TYPES[wanted['type']][0]
                    if row['state']!='1' or row['source1']!=wanted['channel'] or not kind.startswith(row['type']):
                        raise ScopeError('Scope did not accept measurement slot '+str(n+1))
                elif row['state']!='0':
                    raise ScopeError('Scope did not turn off measurement slot '+str(n+1))
        except Exception:
            restore(s,saved)
            raise
        return jsonify(ok=True,slots=actual,limit=4)


from screen_effect import recolor
import uuid
CAPTURES = {}
@app.get('/api/screen/display')
def display_screen():
    with scope() as (_,c):
        with urllib.request.urlopen('http://'+c['address']+'/Image.png',timeout=c['timeout']) as r:
            raw = validate_png(r.read(200000))
        colors = appearance()
        captured_at = time.time()
    warning = ''
    try:
        displayed,changed = recolor(raw,colors)
        effect = 'channel-trace-colors'
    except ScopeError as exc:
        displayed,changed,effect,warning = raw,0,'original',str(exc)
    token = uuid.uuid4().hex
    with serialized():
        CAPTURES[token] = raw
        while len(CAPTURES)>16:
            del CAPTURES[next(iter(CAPTURES))]
    return Response(displayed,mimetype='image/png',headers={
        'X-Display-Effect':effect,'X-Display-Effect-Warning':warning,
        'X-Changed-Trace-Pixels':str(changed),
        'X-Original-Capture':'/api/screen/original/'+token+'.png',
        'X-Captured-At':datetime.fromtimestamp(captured_at,timezone.utc).isoformat()})

@app.get('/api/screen/original/<token>.png')
def original_screen(token):
    if not re.fullmatch('[a-f0-9]{32}',token):
        raise ScopeError('Capture not found.',404)
    with serialized():
        raw = CAPTURES.get(token)
    if raw is None:
        raise ScopeError('Original capture expired. Refresh the scope image to capture again.',404)
    return Response(raw,mimetype='image/png')


@app.get('/api/autoset-status')
def autoset_status():
    with scope() as (s,_):
        return jsonify(busy=ask(s,'BUSY?')=='1')

from archive_tools import (export_backup,validate_backup,restore_preview,restore_preferences,
                           fingerprint,read_restore_point,make_capture)

def controller_preferences():
    return {'connection':config(),'appearance':appearance(),
            'measurements':saved_entries(),'presets':preset_store()}

def capture_png(connection):
    with urllib.request.urlopen('http://'+connection['address']+'/Image.png',timeout=connection['timeout']) as response:
        return validate_png(response.read(200000))

@app.get('/api/capture-bundle')
def capture_bundle():
    with scope() as (s,connection):
        package,manifest=make_capture(s,connection,VERSION,controller_preferences(),read_state,capture_png)
    name='tektronix-test-capture-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.zip'
    return Response(package,mimetype='application/zip',headers={
        'Content-Disposition':'attachment; filename="'+name+'"',
        'X-Capture-Complete':'1' if manifest['complete'] else '0',
        'X-Capture-Warning':'One or more channel CSVs are unavailable; see manifest.json.' if not manifest['complete'] else '',
        'X-Captured-At':manifest['finished_utc']})

@app.get('/api/setup/backup')
def backup_setup():
    with serialized():
        backup=export_backup(controller_preferences(),VERSION)
    name='tektronix-setup-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json'
    return Response(json.dumps(backup,indent=2,allow_nan=False),mimetype='application/json',
                    headers={'Content-Disposition':'attachment; filename="'+name+'"'})

@app.get('/api/setup/backup/<name>')
def backup_restore_point(name):
    with serialized():
        data=read_restore_point(name)
    return Response(data,mimetype='application/json',
                    headers={'Content-Disposition':'attachment; filename="'+name+'"'})

@app.post('/api/setup/restore/preview')
def preview_setup():
    d=request.get_json()
    if not isinstance(d,dict):
        raise ScopeError('Select a controller setup-backup JSON file.',400)
    validated=validate_backup(d.get('backup'),FIELDS,command_for)
    with serialized():
        plan=restore_preview(validated,controller_preferences())
    return jsonify(plan)

@app.post('/api/setup/restore')
def restore_setup():
    d=request.get_json()
    if not isinstance(d,dict):
        raise ScopeError('Review a setup backup before restoring it.',400)
    validated=validate_backup(d.get('backup'),FIELDS,command_for)
    with serialized():
        current=controller_preferences()
        if d.get('expected_current_fingerprint')!=fingerprint(current):
            raise ScopeError('Controller settings changed after the preview. Review the backup again before restoring.',409)
        previous=restore_preferences(validated,current,VERSION)
    return jsonify(restored=True,previous_backup='/api/setup/backup/'+previous,
                   summary=restore_preview(validated,validated))

from example_catalog import all_examples,example_by_id

@app.get('/api/examples')
def examples():
    return jsonify(all_examples())

@app.post('/api/examples/<ident>/recall')
def recall_example(ident):
    example=example_by_id(ident)
    if not example['recallable']:
        raise ScopeError('This example is incomplete: establish the timebase and trigger configuration, test it manually, then save a new personal setup.',409)
    wanted=example['settings']
    for key,value in wanted.items():
        command_for(key,value)
    with scope() as (s,_):
        old=read_fields(s)
        try:
            apply_settings(s,wanted)
            actual=read_fields(s)
        except Exception as error:
            rollback=dict(old);trigger=rollback.pop('trigger_type')
            try:
                apply_settings(s,rollback);s.write('TRIGGER:A:TYPE '+trigger)
                checked=read_fields(s)
                if any(not same(old[k],checked[k]) for k in old):
                    raise ScopeError('Rollback readback mismatch.')
            except Exception as restore_error:
                raise ScopeError('Example recall failed and rollback could not be verified: '+str(restore_error)) from error
            raise ScopeError('Example recall failed; previous scope settings restored: '+str(error)) from error
        differences={k:{'requested':wanted[k],'actual':actual[k]} for k in wanted if not same(wanted[k],actual[k])}
        other_changes={k:{'before':old[k],'after':actual[k]} for k in old if k not in wanted and not same(old[k],actual[k])}
        return jsonify(ok=True,example_id=ident,status=example['status'],settings=actual,
                       differences=differences,other_changes=other_changes,
                       message='Suggested example applied and read back. Check the physical probe switches and wiring; this is not a verified capture.')

@app.get('/docs/assets/<path:filename>')
def docs_asset(filename):
    return send_from_directory(ROOT/'docs'/'assets',filename)

@app.get('/docs/reference.md')
def docs_source_reference():
    return send_file(ROOT/'README.md',mimetype='text/plain')

# Optional shared instrument menu.
try:
    from tool_registration import install_navigation as install_suite_navigation
except ModuleNotFoundError as exc:
    if exc.name != 'tool_registration':raise
else:
    install_suite_navigation(app, 'scope')

