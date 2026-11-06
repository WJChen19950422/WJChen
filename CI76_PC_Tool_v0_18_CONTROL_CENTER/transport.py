"""Thread-owned pyserial CI76 transport, with framing and RX resynchronization."""
from __future__ import annotations
import time
from protocol import READ_RESPONSE, ProtocolError, decode_frame, encode_frame, HEADER, BAUD


class DeviceClient:
    def __init__(self, serial_obj, trace=None):
        self.serial = serial_obj
        self.trace = trace or (lambda _kind, _raw: None)

    @classmethod
    def open(cls, port: str, trace=None):
        import serial
        obj = serial.Serial(port=port, baudrate=BAUD, bytesize=8,
                            parity='N', stopbits=1, timeout=0.01,
                            write_timeout=1.0, rtscts=False, dsrdtr=False)
        return cls(obj, trace)

    def close(self):
        self.serial.close()

    def _receive(self, timeout=1.2):
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = self.serial.read(1)
            if chunk:
                buf.extend(chunk)
            while buf:
                if buf[0] != HEADER:
                    buf.pop(0)
                    continue
                if len(buf) < 2:
                    break
                n = buf[1]
                if n < 4 or n > 255:
                    buf.pop(0)
                    continue
                if len(buf) < n:
                    break
                raw = bytes(buf[:n])
                try:
                    result = decode_frame(raw)
                    del buf[:n]
                    self.trace('RX', raw)
                    return result
                except ProtocolError:
                    buf.pop(0)
        raise TimeoutError("CI76 response timeout (no valid UART frame)")

    def request(self, cmd, payload=b'', *, expected=None, size=None, timeout=1.2):
        if cmd in READ_RESPONSE:
            expected, size = READ_RESPONSE[cmd]
        if expected is None:
            expected = cmd | 0x80
        raw = encode_frame(cmd, payload)
        self.serial.reset_input_buffer()
        self.trace('TX', raw)
        self.serial.write(raw)
        self.serial.flush()
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            msg = self._receive(max(0.05, until - time.monotonic()))
            if msg.cmd != expected:
                continue
            if size is not None and len(msg.payload) != size:
                raise ProtocolError(f"Expected {size} payload bytes for 0x{cmd:02X}; got {len(msg.payload)}")
            return msg.payload
        raise TimeoutError(f"CI76 CMD 0x{cmd:02X} no matching ACK")

    def read_cmd(self, cmd, *, timeout=1.2):
        # Upgrade protocol specifies one 0x00 payload byte for 0x70 and 0x71.
        return self.request(cmd, b'\x00' if cmd in (0x70, 0x71) else b'', timeout=timeout)

    def write_cmd(self, cmd, payload, *, timeout=1.2):
        # Firmware generally echoes the written values in ACK: verify them.
        answer = self.request(cmd, payload, size=len(payload), timeout=timeout)
        if answer != payload:
            raise ProtocolError(f"ACK did not echo written payload for CMD 0x{cmd:02X}")
        return answer
