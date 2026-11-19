"""Capture records and validated controller-preference backup/restore."""
import copy
import hashlib
import io
import json
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from scope_io import (ROOT, ScopeError, atomic_json, validate_connection, validate_entries,
                      waveform_csv, measurement_entries, display_slots)
from screen_effect import recolor

FORMAT = 'fischer-tektronix-controller-setup'
SCHEMA = 1
SETTINGS_FILES = {'connection':'connection.json','appearance':'appearance.json',
                  'measurements':'measurement-selection.json','presets':'presets.json'}
def utc():
    return datetime.now(timezone.utc).isoformat()

def fingerprint(settings):
    return hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def export_backup(settings,version):
    return {'format':FORMAT,'schema_version':SCHEMA,'controller_version':version,
            'created_utc':utc(),'settings':copy.deepcopy(settings)}

def validate_backup(backup,fields,command_for):
    if not isinstance(backup,dict) or backup.get('format')!=FORMAT or type(backup.get('schema_version')) is not int or backup['schema_version']!=SCHEMA:
        raise ScopeError('This is not a supported Tektronix controller setup backup.',400)
    settings=backup.get('settings')
    if not isinstance(settings,dict) or set(settings)!=set(SETTINGS_FILES):
        raise ScopeError('Backup must include connection, channel colors, measurement selections and presets.',400)
    connection=validate_connection(settings['connection'])
    colors=settings['appearance']
    if not isinstance(colors,dict) or set(colors)!={'ch1','ch2'} or any(
        not isinstance(colors[k],str) or not re.fullmatch('#[0-9A-Fa-f]{6}',colors[k]) for k in ('ch1','ch2')):
        raise ScopeError('Backup contains invalid channel colors.',400)
    entries=validate_entries(settings['measurements'])
    presets=settings['presets']
    if not isinstance(presets,dict) or len(presets)>50:
        raise ScopeError('Backup contains too many or invalid named presets.',400)
    cleaned={}
    for name,preset in presets.items():
        if not isinstance(name,str) or not 1<=len(name.strip())<=64 or name!=name.strip() or any(ord(c)<32 for c in name):
            raise ScopeError('Backup contains an invalid preset name.',400)
        if not isinstance(preset,dict) or not isinstance(preset.get('settings'),dict) or set(preset['settings'])!=set(fields):
            raise ScopeError('Preset settings do not match this controller version: '+name,400)
        for key,value in preset['settings'].items():
            command_for(key,value)
        if not all(isinstance(preset.get(k),str) and len(preset[k])<=1024 for k in ('saved_utc','identity')):
            raise ScopeError('Backup contains invalid preset metadata: '+name,400)
        cleaned[name]=copy.deepcopy(preset)
    return {'connection':connection,'appearance':{k:v.lower() for k,v in colors.items()},
            'measurements':entries,'presets':cleaned}

def restore_preview(settings,current):
    return {'scope_address':settings['connection']['address'],'timeout':settings['connection']['timeout'],
            'colors':settings['appearance'],'measurement_entries':len(settings['measurements']),
            'preset_names':sorted(settings['presets']),
            'scope_address_changes':settings['connection']['address']!=current['connection']['address'],
            'replaces':['Scope connection address and timeout','Dashboard channel colors',
                        'Saved measurement selection','Named controller presets'],
            'unchanged':['Instrument network configuration','Instrument settings and acquisition',
                         'Physical model configuration','Browser panel layout'],
            'expected_current_fingerprint':fingerprint(current)}

