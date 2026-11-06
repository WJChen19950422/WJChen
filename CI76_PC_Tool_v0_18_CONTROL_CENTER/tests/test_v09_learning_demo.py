"""v0.9 lab-only command logic tests. No CI76 hardware is touched."""
from __future__ import annotations
import sys
import types
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import PySide6.QtCore
except ImportError:
    # Existing worker tests use the same minimal QObject placeholders.
    pkg = types.ModuleType('PySide6')
    qtcore = types.ModuleType('PySide6.QtCore')
    class QThread:
        def __init__(self, *a, **kw): pass
    class Signal:
        def __init__(self, *a): pass
        def __get__(self, instance, owner): return self
        def emit(self, *a): pass
    qtcore.QThread,qtcore.Signal = QThread,Signal
    sys.modules['PySide6'] = pkg
    sys.modules['PySide6.QtCore'] = qtcore
from lab_features import learning_payload, learning_preflight, demo_current_write, learning_observation
from worker import SerialWorker
from protocol import ProtocolError, parse_group, build_write

class FakeClient:
    def __init__(self):
        self.writes=[]
        self.status=b'\x01'
        self.faults=b'\x20\x00'
        self.uart_mode=0
        self.current=(100).to_bytes(2,'little')+(900).to_bytes(2,'little')+(500).to_bytes(2,'little')
    def read_cmd(self, cmd, *, timeout=1.2):
        if cmd==0x70: return b'\x01\x01\x0b'
        if cmd==0x71: return b'\x01\x01\x0b'
        if cmd==0x12: return self.status
        if cmd==0x13: return bytes((self.uart_mode, 1))
        if cmd==0x17: return self.faults
        if cmd==0x19: return self.current
        if cmd==0x11: return b'\x64\x00'
        if cmd==0x10: return b'\x0a\x00'
        if cmd==0x14: return b'\x00'*4
        raise ValueError(cmd)
    def write_cmd(self, cmd, payload, *, timeout=1.2):
        self.writes.append((cmd,bytes(payload)))
        if cmd==0x06: self.current=bytes(payload)
        if cmd==0x03: self.uart_mode=payload[0]
        return payload

class LearningDemoTests(unittest.TestCase):
    def test_learning_command_values(self):
        self.assertEqual(learning_payload(True),(0x02,b'\x01'))
        self.assertEqual(learning_payload(False),(0x02,b'\x00'))
    def test_learning_allows_only_expected_0x20(self):
        self.assertTrue(learning_preflight(b'\x01',b'\x00\x01',b'\x20\x00'))
        with self.assertRaises(ProtocolError): learning_preflight(b'\x05',b'\x00\x01',b'\x20\x00')
        with self.assertRaises(ProtocolError): learning_preflight(b'\x01',b'\x01\x01',b'\x20\x00')
        with self.assertRaises(ProtocolError): learning_preflight(b'\x01',b'\x00\x01',b'\x28\x00')
    def test_learning_requests_ack_not_completion(self):
        w=SerialWorker();w.client=FakeClient()
        out=w._start_learning()
        self.assertEqual(out,{'request_ack':True,'complete':False})
        self.assertTrue(w.learning_active)
        self.assertEqual(w.client.writes,[(0x02,b'\x01')])
    def test_queued_learning_start_cannot_run_after_cancel(self):
        w=SerialWorker(); w.client=FakeClient()
        w.submit('learning_start')
        w.submit('learning_abort')
        w._service_urgent()
        with self.assertRaises(ProtocolError): w._start_learning()
        self.assertNotIn((0x02,b'\x01'),w.client.writes)
    def test_learning_abort_sends_abort_and_stop(self):
        w=SerialWorker();w.client=FakeClient();w._start_learning()
        answer=w._abort_learning()
        self.assertTrue(answer['abort_ack'])
        self.assertFalse(answer['physical_stop_verified'])
        self.assertEqual(w.client.writes[-2:],[(0x02,b'\x00'),(0x09,b'\x00\x00\x01')])
        self.assertFalse(w.learning_active)
    def test_learning_observation_requires_seen_and_flags(self):
        self.assertEqual(learning_observation(False,b'\x01',b'\x00\x00'),'pending')
        self.assertEqual(learning_observation(True,b'\x05',b'\x20\x00'),'learning')
        self.assertEqual(learning_observation(True,b'\x01',b'\x20\x00'),'pending')
        self.assertEqual(learning_observation(True,b'\x01',b'\x00\x00'),'completed_candidate')
        self.assertEqual(learning_observation(True,b'\x01',b'\x40\x00'),'failed')
    def test_demo_preserves_other_current_settings(self):
        old=FakeClient().current
        cmd,payload,values,requested=demo_current_write(old,1.50)
        self.assertEqual(cmd,0x06)
        self.assertEqual(payload,(150).to_bytes(2,'little')+old[2:])
        self.assertEqual(values['current_overload'],9.00)
        self.assertEqual(requested['current_limit'],1.5)
    def test_demo_new_firmware_range_0_to_8(self):
        old=FakeClient().current
        for value in (-0.01,8.01,10.0):
            with self.assertRaises(ProtocolError): demo_current_write(old,value)
        for value in (0.0,0.02,8.0):
            cmd,raw,_,requested=demo_current_write(old,value)
            self.assertEqual(cmd,0x06)
            self.assertEqual(int.from_bytes(raw[:2],'little'),round(value*100))
            self.assertEqual(requested['current_limit'],value)
    def test_worker_demo_readback_and_restore(self):
        w=SerialWorker();w.client=FakeClient();w.bench_uart_enabled=True
        original=w.client.current
        result=w._demo_limit(1.50)
        self.assertEqual(result['actual_A'],1.50)
        self.assertEqual(w.client.current[2:],original[2:])
        self.assertIsNotNone(w.demo_original_current)
        w.bench_uart_enabled=False
        out=w._demo_restore()
        self.assertTrue(out['restored'])
        self.assertEqual(w.client.current,original)
        self.assertIsNone(w.demo_original_current)
    def test_demo_refuses_when_learning(self):
        w=SerialWorker();w.client=FakeClient();w.bench_uart_enabled=True;w.learning_active=True
        with self.assertRaises(ProtocolError):w._demo_limit(1.5)
        self.assertEqual(w.client.writes,[])
    def test_no_demo_mode_exit_when_original_not_restored(self):
        w=SerialWorker();w.client=FakeClient();w.bench_uart_enabled=True
        w._demo_limit(1.50)
        with self.assertRaises(ProtocolError): w._bench_uart_mode(False)
if __name__=='__main__':unittest.main()
