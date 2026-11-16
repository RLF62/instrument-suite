import unittest
import time
from unittest.mock import patch
from flask import Flask
import hp34401a as meter


class MeterViewTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__); meter.install(self.app); self.client=self.app.test_client()
        with meter.state_lock:
            meter.state.update(identity=None,configuration=None,value=None,reading='—',unit='',
                               sample_time=None,source='disconnected',polling=False,prepared=False,error=None,
                               stats={'count':0,'min':None,'max':None,'mean':None})
            meter.state.update(acquisition='manual',hold_captured=False,hold_window=[],local_requested=False)

    def test_both_views_and_status_do_not_touch_hardware(self):
        with patch('hp34401a.execute') as execute:
            for path in ('/multimeter/classic','/multimeter/modern','/api/multimeter/status'):
                self.assertEqual(self.client.get(path).status_code,200)
            execute.assert_not_called()

    def test_identity_action_only_reads_identity_and_configuration(self):
        with patch('hp34401a.execute',side_effect=[{'identity':'HP,34401A,123,1'}, {'function':'dcv'}]) as execute:
            r=self.client.post('/api/control/meter/identify',json={})
            self.assertEqual(r.status_code,200)
            self.assertEqual([c.args for c in execute.call_args_list],[('meter','identify'),('meter','configuration')])
            self.assertFalse(r.json['polling']); self.assertFalse(r.json['prepared'])
            self.assertIsNone(r.json['value'])

    def test_sample_is_refused_before_operator_enables_measurements(self):
        with patch('hp34401a.execute') as execute:
            self.assertEqual(self.client.post('/api/control/meter/sample',json={}).status_code,409)
            execute.assert_not_called()

    def test_meter_error_stops_background_polling(self):
        with meter.state_lock: meter.state.update(prepared=True,polling=True)
        with patch('hp34401a.execute',side_effect=meter.AdapterError('Meter timed out')):
            r=self.client.post('/api/control/meter/sample',json={})
            self.assertEqual(r.status_code,503); self.assertFalse(r.json['state']['polling'])
            self.assertFalse(r.json['state']['prepared'])

    def test_user_control_waits_for_inflight_poll(self):
        import threading
        meter.operation_lock.acquire()
        release=threading.Timer(.15,meter.operation_lock.release)
        release.start()
        try:
            with patch('hp34401a.execute',return_value={'function':'acv'}) as execute:
                response=self.client.post('/api/control/meter/configuration',json={})
                self.assertEqual(response.status_code,200)
                execute.assert_called_once_with('meter','configuration')
            self.assertEqual(meter.state['pending_controls'],0)
        finally:
            release.join()

    def test_invalid_action_rejected(self):
        with patch('hp34401a.execute') as execute:
            self.assertEqual(self.client.post('/api/control/meter/reset',json={}).status_code,400)
            execute.assert_not_called()

    def test_format_does_not_invent_a_reading(self):
        self.assertEqual(meter.format_reading(None),'—')
        self.assertEqual(meter.format_reading(None,True),'OVLD')
        self.assertEqual(meter.format_reading(10),'+10.00000')
        with self.assertRaises(ValueError):meter.format_reading(float('nan'))

    def test_web_hold_waits_for_three_stable_readings(self):
        with meter.state_lock:
            meter.state.update(acquisition='hold',polling=True,prepared=True,hold_captured=False)
        value={'value':1.5,'overload':False,'unit':'V','sample_time':time.time()}
        with patch('hp34401a.execute',return_value=value):
            meter.sample();self.assertEqual(meter.snapshot()['source'],'waiting_hold')
            meter.sample();self.assertEqual(meter.snapshot()['source'],'waiting_hold')
            meter.sample();self.assertEqual(meter.snapshot()['source'],'held')
        self.assertEqual(meter.snapshot()['value'],1.5)

    def test_local_pauses_acquisition_before_request_and_does_not_query_after(self):
        with meter.state_lock:meter.state.update(polling=True,prepared=True)
        def request_local(*args,**kwargs):
            self.assertFalse(meter.state['polling'])
            return {'local_requested':True,'adapter_acknowledged':True,'instrument_mode_verified':False}
        with patch('hp34401a.execute',side_effect=request_local) as execute:
            response=self.client.post('/api/control/meter/local',json={})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json['local_requested'])
            execute.assert_called_once_with('meter','local')


if __name__=='__main__': unittest.main(verbosity=2)
