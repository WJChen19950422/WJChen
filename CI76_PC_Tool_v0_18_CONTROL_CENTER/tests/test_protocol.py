import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import (
    checksum, encode_frame, decode_frame, pack_u16, unpack_u16,
    parse_group, build_write, read_info, ProtocolError, GROUPS,
)

class PacketTests(unittest.TestCase):
    def test_read_version_request_matches_upgrade_spec(self):
        self.assertEqual(encode_frame(0x70, b'\x00'), bytes.fromhex('B0 05 70 00 25'))

    def test_checksum_and_decode(self):
        packet = encode_frame(0x06, bytes.fromhex('5E 01 0E 01 F4 01'))
        self.assertEqual(decode_frame(packet).payload, bytes.fromhex('5E 01 0E 01 F4 01'))
        self.assertEqual(packet[-1], checksum(packet[:-1]))
        with self.assertRaises(ProtocolError):
            decode_frame(packet[:-1] + bytes([packet[-1] ^ 0x01]))

    def test_u16(self):
        raw = pack_u16([350, 270, 500])
        self.assertEqual(raw, bytes.fromhex('5E 01 0E 01 F4 01'))
        self.assertEqual(unpack_u16(raw), [350,270,500])

    def test_current_write_vs_read_mapping(self):
        values = {'current_limit':3.5, 'current_overload':2.7, 'current_time':500}
        cmd, payload = build_write('電流', values)
        self.assertEqual(cmd, 0x06)
        self.assertEqual(unpack_u16(payload), [350,270,500])
        self.assertEqual(parse_group('電流', payload), values)

    def test_voltage_response_includes_brake(self):
        payload = pack_u16([310,190,520,510])
        self.assertEqual(parse_group('電壓', payload), {'voltage_high':31.0,'voltage_low':19.0})
        self.assertEqual(parse_group('回生', payload), {'brake_on':52.0,'brake_off':51.0})

    def test_no_overwrite_firmware_factory_brake_values(self):
        with self.assertRaises(ProtocolError):
            build_write('回生', {'brake_on':52,'brake_off':51})

    def test_position_indices_skip_target(self):
        p = pack_u16([500,10,900,100,12,34,56])
        self.assertEqual(parse_group('位置',p), {'pos_accuracy':1.0,'pos_max':90.0,'pos_min':10.0})

    def test_speed_indices_skip_speed_command(self):
        p = pack_u16([1000,1200,800,300,600])
        self.assertEqual(parse_group('速度',p), {'ext_acc':1200,'ext_dec':800,'ret_acc':300,'ret_dec':600})

    def test_safety_validation(self):
        with self.assertRaises(ProtocolError):
            build_write('電壓', {'voltage_high':19.0,'voltage_low':31.0})
        with self.assertRaises(ProtocolError):
            build_write('位置', {'pos_accuracy':1.0,'pos_min':90,'pos_max':10})

    def test_version_response(self):
        self.assertEqual(read_info(b'\x01\x01\x0B'), '0x0B01')

if __name__ == '__main__':
    unittest.main()
