import json
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch
from adapter_broker import Coordinator
from adapter_worker import meter, supply, function_key, pulse, menu_read, menu_set


CFG = {'hardware_enabled': True, 'addresses': {'supply': 10, 'meter': 22}, 'resource': 'FAKE'}


def req(target, action, **data):
    return {'target': target, 'action': action, 'data': data}


class CoordinationTests(unittest.TestCase):
    def test_hardware_disabled_never_opens_adapter(self):
        runner = Mock()
        c = Coordinator({**CFG, 'hardware_enabled': False}, runner)
        self.assertFalse(c.execute(req('meter', 'identify'))['ok'])
        runner.assert_not_called()

    def test_read_only_phase_blocks_all_meter_writes_and_acquisition(self):
        runner=Mock();c=Coordinator({**CFG,'meter_read_only':True},runner)
        c.identified=c.configured=True
        for action in ('prepare','sample','single','function','range','digits','math','menu-set','local'):
            self.assertFalse(c.execute(req('meter',action))['ok'])
        runner.assert_not_called()

    def test_disconnected_supply_is_not_queried_during_meter_only_setup(self):
        runner=Mock();c=Coordinator({**CFG,'supply_enabled':False},runner)
        self.assertFalse(c.execute(req('supply','snapshot'))['ok'])
        runner.assert_not_called()

    def test_identity_then_configuration_required_before_measurements(self):
        runner = Mock(return_value={'ok': True, 'result': {}})
        c = Coordinator(CFG, runner)
        self.assertFalse(c.execute(req('meter', 'sample'))['ok'])
        self.assertTrue(c.execute(req('meter', 'identify'))['ok'])
        self.assertFalse(c.execute(req('meter', 'sample'))['ok'])
        self.assertTrue(c.execute(req('meter', 'configuration'))['ok'])
        self.assertTrue(c.execute(req('meter', 'sample'))['ok'])

    def test_complete_transactions_never_interleave(self):
        active, maximum, events = 0, 0, []
        guard = threading.Lock()
        def runner(payload, timeout):
            nonlocal active, maximum
            with guard:
                active += 1; maximum = max(maximum, active)
                events.append((payload['request']['target'], 'start'))
            time.sleep(.025)
            with guard:
                events.append((payload['request']['target'], 'end')); active -= 1
            return {'ok': True, 'result': {}}
        c = Coordinator(CFG, runner)
        threads = [threading.Thread(target=c.execute, args=(req('supply', 'snapshot'),)) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(maximum, 1)
        self.assertEqual([x[1] for x in events], ['start','end']*5)

    def test_timeout_releases_owner_and_supply_still_succeeds(self):
        started = threading.Event()
        recoveries = []
        def runner(payload, timeout):
            if payload['request']['target'] == 'meter':
                started.set(); time.sleep(.12); raise TimeoutError('unresponsive meter')
            recoveries.append(payload['recover'])
            return {'ok': True, 'result': {'OUT': 0}}
        c = Coordinator(CFG, runner); c.identified = c.configured = True
        t = threading.Thread(target=c.execute, args=(req('meter', 'sample'),)); t.start(); started.wait(1)
        now = time.monotonic()
        result = c.execute(req('supply', 'snapshot'))
        t.join()
        self.assertTrue(result['ok']); self.assertLess(time.monotonic()-now, .5)
        self.assertFalse(c.execute(req('meter', 'identify'))['ok'])
        self.assertTrue(c.execute(req('supply', 'snapshot'))['ok'])
        self.assertEqual(recoveries, [True, False])

    def test_bad_request_cannot_execute_arbitrary_commands(self):
        runner=Mock(); c=Coordinator(CFG, runner)
        self.assertFalse(c.execute(req('meter', '*RST'))['ok']); runner.assert_not_called()

    def test_wrong_identity_is_rejected(self):
        dev=Mock(); dev.query.return_value='HEWLETT-PACKARD,6033A,0,1'
        with self.assertRaises(RuntimeError): meter(dev,'identify',{})
        dev.write.assert_not_called()

    def test_identify_is_read_only(self):
        dev=Mock(); dev.query.return_value='HEWLETT-PACKARD,34401A,123,1.0'
        self.assertIn('34401A',meter(dev,'identify',{})['identity']); dev.write.assert_not_called()

    def test_external_trigger_refused_without_read_command(self):
        dev=Mock(); dev.query.side_effect=['"VOLT:DC"','EXT','1','1','0']
        with self.assertRaises(RuntimeError): meter(dev,'sample',{})
        self.assertNotIn('READ?', [x.args[0] for x in dev.query.call_args_list])

    def test_overload_is_not_a_numeric_reading(self):
        dev=Mock(); dev.query.side_effect=['"VOLT:DC"','IMM','1','1','0','9.9e37','0','NULL']
        r=meter(dev,'sample',{}); self.assertIsNone(r['value']); self.assertTrue(r['overload'])

    def test_supply_output_on_readback_guards_remain(self):
        dev=Mock(); dev.query.side_effect=['VSET 5','ISET 0','OUT 0']
        with self.assertRaises(RuntimeError): supply(dev,'set',{'key':'output','value':True})
        dev.write.assert_not_called()

    def test_supply_settings_refused_when_output_is_on(self):
        dev=Mock(); dev.query.return_value='OUT 1'
        with self.assertRaises(RuntimeError): supply(dev,'set',{'key':'voltage','value':5})
        dev.write.assert_not_called()

    def test_output_off_does_not_require_output_on_prerequisites(self):
        dev=Mock(); dev.query.return_value='OUT 0'
        self.assertEqual(supply(dev,'output_off',{}),0)
        dev.write.assert_called_once_with('OUT OFF')

    def test_nonfinite_supply_setting_refused(self):
        with self.assertRaises(ValueError): supply(Mock(),'set',{'key':'voltage','value':float('nan')})

    def test_function_aliases(self):
        self.assertEqual(function_key('"VOLTAGE:DC"'),'dcv')
        self.assertEqual(function_key('"FRES"'),'ohm4')
        self.assertEqual(function_key('"VOLT"'),'dcv')
        self.assertEqual(function_key('"CURR"'),'dci')

    def test_address_pulse_reuses_the_owned_usb_handle(self):
        rm,dev,interface=Mock(),Mock(),Mock();dev.session=5
        rm.visalib.sessions={5:Mock(interface=interface)}
        interface.usb_intf.index=0
        pulse(rm,dev)
        interface.usb_dev.ctrl_transfer.assert_called_once_with(0xa1,0x40,0,0,1,timeout=600)
        dev.control_in.assert_not_called()

    def test_digit_shortcuts_follow_manual_not_fast_integration_defaults(self):
        for digits,plc in ((4,'1'),(5,'10'),(6,'10')):
            dev=Mock();dev.query.side_effect=['"VOLT:DC"','0,"No error"']
            with patch('adapter_worker.config_readback',return_value={'nplc':float(plc)}):
                meter(dev,'digits',{'digits':digits})
            dev.write.assert_called_once_with('VOLT:DC:NPLC '+plc)

    def test_frequency_digits_use_documented_gate_time(self):
        dev=Mock();dev.query.side_effect=['"FREQ"','0,"No error"']
        with patch('adapter_worker.config_readback',return_value={'aperture':1}):
            meter(dev,'digits',{'digits':6})
        dev.write.assert_called_once_with('FREQ:APER 1')

    def test_ac_digits_are_explicit_web_mask_without_a_rejected_meter_write(self):
        dev=Mock();dev.query.side_effect=['"VOLT:AC"','0,"No error"']
        with patch('adapter_worker.config_readback',return_value={'function':'acv'}):
            result=meter(dev,'digits',{'digits':4})
        dev.write.assert_not_called()
        self.assertIn('web display mask',result['digits_effect'])

    def test_db_refused_for_current_without_writing(self):
        dev=Mock();dev.query.return_value='"CURR:DC"'
        with self.assertRaises(ValueError):meter(dev,'math',{'mode':'db'})
        dev.write.assert_not_called()

    def test_math_button_toggles_off_after_reading_state(self):
        dev=Mock();dev.query.side_effect=['"VOLT:DC"','NULL','1','0,"No error"']
        with patch('adapter_worker.config_readback',return_value={'math_enabled':False}):
            meter(dev,'math',{'mode':'null'})
        dev.write.assert_called_once_with('CALC:STAT OFF')

    def test_auto_man_toggles_existing_autorange(self):
        dev=Mock();dev.query.side_effect=['"VOLT:DC"','1','0,"No error"']
        with patch('adapter_worker.config_readback',return_value={'autorange':False}):
            meter(dev,'range',{'direction':'toggle'})
        dev.write.assert_called_once_with('VOLT:DC:RANG:AUTO OFF')

    def test_menu_setting_is_read_back_and_checked(self):
        dev=Mock();dev.query.side_effect=['0,"No error"','BUS']
        with patch('adapter_worker.config_readback',return_value={'trigger_source':'BUS'}):
            result=menu_set(dev,'trigger-source','BUS')
        self.assertEqual(result['value'],'BUS')
        dev.write.assert_called_once_with('TRIG:SOUR BUS')

    def test_invalid_menu_command_refused(self):
        dev=Mock()
        with self.assertRaises(ValueError):menu_set(dev,'calibration-unlock','secret')
        dev.write.assert_not_called()

    def test_front_rear_selector_has_readback_but_no_remote_write(self):
        dev=Mock();dev.query.return_value='FRON'
        self.assertEqual(menu_read(dev,'terminals')['value'],'FRON')
        with self.assertRaises(ValueError):menu_set(dev,'terminals','REAR')
        dev.write.assert_not_called()

    def test_bus_single_trigger_is_an_entire_init_trigger_fetch_transaction(self):
        dev=Mock();dev.query.side_effect=['"VOLT:DC"','BUS','1','1','0','1.0','0','NULL']
        result=meter(dev,'single',{})
        self.assertEqual(result['value'],1)
        self.assertEqual([x.args[0] for x in dev.write.call_args_list],['INIT','*TRG'])
        self.assertIn('FETC?',[x.args[0] for x in dev.query.call_args_list])

    def test_hard_deadline_kills_and_reaps_worker_before_return(self):
        proc=Mock(); proc.communicate.side_effect=[subprocess.TimeoutExpired('worker',1.8),('','')]
        proc.__enter__=Mock(return_value=proc); proc.__exit__=Mock(return_value=False)
        with patch('adapter_broker.subprocess.Popen', return_value=proc):
            with self.assertRaises(TimeoutError): Coordinator(CFG).run_worker({},1.8)
        proc.kill.assert_called_once(); self.assertEqual(proc.communicate.call_count,2)


if __name__=='__main__': unittest.main(verbosity=2)

class UsbRecoveryTests(unittest.TestCase):
    def test_stuck_kernel_worker_refuses_competing_connection(self):
        runner=Mock()
        c=Coordinator(CFG,runner)
        c.stuck_worker=Mock()
        c.stuck_worker.poll.return_value=None
        result=c.execute(req('supply','snapshot'))
        self.assertFalse(result['ok'])
        self.assertIn('USB driver is stuck',result['error'])
        runner.assert_not_called()
        self.assertFalse(c.lock.locked())

    def test_reconnect_clears_stale_recovery_and_identity(self):
        runner=Mock(return_value={'ok':True,'result':{'identity':'test'}})
        with patch.object(Coordinator,'current_usb_generation',return_value=(('1','4'),)):
            c=Coordinator(CFG,runner)
        c.recover=True
        c.cooldown_until=time.monotonic()+10
        c.identified=c.configured=True
        with patch.object(c,'current_usb_generation',return_value=(('1','7'),)):
            result=c.execute(req('meter','identify'))
        self.assertTrue(result['ok'])
        self.assertFalse(runner.call_args.args[0]['recover'])
        self.assertTrue(c.identified)
        self.assertFalse(c.configured)