def _atomic_bytes(path,data):
    tmp=path.with_suffix('.rollback.tmp')
    with tmp.open('wb') as f:
        os.chmod(tmp,0o600);f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def restore_preferences(settings,current,version):
    # Caller holds the same serialized lock used by all configuration writers.
    directory=ROOT/'setup-backups'
    directory.mkdir(exist_ok=True)
    name='before-restore-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]+'.json'
    atomic_json(directory/name,export_backup(current,version))
    before={filename:(ROOT/filename).read_bytes() if (ROOT/filename).exists() else None
            for filename in SETTINGS_FILES.values()}
    try:
        for key,filename in SETTINGS_FILES.items():
            atomic_json(ROOT/filename,settings[key])
    except Exception as error:
        problems=[]
        for filename,data in before.items():
            try:
                path=ROOT/filename
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_bytes(path,data)
                actual=path.read_bytes() if path.exists() else None
                if actual!=data:
                    problems.append(filename)
            except Exception:
                problems.append(filename)
        if problems:
            raise ScopeError('Restore failed and automatic rollback could not be verified. Download the previous-settings backup: '+name) from error
        raise ScopeError('Restore failed; the previous settings were restored. No configuration changes were applied.') from error
    return name

def read_restore_point(name):
    if not re.fullmatch(r'before-restore-[0-9]{8}T[0-9]{12}Z-[a-f0-9]{8}\.json',name):
        raise ScopeError('Previous-settings backup not found.',404)
    path=ROOT/'setup-backups'/name
    if not path.is_file():
        raise ScopeError('Previous-settings backup not found.',404)
    return path.read_bytes()

def make_capture(s,connection,version,preferences,state_reader,screen_reader):
    started=utc()
    artifacts={}
    files={}
    before=state_reader(s,connection)
    before['display_measurement_slots']=display_slots(s)
    raw=screen_reader(connection)
    image_time=utc()
    files['scope-original.png']=raw
    artifacts['scope-original.png']={'status':'ok','captured_utc':image_time,'kind':'unmodified scope capture'}
    try:
        shown,changed=recolor(raw,preferences['appearance'])
        files['scope-dashboard-effect.png']=shown
        artifacts['scope-dashboard-effect.png']={'status':'ok','captured_utc':image_time,
            'kind':'dashboard channel color effect','changed_channel_pixels':changed}
    except ScopeError as e:
        artifacts['scope-dashboard-effect.png']={'status':'unavailable','reason':str(e)}
    warnings=[]
    for ch in ('CH1','CH2'):
        name=ch+'.csv'
        try:
            csv_data,preamble,stamp=waveform_csv(s,ch)
            files[name]=csv_data.encode()
            artifacts[name]={'status':'ok','waveform_read_utc':stamp,'point_format':preamble['point_format'],
                             'values':preamble['points'],'record_identifier':preamble['waveform_id']}
        except ScopeError as e:
            if e.status!=409:
                raise
            message=str(e)
            files[ch+'-unavailable.txt']=(ch+' waveform was not exported.\n'+message+
                '\nThe controller did not enable the channel or alter acquisition.\n').encode()
            artifacts[name]={'status':'unavailable','reason':message}
            warnings.append(ch+': '+message)
    readings=measurement_entries(s,preferences['measurements'])
    files['measurements.json']=json.dumps(readings,indent=2,allow_nan=False).encode()
    after=state_reader(s,connection)
    files['settings.json']=json.dumps({'captured_utc':utc(),'controller_version':version,
        'instrument_settings_before':before,'instrument_settings_after':after,
        'controller_preferences':preferences,
        'settings_scope':'Controller-supported instrument fields and displayed measurement-slot configuration; not a complete factory setup image.'},
        indent=2,allow_nan=False).encode()
    manifest={'format':'fischer-tektronix-test-capture','schema_version':1,'controller_version':version,
              'started_utc':started,'finished_utc':utc(),'scope_address':connection['address'],
              'reported_identity':before['identity'],'artifacts':artifacts,'warnings':warnings,
              'complete':all(artifacts[ch+'.csv']['status']=='ok' for ch in ('CH1','CH2')),
              'consistency':'Sequential capture. Acquisition is not paused, stopped, restarted or rearmed. Images, measurements and channel records can represent different acquisitions.',
              'waveform_warning':'Each CSV uses the stored record preamble. Stored records may predate current settings. Timestamps are host read times, not instrument trigger times.'}
    files['manifest.json']=json.dumps(manifest,indent=2,allow_nan=False).encode()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items():
            archive.writestr(name,data)
    return output.getvalue(),manifest
