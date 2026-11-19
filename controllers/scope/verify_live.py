"""Opt-in connected-scope verification. Temporarily changes settings, then restores them."""
import concurrent.futures
import csv
import io
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path
from app import FIELDS, apply_settings, read_fields
from scope_io import ROOT, TRANSFER_KEYS, ask, config, restore, same, scope

BASE='http://127.0.0.1:8081'
def call(path, data=None, expected=200):
    req=urllib.request.Request(BASE+path, data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json','Origin':BASE})
    try:
        with urllib.request.urlopen(req,timeout=110) as r:
            result=(r.status,r.read(),r.headers)
    except urllib.error.HTTPError as e:
        result=(e.code,e.read(),e.headers)
    assert result[0]==expected,(path,result[0],result[1][:300])
    return result
def get(path):return json.loads(call(path)[1])
def post(path,data):return json.loads(call(path,data)[1])
def control(k,v):return post('/api/control',{'key':k,'value':v})
def verify_csv(ch):
    text=call('/api/waveform.csv?channel='+ch)[1].decode()
    meta={}; data=[]
    for row in csv.reader(io.StringIO(text)):
        if row[0].startswith('# '):meta[row[0][2:]]=row[1]
        else:data.append(row)
    rows=list(csv.DictReader(io.StringIO('\n'.join(','.join(r) for r in data))))
    assert meta['channel']==ch
    assert meta['transfer_settings_restored']=='verified'
    expected=int(meta['points'])//(2 if meta['point_format']=='ENV' else 1)
    assert len(rows)==expected,(len(rows),expected)
    for i in (0,len(rows)//2,len(rows)-1):
        r=rows[i]; t=float(meta['xzero'])+float(meta['xincr'])*(i-int(meta['pt_off']))
        assert math.isclose(float(r['time_seconds']),t,abs_tol=1e-18)
        if meta['point_format']=='Y':
            y=float(meta['yzero'])+float(meta['ymult'])*(int(r['raw_sample'])-float(meta['yoff']))
            assert math.isclose(float(r['voltage_volts']),y,abs_tol=1e-12)
    return meta,len(rows)

original=get('/api/state')
oldconf=get('/api/config')
with scope() as (s,_):
    before_transfer={k:ask(s,k+'?') for k in TRANSFER_KEYS}
    immediate={k:ask(s,k+'?') for k in ('MEASUREMENT:IMMED:SOURCE1','MEASUREMENT:IMMED:TYPE')}
(ROOT/'verification-original-scope.json').write_text(json.dumps(original,indent=2))
report=[]
def log(message):
    report.append(message); print(message,flush=True)
try:
    post('/api/presets/save',{'name':'Baseline before v0.2 feature tests'})
    log('Saved a named baseline of the current included scope settings.')
    for ch in ('CH1','CH2'):
        readings=get('/api/measurements?channel='+ch)
        assert len(readings['readings'])==5
        assert all(r['valid'] or r['value'] is None for r in readings['readings'].values())
        m,n=verify_csv(ch);log(ch+' CSV: '+str(n)+' rows, '+m['point_format']+'; SI scaling verified.')
    with scope() as (s,_):
        assert before_transfer=={k:ask(s,k+'?') for k in TRANSFER_KEYS}
        assert immediate=={k:ask(s,k+'?') for k in immediate}
    log('Both CSV and measurement temporary settings restored exactly.')
    # Disabled source must return no numeric readings and must not silently enable it.
    control('ch2_on','0')
    off=get('/api/measurements?channel=CH2')
    assert all(not r['valid'] and r['value'] is None for r in off['readings'].values())
    call('/api/waveform.csv?channel=CH2',expected=409)
    control('ch2_on',original['ch2_on'])
    log('Disabled CH2: measurements unavailable; CSV rejected without enabling the channel.')
    # Preset recall round trip.
    control('ch1_position','1')
    recalled=post('/api/presets/recall',{'name':'Baseline before v0.2 feature tests'})
    assert not recalled['differences'],recalled['differences']
    log('Named preset save, changed-position recall and complete readback passed.')
    # New controls must really change and then report accepted settings.
    for n in (1,2):
        for key,val in [(f'ch{n}_probe','1'),(f'ch{n}_probe',original[f'ch{n}_probe']),
                        (f'ch{n}_bandwidth','TWENTY'),(f'ch{n}_bandwidth','ONEFIFTY'),
                        (f'ch{n}_bandwidth','FULL'),(f'ch{n}_invert','1'),(f'ch{n}_invert','0')]:
            d=control(key,val);assert d['matched'],(key,d)
    control('acq_mode','AVERAGE')
    assert control('average_count','8')['actual']=='8'
    log('Both channels: probe, 20/150 MHz/full bandwidth and invert accepted. Average count 8 accepted.')
    # Continuous run then stopped export, with deliberately nondefault transfer settings.
    control('acq_mode','SAMPLE');control('running','1');control('running','0')
    with scope() as (s,_):
        s.write('DATA:SOURCE CH2');s.write('DATA:START 17');s.write('DATA:STOP 321')
        s.write('DATA:WIDTH 1');s.write('DATA:ENCDG ASCII')
        custom={k:ask(s,k+'?') for k in TRANSFER_KEYS}
    verify_csv('CH1')
    with scope() as (s,_):
        assert ask(s,'ACQUIRE:STATE?')=='0'
        assert custom=={k:ask(s,k+'?') for k in TRANSFER_KEYS}
    log('Stopped CSV preserved Stop and restored custom ASCII/width/source/start/stop settings.')
    # Unconnected external trigger with normal mode to observe ready/waiting.
    control('trigger_mode','NORMAL');control('trigger_source','EXT10');control('trigger_level','8')
    control('single','1')
    deadline=time.monotonic()+8
    status=get('/api/acquisition')
    while status['trigger_state'] != 'READY' and time.monotonic()<deadline:
        time.sleep(.1)
        status=get('/api/acquisition')
    assert status['running']=='1',status
    assert status['trigger_state']=='READY',status
    assert status['acquisition_label']=='Waiting for trigger',status
    verify_csv('CH1')
    assert get('/api/acquisition')['running']=='1'
    assert control('menu_off','1')['ok']
    assert get('/api/acquisition')['running']=='1'
    with scope() as (s,_):s.write('TRIGGER:FORCE')
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        status=get('/api/acquisition')
        if status['running']=='0':break
        time.sleep(.1)
    assert status['running']=='0',status
    log('Single reached Waiting for trigger; CSV left it armed; forced trigger completed to Stopped.')
    # Actual new Peak Detect record, not preview data from a previous Sample acquisition.
    control('timebase','0.001');control('acq_mode','PEAKDETECT');control('trigger_mode','AUTO')
    control('single','1')
    deadline=time.monotonic()+8
    status=get('/api/acquisition')
    while status['running']=='1' and status['trigger_state']!='READY' and time.monotonic()<deadline:
        time.sleep(.1)
        status=get('/api/acquisition')
    if status['running']=='1':
        assert status['trigger_state']=='READY',status
        with scope() as (s,_):s.write('TRIGGER:FORCE')
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        status=get('/api/acquisition')
        if status['running']=='0':break
        time.sleep(.1)
    assert status['running']=='0',status
    m,n=verify_csv('CH1')
    log('New Peak Detect CSV: '+str(n)+' rows, '+m['point_format']+'; '+m['waveform_id'])
    # Menu Off acknowledgement and corrected PNG response.
    d=control('menu_off','1');assert d['ok']
    png=call('/api/screen')[1];assert png.startswith(b'\x89PNG') and png.endswith(b'IEND\xaeB\x60\x82')
    log('Documented CLEARMENU completed while Single was armed; post-command screenshot valid.')
    # Concurrent HTTP clients must share the same serialization lock.
    paths=['/api/state','/api/measurements?channel=CH1','/api/waveform.csv?channel=CH1','/api/screen']
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(call,p) for p in paths]
        results=[f.result() for f in futures]
        assert all(r[0]==200 for r in results)
    log('Concurrent state/measurements/CSV/screen requests all completed without mixed responses.')
    post('/api/config/test',oldconf)
    post('/api/config',{'address':'127.0.0.1','timeout':1})
    call('/setup');call('/api/state',expected=502)
    post('/api/config',oldconf)
    assert get('/api/config')==oldconf
    log('Setup remained accessible with unreachable configured scope; saved address restored.')
finally:
    post('/api/config',oldconf)
    with scope() as (s,_):
        s.write('ACQUIRE:STATE OFF')
        settings={k:original[k] for k in FIELDS if k!='trigger_type'}
        apply_settings(s,settings)
        s.write('TRIGGER:A:TYPE '+original['trigger_type'])
        s.write('ACQUIRE:STOPAFTER '+original['stop_after'])
        restore(s,before_transfer)
        restore(s,immediate)
        s.write('ACQUIRE:STATE '+original['running'])
        checked=read_fields(s)
        assert all(same(original[k],checked[k]) for k in FIELDS),(original,checked)
        assert ask(s,'ACQUIRE:STATE?')==original['running']
    log('Original included settings, acquisition state and transfer/measurement settings restored.')
    (ROOT/'verification-results.txt').write_text('\n'.join(report)+'\n')
print('LIVE CHECKS COMPLETE')
