import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol import (SENSOR_MODE_LABELS, ProtocolError, build_sensor_write, require_stopped_motor,
                      parse_sensor_status, parse_motor_seconds, format_motor_seconds,
                      GROUPS, FIELDS)
from monitoring import decode_monitor
from config_io import (CONFIG_SCHEMA, LEGACY_SCHEMA, build_profile, parse_profile,
                       save_profile, load_profile)
from transport import DeviceClient
from protocol import encode_frame

SAMPLE = {
    'voltage_high': 30.0, 'voltage_low': 18.0,
    'brake_on': 52.0, 'brake_off': 51.0,
    'current_limit': 2.0, 'current_overload': 3.5, 'current_time': 500,
    'ext_acc': 400, 'ext_dec': 600, 'ret_acc': 400, 'ret_dec': 600,
    'pos_accuracy': 1.0, 'pos_max': 90.0, 'pos_min': 10.0,
}

class UserFeatureTests(unittest.TestCase):
    def test_sensor_write_frame(self):
        self.assertEqual(build_sensor_write(1), (0x04,b'\x01'))
        self.assertEqual(encode_frame(*build_sensor_write(2)), bytes.fromhex('B0 05 04 02 BB'))
        for bad in (0,3,-1,None,True):
            with self.assertRaises(ProtocolError):
                build_sensor_write(bad)

    def test_no_sensor_switch_while_moving(self):
        require_stopped_motor(b'\x01')
        for payload in (b'\x02', b'\x03', b'\x04', b'\x05', b'', b'\x01\x00'):
            with self.assertRaises(ProtocolError):
                require_stopped_motor(payload)

    def test_sensor_read_status(self):
        self.assertEqual(parse_sensor_status(b'\x00\x01'), 1)
        self.assertEqual(parse_sensor_status(b'\x01\x02'), 2)
        for bad in (b'\x01', b'\x00\x00', b'\x00\x03'):
            with self.assertRaises(ProtocolError): parse_sensor_status(bad)
        self.assertEqual(decode_monitor(0x13,b'\x00\x02')['sensor_mode'],2)

    def test_runtime_data(self):
        secs = 86400+3600+120+3
        self.assertEqual(parse_motor_seconds(secs.to_bytes(4,'little')), secs)
        self.assertEqual(format_motor_seconds(secs), '1 天 01 時 02 分 03 秒')
        self.assertEqual(decode_monitor(0x14, secs.to_bytes(4,'little'))['motor_seconds'], secs)
        with self.assertRaises(ProtocolError): parse_motor_seconds(b'\x01\x00')

    def test_config_roundtrip_and_legacy(self):
        doc=build_profile(SAMPLE,1)
        self.assertEqual(doc['schema'],CONFIG_SCHEMA)
        self.assertEqual(doc['sensor_mode'],1)
        old={'schema':LEGACY_SCHEMA,'parameters':SAMPLE}
        import json
        self.assertIsNone(parse_profile(json.dumps(old))['sensor_mode'])
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'test.config'
            save_profile(path,SAMPLE,2)
            loaded=load_profile(path)
            self.assertEqual(loaded['sensor_mode'],2)
            self.assertEqual(loaded['parameters'],SAMPLE)

    def test_config_rejects_invalid_and_never_executes_data(self):
        import json
        bad = dict(SAMPLE)
        bad['current_limit'] = -3
        with self.assertRaises(ValueError): build_profile(bad,1)
        bad = dict(SAMPLE)
        bad['current_limit'] = float('nan')
        with self.assertRaises(ValueError): build_profile(bad,1)
        with self.assertRaises(ValueError): parse_profile(json.dumps({'schema':'malicious','parameters': SAMPLE}))
        with self.assertRaises(ValueError): parse_profile(json.dumps({'schema':CONFIG_SCHEMA,'device':'Other','parameters':SAMPLE}))
        with self.assertRaises(ValueError): parse_profile(json.dumps({'schema':CONFIG_SCHEMA,'parameters':SAMPLE,'sensor_mode':3}))

    def test_zero_is_valid_after_reported_firmware_change(self):
        from protocol import build_write
        values={k:SAMPLE[k] for k in GROUPS['電流'][3]}
        values['current_limit']=0.0
        cmd,payload=build_write('電流',values)
        self.assertEqual(cmd,0x06)
        self.assertEqual(payload[:2],b'\x00\x00')
        values['current_limit']=8.0
        self.assertEqual(build_write('電流',values)[0],0x06)

if __name__ == '__main__': unittest.main()
