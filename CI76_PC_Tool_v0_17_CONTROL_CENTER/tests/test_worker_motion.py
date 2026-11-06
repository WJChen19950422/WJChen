"""Software-only tests of motion worker. No motors/serial hardware are driven."""
from __future__ import annotations
import sys
import types
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import PySide6.QtCore  # type: ignore
except ImportError:
    pkg = types.ModuleType('PySide6')
    qtcore = types.ModuleType('PySide6.QtCore')
    class QThread:
        def __init__(self, *a, **kw): pass
    class Signal:
        def __init__(self, *a): pass
        def __get__(self, instance, owner):
            return self
        def emit(self, *a): pass
    qtcore.QThread, qtcore.Signal = QThread, Signal
    sys.modules['PySide6'] = pkg
    sys.modules['PySide6.QtCore'] = qtcore
from worker import SerialWorker
from protocol import ProtocolError


class FakeClient:
    def __init__(self, version=b'\x01\x02\x0b'):
        self.version = version
        self.writes = []
        self.uart_mode = 0
        self.motor_status = b'\x01'
        self.faults = b'\x00\x00'

    def read_cmd(self, cmd, *, timeout=1.2):
        if cmd == 0x70: return self.version
        if cmd == 0x71: return b'\x01\x01\x0b'
        if cmd == 0x12: return self.motor_status
        if cmd == 0x13: return bytes([self.uart_mode, 1])
        if cmd == 0x17: return self.faults
        if cmd == 0x14: return b'\x00\x00\x00\x00'
        if cmd == 0x16: return b'\x00'*8
        if cmd == 0x15: return b'\x01\x02\x03\x04'
        if cmd == 0x10: return b'\x10\x00'
        if cmd == 0x11: return b'\x64\x00'
        if cmd == 0x18: return b'\x00'*8
        if cmd == 0x19: return b'\x00'*6
        if cmd == 0x20: return b'\xe8\x03' + b'\x00'*8
        if cmd == 0x21: return b'\x00'*14
        raise ValueError(f'unknown cmd {cmd}')

    def write_cmd(self, cmd, payload, *, timeout=1.2):
        self.writes.append((cmd, payload))
        if cmd == 0x03:
            self.uart_mode = payload[0]
        return payload


class MotionWorkerTests(unittest.TestCase):
    def test_run_stop(self):
        w = SerialWorker()
        w.client = FakeClient()
        got = w._start_motor('extend', 20)
        self.assertEqual(got['direction'], 'extend')
        self.assertEqual(w.motor_direction, 'extend')
        self.assertEqual(w.client.writes[:3], [(0x03, b'\x01'), (0x07, b'\xc8\x00'), (0x09, b'\x00\x00\x02')])
        w.motor_last_tick = 0
        w._heartbeat()
        self.assertEqual(w.client.writes[-1], (0x09, b'\x00\x00\x02'))
        done = w._stop_motor()
        self.assertTrue(done['ack'])
        self.assertIsNone(w.motor_direction)
        self.assertEqual(w.client.writes[-3:], [(0x09, b'\x00\x00\x01'),(0x07, b'\xe8\x03'),(0x03, b'\x00')])

    def test_refuses_older_firmware(self):
        w = SerialWorker(); w.client = FakeClient(version=b'\x01\x01\x0b')
        with self.assertRaises(ProtocolError):
            w._start_motor('extend', 20)
        self.assertEqual(w.client.writes, [])

    def test_refuses_fault_flags(self):
        w = SerialWorker(); w.client = FakeClient(); w.client.faults = b'\x08\x00'
        with self.assertRaises(ProtocolError):
            w._start_motor('extend', 20)
        self.assertEqual(w.client.writes, [])

    def test_stop_send_failure_disarms_heartbeat(self):
        class BrokenStop(FakeClient):
            def write_cmd(self, cmd, payload, *, timeout=1.2):
                if cmd == 0x09 and payload[-1] == 1:
                    raise TimeoutError('USB cable lost')
                return super().write_cmd(cmd, payload, timeout=timeout)
        w = SerialWorker(); w.client = BrokenStop()
        w.motor_direction = 'extend'
        with self.assertRaises(TimeoutError):
            w._stop_motor()
        # Must NEVER keep sending motion heartbeats after a failed STOP.
        self.assertIsNone(w.motor_direction)

    def test_diagnostics(self):
        w = SerialWorker(); w.client = FakeClient()
        result = w._diagnostics()
        self.assertEqual(result['device'], '0x0B01')
        self.assertEqual(result['motor_seconds'], 0)
        self.assertEqual(set(result['counters']), {'voltage','current','position','total'})


if __name__ == '__main__': unittest.main()
