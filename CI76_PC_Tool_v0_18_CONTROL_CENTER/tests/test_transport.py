import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import encode_frame, unpack_u16, ProtocolError
from transport import DeviceClient


class FakeSerial:
    def __init__(self, response_cmd, response_payload):
        self.rx = bytearray()
        self.tx = []
        self.response_cmd = response_cmd
        self.response_payload = response_payload

    def reset_input_buffer(self):
        self.rx.clear()

    def write(self, data):
        self.tx.append(data)
        # Deliberate junk prefix tests RX resynchronization.
        self.rx.extend(b'garbage' + encode_frame(self.response_cmd, self.response_payload))
        return len(data)

    def flush(self):
        pass

    def read(self, n):
        if not self.rx:
            return b''
        value = bytes(self.rx[:1])
        del self.rx[:1]
        return value

    def close(self):
        pass


class TransportTests(unittest.TestCase):
    def test_read_version(self):
        fake = FakeSerial(0xF0, bytes.fromhex('01 01 0B'))
        dev = DeviceClient(fake)
        self.assertEqual(dev.read_cmd(0x70), bytes.fromhex('01 01 0B'))
        self.assertEqual(fake.tx[0], bytes.fromhex('B0 05 70 00 25'))

    def test_read_current_parameters(self):
        raw = bytes.fromhex('5E 01 0E 01 F4 01')
        fake = FakeSerial(0x99, raw)
        self.assertEqual(unpack_u16(DeviceClient(fake).read_cmd(0x19)), [350, 270, 500])

    def test_write_ack_echo(self):
        payload = bytes.fromhex('5E 01 0E 01 F4 01')
        fake = FakeSerial(0x86, payload)
        self.assertEqual(DeviceClient(fake).write_cmd(0x06, payload), payload)

    def test_write_ack_mismatch_rejected(self):
        fake = FakeSerial(0x86, bytes.fromhex('00 00 00 00 00 00'))
        with self.assertRaises(ProtocolError):
            DeviceClient(fake).write_cmd(0x06, bytes.fromhex('5E 01 0E 01 F4 01'))

if __name__ == '__main__':
    unittest.main()
