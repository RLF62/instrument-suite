"""Offline regression checks for waveform scaling, validity, and restoration failures."""
import csv
import io
import struct
import unittest
from unittest.mock import patch
import scope_io as io_scope
from scope_io import ScopeError, measurement_result, parse_waveform, restore, validate_connection, waveform_csv

def record(fmt='Y', samples=None):
    if samples is None:
        samples = [-32000,0,1000,32767] + [100]*496
    payload = struct.pack('>'+str(len(samples))+'h',*samples)
    fields = ['2','16','BIN','RI','MSB','500','"Ch1, stored test record"',fmt,
              '0.000002','3','-0.001','"s"','0.002','1.5','100','"V"']
    prefix = ';'.join(fields).encode()
    return prefix+b';:CURV #'+str(len(str(len(payload)))).encode()+str(len(payload)).encode()+payload+b'\n'

class FakeScope:
    def __init__(self, raw=None):
        self.settings = dict(zip(io_scope.TRANSFER_KEYS,['CH2','17','321','1','RI','LSB','SRI']))
        self.original = self.settings.copy()
        self.writes=[]
        self.raw = raw or record()
        self.running='1'
    def ask(self,q):
        if q=='SELECT:CH1?': return '1'
        if q=='ACQUIRE:STATE?': return self.running
        if q=='ACQUIRE:STOPAFTER?': return 'SEQ'
        if q=='*IDN?': return 'TEKTRONIX,TDS 3052B,test'
        return self.settings[q[:-1]]
    def write(self,cmd):
        self.writes.append(cmd)
        if cmd=='WAVFRM?': return
        k,v=cmd.split(' ',1)
        self.settings[k]=v
    def read_raw(self): return self.raw

class WaveformTests(unittest.TestCase):
    def test_signed_scaling_and_point_origin(self):
        s=FakeScope()
        text,p,_=waveform_csv(s,'CH1')
        lines=[l for l in text.splitlines() if not l.startswith('#')]
        rows=list(csv.DictReader(lines))
        self.assertEqual(len(rows),500)
        self.assertAlmostEqual(float(rows[0]['time_seconds']),-.001006)
        self.assertAlmostEqual(float(rows[0]['voltage_volts']),1.5+.002*(-32000-100))
        self.assertEqual(int(rows[3]['raw_sample']),32767)
        self.assertEqual(s.settings,s.original)
        self.assertFalse(any(w.startswith('ACQUIRE:') for w in s.writes))
    def test_envelope_pairs_share_one_time(self):
        s=FakeScope(record('ENV',[-100,300]*250))
        text,_,_=waveform_csv(s,'CH1')
        rows=list(csv.DictReader(l for l in text.splitlines() if not l.startswith('#')))
        self.assertEqual(len(rows),250)
        self.assertAlmostEqual(float(rows[0]['voltage_min_volts']),1.1)
        self.assertAlmostEqual(float(rows[0]['voltage_max_volts']),1.9)
        self.assertAlmostEqual(float(rows[1]['time_seconds'])-float(rows[0]['time_seconds']),2e-6)
    def test_truncation_and_failure_restore_transfer_settings(self):
        s=FakeScope(record()[:-10])
        with self.assertRaises(ScopeError):
            waveform_csv(s,'CH1')
        self.assertEqual(s.settings,s.original)
    def test_incorrect_block_count_rejected(self):
        with self.assertRaises(ScopeError):
            parse_waveform(record(samples=[1,2]))
    def test_invalid_measurements(self):
        for raw in ('9.9E37,0','nan,0','1.2,2208','1.2,2228','-2,0','bad'):
            self.assertFalse(measurement_result(raw,'Hz')['valid'])
        self.assertTrue(measurement_result('0,0','V')['valid'])
        self.assertEqual(measurement_result('1.25,0','V')['value'],1.25)
    def test_connection_validation(self):
        for address in ('http://scope','127.0.0.1:80','1.2.3.999','a/b','-host','scope;reboot'):
            with self.assertRaises(ScopeError):
                validate_connection({'address':address})
        self.assertEqual(validate_connection({'address':'scope.local','timeout':3})['address'],'scope.local')
    def test_restore_attempts_all_settings(self):
        class Broken:
            def __init__(self):self.calls=[]
            def write(self,c):
                self.calls.append(c)
                if c.startswith('A '):raise OSError('connection lost')
            def ask(self,c):return '0'
        s=Broken()
        with self.assertRaises(ScopeError):
            restore(s,{'A':'1','B':'2'})
        self.assertIn('B 2',s.calls)

    def test_timeout_releases_lock_for_next_thread(self):
        import concurrent.futures
        import socket
        class TimedOutInstrument:
            def __init__(self,address):
                self.client=None
                self.abort_client=None
                self.link=None
                self.closed=False
            def ask(self,q):
                # Real socket receive timeout, without affecting the real scope.
                a,b=socket.socketpair()
                try:
                    a.settimeout(.02)
                    return a.recv(1)
                finally:
                    a.close();b.close()
            def close(self):
                raise AssertionError('Must not send destroy_link on a timed-out stream')
        with patch.object(io_scope,'BoundedInstrument',TimedOutInstrument):
            with self.assertRaises(TimeoutError):
                with io_scope.scope({'address':'test','timeout':1}) as (s,_):
                    s.ask('*IDN?')
        def subsequent_request():
            with io_scope.serialized():
                return 'lock acquired'
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            self.assertEqual(pool.submit(subsequent_request).result(timeout=1),'lock acquired')

if __name__=='__main__':
    unittest.main(verbosity=2)
