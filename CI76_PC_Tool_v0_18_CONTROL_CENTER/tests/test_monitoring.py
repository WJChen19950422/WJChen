import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitoring import decode_monitor, gauge_value, scheduled_monitor_commands
from diagnostics import FLAGS, decode_error_flags, error_summary
from protocol import READ_RESPONSE, ProtocolError, encode_frame


class LiveTelemetryTests(unittest.TestCase):
    def test_current_raw_to_amperes(self):
        self.assertEqual(decode_monitor(0x10, bytes.fromhex('fa 00')), {'current': 2.5})

    def test_position_raw_to_percent(self):
        self.assertEqual(decode_monitor(0x11, bytes.fromhex('ed 01')), {'position': 49.3})

    def test_no_unsupported_voltage_command(self):
        self.assertNotIn(0x31, READ_RESPONSE)
        with self.assertRaises(ValueError):
            decode_monitor(0x31, bytes.fromhex('f0 00'))

    def test_error_decode(self):
        self.assertIn('無異常', decode_monitor(0x17, b'\x00\x00')['errors'])
        self.assertIn('1 項', decode_monitor(0x17, b'\x02\x00')['errors'])

    def test_length_validation(self):
        for cmd,payload in ((0x10,b'\x10'),(0x13,b''),(0x17,b'\x01')):
            with self.assertRaises(ProtocolError):
                decode_monitor(cmd,payload)

    def test_fast_poll_does_not_query_every_status_at_100ms(self):
        timestamps = {}
        first = scheduled_monitor_commands(auto=True, now=20.0, last=timestamps)
        second = scheduled_monitor_commands(auto=True, now=20.1, last=timestamps)
        half_second = scheduled_monitor_commands(auto=True, now=20.51, last=timestamps)
        one_second = scheduled_monitor_commands(auto=True, now=21.1, last=timestamps)
        self.assertEqual(first, [0x10, 0x11, 0x12, 0x13, 0x17, 0x14])
        self.assertEqual(second, [0x10, 0x11])
        self.assertEqual(half_second, [0x10, 0x11, 0x12])
        self.assertEqual(one_second, [0x10, 0x11, 0x12, 0x13, 0x17, 0x14])
        between = scheduled_monitor_commands(auto=True, now=21.6, last=timestamps)
        self.assertNotIn(0x14, between)
        after_one_second = scheduled_monitor_commands(auto=True, now=22.2, last=timestamps)
        self.assertIn(0x14, after_one_second)

    def test_gauge_bounds(self):
        self.assertEqual(gauge_value(2.5, 10), 250)
        self.assertEqual(gauge_value(60, 50), 1000)
        self.assertEqual(gauge_value(-1, 100), 0)


class ErrorFlagTests(unittest.TestCase):
    def test_all_nine_firmware_flags_mapped(self):
        self.assertEqual(len(FLAGS), 9)
        self.assertEqual({(d.byte,d.mask) for d in FLAGS},
                         {(0,1<<i) for i in range(8)} | {(1,1)})

    def test_each_flag_individually(self):
        for d in FLAGS:
            with self.subTest(d=d.key):
                payload = bytes([d.mask,0]) if d.byte==0 else bytes([0,d.mask])
                got=decode_error_flags(payload)
                self.assertEqual(got['active'],(d.key,))
                self.assertIn('1 項',error_summary(got))

    def test_multiple_flags_and_reserved_bits(self):
        snapshot = decode_error_flags(bytes.fromhex('89 05'))
        self.assertEqual(snapshot['active'],('short','overload','mode','input'))
        self.assertEqual(snapshot['reserved_bits'],0x04)
        self.assertIn('未知旗標',error_summary(snapshot))

    def test_no_error_is_not_unknown(self):
        snapshot = decode_error_flags(b'\x00\x00')
        self.assertEqual(snapshot['active'],())
        self.assertEqual(snapshot['reserved_bits'],0)

if __name__ == '__main__': unittest.main()
