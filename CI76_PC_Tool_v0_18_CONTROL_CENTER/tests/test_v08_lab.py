"""Pure software tests. No real serial port or actuator is connected."""
from __future__ import annotations
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from PySide6.QtCore import QThread
except ImportError:
    pkg = sys.modules.setdefault('PySide6', types.ModuleType('PySide6'))
    mod = sys.modules.setdefault('PySide6.QtCore', types.ModuleType('PySide6.QtCore'))
    class QThread:
        def __init__(self, *a, **kw): pass
    class Signal:
        def __init__(self, *a): pass
        def __get__(self, instance, owner): return self
        def emit(self, *a): pass
    mod.QThread, mod.Signal = QThread, Signal
from worker import SerialWorker
from protocol import ProtocolError

class DummyDevice:
    def __init__(self):
        self.fw = 'legacy'
        self.motor_status = b'\x01'
        self.errors = b'\x00\x00'
        self.pos_raw = 500
        self.mode = 0
        self.writes = []
        self.stop_error = False

    def read_cmd(self, cmd, *, timeout=1.2):
        if cmd == 0x70: return b'\x01\x01\x0b'
        if cmd == 0x71: return b'\x01\x01\x0b'
        if cmd == 0x12: return self.motor_status
        if cmd == 0x13: return bytes([self.mode, 1])
        if cmd == 0x17: return self.errors
        if cmd == 0x11: return self.pos_raw.to_bytes(2, 'little')
        if cmd == 0x20: return b'\xe8\x03' + b'\x00'*8
        raise ValueError(f'unknown cmd: {cmd}')

    def write_cmd(self, cmd, payload, *, timeout=1.2):
        self.writes.append((cmd, bytes(payload)))
        if cmd == 0x09 and payload == b'\x00\x00\x01' and self.stop_error:
            raise TimeoutError('STOP not acknowledged')
        if cmd == 0x03: self.mode = payload[0]
        return payload

class LegacyBenchTests(unittest.TestCase):
    def setUp(self):
        self.worker = SerialWorker()
        self.dev = DummyDevice()
        self.worker.client = self.dev

    def test_mode_requires_fault_free_idle_and_readback(self):
        self.dev.errors = b'\x08\x00'
        with self.assertRaises(ProtocolError): self.worker._bench_uart_mode(True)
        self.assertEqual(self.dev.writes, [])
        self.dev.errors = b'\x00\x00'
        self.assertEqual(self.worker._bench_uart_mode(True)['enabled'], True)
        self.assertEqual(self.dev.writes[:2], [(0x09,b'\x00\x00\x01'),(0x03,b'\x01')])
        self.assertTrue(self.worker.bench_uart_enabled)
        self.worker._bench_uart_mode(False)
        self.assertEqual(self.dev.writes[-2:], [(0x09,b'\x00\x00\x01'),(0x03,b'\x00')])
        self.assertFalse(self.worker.bench_uart_enabled)

    def test_position_feedback_fault_blocks_mode_without_sending_stop(self):
        self.dev.errors = b'\x20\x00'
        with self.assertRaisesRegex(ProtocolError, '位置回授異常'):
            self.worker._bench_uart_mode(True)
        self.assertEqual(self.dev.writes, [])
        self.assertFalse(self.worker.bench_uart_enabled)

    def test_start_requires_explicit_uart_mode(self):
        with self.assertRaisesRegex(ProtocolError, 'UART MODE'):
            self.worker._start_bench('extend', 20)
        self.assertEqual(self.dev.writes, [])

    def test_2_second_test_auto_sends_stop_and_keeps_uart_mode(self):
        self.worker._bench_uart_mode(True)
        started = self.worker._start_bench('extend', 20)
        self.assertTrue(started['legacy_fw'])
        self.assertEqual(self.dev.writes[-2:], [(0x07,b'\xc8\x00'),(0x09,b'\x00\x00\x02')])
        self.assertTrue(self.worker.bench_limited_motion)
        self.worker.bench_deadline = 0.0  # simulate 2 seconds elapsed
        self.worker._check_bench_deadline()
        self.assertIsNone(self.worker.motor_direction)
        self.assertTrue(self.worker.bench_uart_enabled)
        self.assertIn((0x09,b'\x00\x00\x01'), self.dev.writes)
        self.assertIn((0x07,b'\xe8\x03'), self.dev.writes)  # restore old speed
        self.assertEqual(self.dev.mode, 1)

    def test_physical_I1_not_used_as_stop_command(self):
        self.worker._bench_uart_mode(True)
        self.worker._start_bench('retract', 10)
        self.worker._stop_motor()
        self.assertEqual(self.dev.writes[-2:], [(0x09,b'\x00\x00\x01'),(0x07,b'\xe8\x03')])

    def test_near_limit_rejected(self):
        self.worker._bench_uart_mode(True)
        self.dev.pos_raw = 960
        with self.assertRaisesRegex(ProtocolError, '端點'):
            self.worker._start_bench('extend', 20)
        self.dev.pos_raw = 40
        with self.assertRaisesRegex(ProtocolError, '端點'):
            self.worker._start_bench('retract', 20)

    def test_stop_cancels_not_yet_executed_start(self):
        self.worker._bench_uart_mode(True)
        self.worker.submit('bench_start', ('extend',20))
        self.worker.submit('motor_stop')
        with self.assertRaisesRegex(ProtocolError, '取消'):
            self.worker._start_bench('extend',20)
        self.assertNotIn((0x09,b'\x00\x00\x02'), self.dev.writes)

    def test_stop_failure_never_claims_success(self):
        self.worker._bench_uart_mode(True)
        self.worker._start_bench('extend', 20)
        self.dev.stop_error = True
        with self.assertRaises(TimeoutError): self.worker._stop_motor()
        self.assertIsNone(self.worker.motor_direction)
        self.assertTrue(self.worker.bench_uart_enabled) # mode might still be ON at the MCU

    def test_speed_cap(self):
        self.worker._bench_uart_mode(True)
        with self.assertRaisesRegex(ProtocolError, '1～100'):
            self.worker._start_bench('extend', 101)

if __name__ == '__main__': unittest.main()
