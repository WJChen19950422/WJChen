import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui_ranges import field_editor_spec
from protocol import FIELDS, GROUPS, build_write, parse_group, ProtocolError

class FieldDisplayTests(unittest.TestCase):
    def test_soft_limits_have_full_range(self):
        for key in ('pos_min','pos_max'):
            self.assertEqual(field_editor_spec(key), (0.0,100.0,0,1.0))

    def test_accuracy_does_not_lose_decimal_precision(self):
        self.assertEqual(field_editor_spec('pos_accuracy'), (0.0,20.0,1,0.1))

    def test_regenerative_thresholds_preserve_readable_factory_defaults(self):
        self.assertEqual(field_editor_spec('brake_on')[1], 60.0)
        self.assertEqual(field_editor_spec('brake_off')[1], 60.0)

    def test_other_field_limits_not_incorrectly_capped(self):
        for key in FIELDS:
            self.assertGreaterEqual(field_editor_spec(key)[1], FIELDS[key][4])
        self.assertEqual(field_editor_spec('current_limit')[1], 10.0)
        self.assertEqual(field_editor_spec('ext_acc')[1], 5000)

    def test_write_full_soft_limit_0_to_100(self):
        cmd, payload = build_write('位置', {'pos_accuracy':1.,'pos_max':100.,'pos_min':0.})
        self.assertEqual(cmd, 0x0A)
        self.assertEqual(payload, bytes.fromhex('0a 00 e8 03 00 00'))

    def test_reject_silent_fractional_soft_limit_truncation(self):
        with self.assertRaisesRegex(ProtocolError, '整數百分比'):
            build_write('位置', {'pos_accuracy':1.,'pos_max':60.5,'pos_min':0.})

    def test_readback_full_soft_limit(self):
        payload=bytes.fromhex('00 00 0a 00 e8 03 00 00 00 00 00 00 00 00')
        self.assertEqual(parse_group('位置',payload)['pos_max'],100.0)

if __name__=='__main__': unittest.main()
