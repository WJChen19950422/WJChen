"""FW 0x0B01: software-only checks; not physical safety verification."""
from __future__ import annotations
import unittest
from test_v09_learning_demo import FakeClient
from worker import SerialWorker
from protocol import ProtocolError, encode_frame
from lab_features import error_clear_payload, validate_demo_speed, demo_current_write
from motion import motor_speed_command

class NewVersionTests(unittest.TestCase):
    def test_error_clear_command_only_active_flags(self):
        self.assertEqual(error_clear_payload(),(0x0F,b'\x02'))
        self.assertEqual(encode_frame(*error_clear_payload()), bytes.fromhex('B0 05 0F 02 C6'))
    def test_new_firmware_0_amps_encoding(self):
        cmd,raw,_,_=demo_current_write(FakeClient().current,0)
        self.assertEqual((cmd,raw[:2]), (0x06,b'\x00\x00'))
        cmd,raw,_,_=demo_current_write(FakeClient().current,.03)
        self.assertEqual((cmd,raw[:2]), (0x06,b'\x03\x00'))
    def test_high_current_within_overload_threshold_needs_no_ui_checkbox(self):
        w=SerialWorker();w.client=FakeClient()
        result=w._demo_limit(8)
        self.assertEqual(result['actual_A'],8)
        self.assertEqual(w.client.current[:2],b'\x20\x03')
    def test_unlearned_physical_demo_current_uart_off(self):
        w=SerialWorker();w.client=FakeClient()
        self.assertFalse(w.bench_uart_enabled)
        self.assertEqual(w.client.faults,b'\x20\x00')
        out=w._demo_limit(1.2)
        self.assertEqual(out['actual_A'],1.2)
        self.assertIn((0x06,b'\x78\x00'+w.client.current[2:]),w.client.writes)
    def test_fault_clear_does_not_lie_about_unlearned_0x20(self):
        w=SerialWorker();w.client=FakeClient()
        out=w._clear_active_faults()
        self.assertEqual(out['before'],'20 00')
        self.assertEqual(out['after'],'20 00')
        self.assertFalse(out['cleared'])
        self.assertIn((0x0F,b'\x02'),w.client.writes)
    def test_fault_clear_rejects_running_state(self):
        w=SerialWorker();w.client=FakeClient();w.client.status=b'\x02'
        with self.assertRaises(ProtocolError):w._clear_active_faults()
        self.assertNotIn((0x0F,b'\x02'),w.client.writes)
    def test_speed_0_to_100(self):
        self.assertEqual(motor_speed_command(100), (0x07, b'\xe8\x03'))
        self.assertEqual(validate_demo_speed(0),0)
        self.assertEqual(validate_demo_speed(100),1000)
        for val in (-1,101,21.3):
            with self.assertRaises(ProtocolError): validate_demo_speed(val)
    def test_demo_speed_write_and_restore(self):
        class Client(FakeClient):
            def __init__(self):
                super().__init__();self.speed=(200).to_bytes(2,'little')+b'\x00'*8
            def read_cmd(self,cmd,*,timeout=1.2):
                if cmd==0x20: return self.speed
                return super().read_cmd(cmd,timeout=timeout)
            def write_cmd(self,cmd,payload,*,timeout=1.2):
                if cmd==0x07:
                    self.writes.append((cmd,bytes(payload)))
                    self.speed=bytes(payload)+self.speed[2:]
                    return payload
                return super().write_cmd(cmd,payload,timeout=timeout)
        w=SerialWorker();w.client=Client()
        result=w._demo_speed(90)
        self.assertEqual(result['speed'],90)
        self.assertEqual(w.client.speed[:2],b'\x84\x03')
        w._demo_restore()
        self.assertEqual(w.client.speed[:2],b'\xc8\x00')
    def test_demo_speed_block_when_button_held(self):
        class Client(FakeClient):
            pass
        w=SerialWorker();w.client=Client();w.client.status=b'\x02'
        with self.assertRaises(ProtocolError):w._demo_speed(100)
        self.assertEqual(w.client.writes,[])

if __name__ == '__main__':unittest.main()
