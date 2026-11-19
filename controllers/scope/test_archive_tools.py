import copy,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import archive_tools as tools
from app import FIELDS,command_for,app
from scope_io import ScopeError,measurement_result,measurement_entries
from example_catalog import example_by_id
from test_screen_effect import synthetic

class FakeMeasurements:
    def __init__(self):
        self.writes=[]
        self.settings={'MEASUREMENT:IMMED:SOURCE1':'CH1','MEASUREMENT:IMMED:TYPE':'MEAN'}
    def ask(self,q):
        if q.startswith('SELECT:'):return '1'
        if q.startswith('MEASUREMENT:MEAS'):
            n=int(q.split(':')[1][4:]);field=q.split(':')[2]
            if field=='SOURCE1?':return 'CH2'
            if field=='TYPE?':return 'FREQ'
            if field=='STATE?':return '1' if n==2 else '0'
            if field=='DATA?':return '40.13,541'
            if field=='UNITS?':return '"Hz"'
        if q=='MEASUREMENT:IMMED:DATA?':return '0.1,0'
        if q=='MEASUREMENT:IMMED:UNITS?':return '"V"'
        return self.settings[q[:-1]]
    def write(self,cmd):
        self.writes.append(cmd);key,val=cmd.split(' ',1);self.settings[key]=val

class MeasurementQualityTests(unittest.TestCase):
    def test_warning_retains_finite_value_with_uncertainty(self):
        for code in (540,541,542,543):
            r=measurement_result('40.13,'+str(code),'Hz')
            self.assertTrue(r['valid']);self.assertEqual(r['quality'],'warning')
            self.assertEqual(r['value'],40.13);self.assertTrue(r['reason'])
        self.assertIn('Low signal',measurement_result('40.13,541','Hz')['reason'])
    def test_errors_and_sentinels_never_become_trusted_values(self):
        for raw in ('9.9E37,541','nan,543','1,2208','-1,541'):
            self.assertIsNone(measurement_result(raw,'Hz')['value'])
    def test_matching_scope_display_slot_is_used_without_immediate_writes(self):
        s=FakeMeasurements()
        r=measurement_entries(s,[{'id':'f','channel':'CH2','type':'frequency','on_scope':False}])
        self.assertEqual(r['entries'][0]['scope_slot'],2)
        self.assertEqual(r['entries'][0]['value'],40.13)
        self.assertEqual(s.writes,[])
    def test_nonmatching_entry_restores_immediate_configuration(self):
        s=FakeMeasurements();old=dict(s.settings)
        r=measurement_entries(s,[{'id':'v','channel':'CH1','type':'mean','on_scope':False}])
        self.assertEqual(r['entries'][0]['basis'],'Immediate measurement')
        self.assertEqual(s.settings,old)

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patcher=patch.object(tools,'ROOT',self.root);self.patcher.start()
        self.current={'connection':{'address':'192.168.1.78','timeout':6.0},
            'appearance':{'ch1':'#f2d56a','ch2':'#79b8ff'},'measurements':[],'presets':{}}
        for key,name in tools.SETTINGS_FILES.items():
            (self.root/name).write_text(json.dumps(self.current[key],indent=2))
        self.wanted=copy.deepcopy(self.current);self.wanted['connection']['address']='scope.local'
        self.wanted['appearance']['ch1']='#123456'
    def tearDown(self):
        self.patcher.stop();self.tmp.cleanup()
    def test_export_validation_and_restore_round_trip(self):
        backup=tools.export_backup(self.wanted,'test')
        valid=tools.validate_backup(backup,FIELDS,command_for)
        name=tools.restore_preferences(valid,self.current,'test')
        self.assertEqual(json.loads((self.root/'connection.json').read_text())['address'],'scope.local')
        previous=json.loads(tools.read_restore_point(name))
        self.assertEqual(previous['settings'],self.current)
    def test_invalid_backup_is_rejected_before_changes(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        bad=tools.export_backup(self.wanted,'test');bad['settings']['appearance']['ch1']='javascript:bad'
        with self.assertRaises(ScopeError):tools.validate_backup(bad,FIELDS,command_for)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
    def test_mid_restore_failure_rolls_back_exact_bytes(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        real=tools.atomic_json;calls=0
        def fail_on_third(path,data):
            nonlocal calls
            calls+=1
            if calls==3:raise OSError('simulated disk write failure')
            return real(path,data)
        with patch.object(tools,'atomic_json',fail_on_third):
            with self.assertRaises(ScopeError):tools.restore_preferences(self.wanted,self.current,'test')
        for name,data in before.items():self.assertEqual((self.root/name).read_bytes(),data)
    def test_restore_point_cannot_escape_directory(self):
        with self.assertRaises(ScopeError):tools.read_restore_point('../connection.json')

class CaptureTests(unittest.TestCase):
    def capture(self,csv_side_effect=None):
        s=FakeMeasurements();png,_,_=synthetic()
        prefs={'appearance':{'ch1':'#ff0000','ch2':'#00ff00'},'measurements':[]}
        csv_value=('time_seconds,voltage_volts,raw_sample\n0,1,10\n',{'point_format':'Y','points':500,'waveform_id':'stored record'},'2026-11-14T00:00:00+00:00')
        with patch.object(tools,'waveform_csv',side_effect=csv_side_effect,return_value=csv_value),patch.object(tools,'measurement_entries',return_value={'entries':[]}):
            data,manifest=tools.make_capture(s,{'address':'scope.local'},'test',prefs,
                lambda *_:{'identity':'TEKTRONIX,TDS 3052B,test','running':'1'},lambda _:png)
        return s,data,manifest,png
    def test_bundle_contains_original_both_csvs_and_current_settings(self):
        s,data,m,png=self.capture()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertTrue({'scope-original.png','scope-dashboard-effect.png','CH1.csv','CH2.csv','settings.json','measurements.json','manifest.json'}<=set(z.namelist()))
            self.assertEqual(z.read('scope-original.png'),png)
        self.assertTrue(m['complete']);self.assertEqual(s.writes,[])
    def test_disabled_channel_is_explicitly_partial_not_a_fake_csv(self):
        v=('x\n',{'point_format':'Y','points':500,'waveform_id':'stored'},'time')
        _,data,m,_=self.capture([v,ScopeError('CH2 is off',409)])
        self.assertFalse(m['complete'])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn('CH2-unavailable.txt',z.namelist());self.assertNotIn('CH2.csv',z.namelist())
    def test_transport_failure_does_not_offer_a_successful_bundle(self):
        with self.assertRaises(TimeoutError):self.capture([TimeoutError('timed out')])

class ExampleTests(unittest.TestCase):
    def test_elevator_is_incomplete_and_has_no_invented_timing(self):
        e=example_by_id('sony-elevator')
        self.assertFalse(e['recallable']);self.assertNotIn('timebase',e['settings'])
        self.assertFalse(any(k.startswith('trigger_') for k in e['settings']))
        c=app.test_client()
        r=c.post('/api/examples/sony-elevator/recall',json={},headers={'Origin':'http://localhost'})
        self.assertEqual(r.status_code,409)
    def test_serial_has_explicit_probes_channels_and_trigger(self):
        e=example_by_id('sony-serial')
        self.assertEqual(e['connections'][0]['point'],'IC503 pin 24')
        self.assertEqual(e['connections'][1]['point'],'IC503 pin 26')
        self.assertEqual(e['settings']['trigger_source'],'CH1')
        self.assertEqual(e['settings']['ch1_probe'],'10')
        self.assertIn('not a verified',e['status'])

if __name__=='__main__':unittest.main(verbosity=2)
