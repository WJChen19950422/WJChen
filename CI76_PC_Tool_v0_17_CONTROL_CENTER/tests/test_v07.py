import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import (encode_frame, decode_frame, parse_error_counters, build_motor_time_reset,
                      parse_motor_seconds, ProtocolError)
from motion import (firmware_motion_supported, motor_position_command, motor_speed_command,
                    validate_start)
from eventlog import EventLog


class V07Tests(unittest.TestCase):
    def test_fw_gate_rejects_old_or_wrong_device(self):
        self.assertFalse(firmware_motion_supported('0x0B01', '0x0B01'))
        self.assertFalse(firmware_motion_supported('0x0B02', '0x0001'))
        self.assertTrue(firmware_motion_supported('0x0B02', '0x0B01'))

    def test_direction_frames(self):
        cmd, payload = motor_position_command('extend')
        self.assertEqual(encode_frame(cmd, payload), bytes.fromhex('B0 07 09 00 00 02 C2'))
        cmd, payload = motor_position_command('retract')
        self.assertEqual(payload, b'\x00\x00\x03')
        cmd, payload = motor_position_command('stop')
        self.assertEqual(payload, b'\x00\x00\x01')

    def test_speed_limits(self):
        self.assertEqual(motor_speed_command(20), (0x07, b'\xc8\x00'))
        self.assertEqual(motor_speed_command(70),(0x07,(700).to_bytes(2,'little')))
        self.assertEqual(motor_speed_command(0),(0x07,b'\x00\x00'))
        with self.assertRaises(ProtocolError):
            motor_speed_command(101)

    def test_status_flag_guard(self):
        validate_start(b'\x01', b'\x00\x01', b'\x00\x00')
        for status, flags in ((b'\x05',b'\x00\x00'), (b'\x01',b'\x01\x00')):
            with self.assertRaises(ProtocolError):
                validate_start(status, b'\x00\x01', flags)

    def test_reset_frame(self):
        cmd, payload = build_motor_time_reset()
        self.assertEqual(encode_frame(cmd, payload), bytes.fromhex('B0 05 0F 03 C7'))
        self.assertEqual(parse_motor_seconds(b'\x00'*4), 0)

    def test_counters(self):
        self.assertEqual(parse_error_counters(bytes.fromhex('02 00 01 00 03 00 06 00')),
                         {'voltage':2,'current':1,'position':3,'total':6})
        with self.assertRaises(ProtocolError):
            parse_error_counters(b'\x00')

    def test_session_log_and_report(self):
        with tempfile.TemporaryDirectory() as folder:
            log = EventLog(Path(folder))
            log.append('fault', flags='08 00')
            reports = log.export_snapshot({'counters':{'current':2}}, Path(folder) / 'report.json')
            records = [json.loads(s) for s in log.file.read_text(encoding='utf8').splitlines()]
            self.assertEqual(records[1]['event'], 'fault')
            self.assertEqual(json.loads(reports.read_text(encoding='utf8'))['counters']['current'],2)


if __name__ == '__main__':
    unittest.main()
