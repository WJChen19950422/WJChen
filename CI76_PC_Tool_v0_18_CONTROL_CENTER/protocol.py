"""CI76 UART frame codec and parameter mapping.
Source baseline: CI76 Protocol_251110.xlsx and LAC2_TEST uart.c (2026-11-04).
No firmware flash or motor actuation commands are exposed from this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

HEADER = 0xB0
BAUD = 115200


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    cmd: int
    payload: bytes


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def encode_frame(cmd: int, payload: bytes = b"") -> bytes:
    if not 0 <= cmd <= 0xFF:
        raise ProtocolError("CMD must fit in one byte")
    if len(payload) > 251:
        raise ProtocolError("UART frame length cannot exceed 255")
    prefix = bytes((HEADER, len(payload) + 4, cmd)) + payload
    return prefix + bytes((checksum(prefix),))


def decode_frame(data: bytes) -> Frame:
    if len(data) < 4 or data[0] != HEADER or data[1] != len(data):
        raise ProtocolError("Invalid CI76 frame header / length")
    if checksum(data[:-1]) != data[-1]:
        raise ProtocolError("Invalid checksum")
    return Frame(data[2], data[3:-1])


def pack_u16(values: list[int] | tuple[int, ...]) -> bytes:
    if any(not 0 <= int(v) <= 65535 or int(v) != v for v in values):
        raise ProtocolError("Value outside unsigned 16-bit range")
    return b"".join(int(v).to_bytes(2, "little") for v in values)


def unpack_u16(data: bytes) -> list[int]:
    if len(data) % 2:
        raise ProtocolError("Expected pairs of little-endian bytes")
    return [int.from_bytes(data[i:i+2], "little") for i in range(0, len(data), 2)]


def to_raw(value: float | str | Decimal, scale: int) -> int:
    """Use Decimal to avoid floating point off-by-one errors."""
    raw = Decimal(str(value)) * Decimal(scale)
    if raw != raw.to_integral_value():
        raise ProtocolError(f"Precision is finer than 1/{scale}")
    return int(raw)


def from_raw(value: int, scale: int) -> float:
    return float(Decimal(value) / Decimal(scale))


# (field key, Chinese label, unit, base-unit-to-raw scale, min, max)
FIELDS = {
    "voltage_high": ("最高保護電壓", "V", 10, 0, 50),
    "voltage_low": ("最低保護電壓", "V", 10, 0, 50),
    "brake_on": ("回生啟動電壓", "V", 10, 10, 50),
    "brake_off": ("回生關閉電壓", "V", 10, 10, 50),
    "current_limit": ("限流值", "A", 100, 0.00, 10),
    "current_overload": ("過載電流門檻", "A", 100, 0.03, 10),
    "current_time": ("過載持續時間", "ms", 1, 0, 5000),
    "ext_acc": ("伸出加速時間", "ms", 1, 0, 5000),
    "ext_dec": ("伸出減速時間", "ms", 1, 0, 5000),
    "ret_acc": ("縮回加速時間", "ms", 1, 0, 5000),
    "ret_dec": ("縮回減速時間", "ms", 1, 0, 5000),
    "pos_accuracy": ("定位精度容差", "%", 10, 0, 20),
    "pos_max": ("軟體上極限", "%", 10, 0, 100),
    "pos_min": ("軟體下極限", "%", 10, 0, 100),
}

# group -> (read CMD, write CMD, indices of read payload, keys in write order)
GROUPS = {
    "電壓": (0x18, 0x05, (0, 1), ("voltage_high", "voltage_low")),
    "回生": (0x18, 0x0C, (2, 3), ("brake_on", "brake_off")),
    "電流": (0x19, 0x06, (0, 1, 2), ("current_limit", "current_overload", "current_time")),
    "速度": (0x20, 0x08, (1, 2, 3, 4), ("ext_acc", "ext_dec", "ret_acc", "ret_dec")),
    "位置": (0x21, 0x0A, (1, 2, 3), ("pos_accuracy", "pos_max", "pos_min")),
}

READ_RESPONSE = {
    0x10: (0x90, 2), 0x11: (0x91, 2), 0x12: (0x92, 1),
    0x13: (0x93, 2), 0x14: (0x94, 4), 0x15: (0x95, 4),
    0x16: (0x96, 8), 0x17: (0x97, 2),
    0x18: (0x98, 8), 0x19: (0x99, 6), 0x20: (0xA0, 10),
    0x21: (0xA1, 14), 0x70: (0xF0, 3), 0x71: (0xF1, 3),
}


def parse_group(group: str, payload: bytes) -> dict[str, float]:
    read_cmd, _, indices, keys = GROUPS[group]
    expected = READ_RESPONSE[read_cmd][1]
    if len(payload) != expected:
        raise ProtocolError(f"{group}: expected {expected} data bytes, received {len(payload)}")
    values = unpack_u16(payload)
    return {k: from_raw(values[i], FIELDS[k][2]) for k, i in zip(keys, indices)}


def build_write(group: str, values: dict[str, float]) -> tuple[int, bytes]:
    _, write_cmd, _, keys = GROUPS[group]
    for key in keys:
        if key not in values:
            raise ProtocolError(f"Missing parameter: {key}")
        lo, hi = FIELDS[key][3:]
        if not lo <= values[key] <= hi:
            raise ProtocolError(f"{FIELDS[key][0]} must be between {lo} and {hi} {FIELDS[key][1]}")
    if group == "電壓" and values["voltage_high"] < values["voltage_low"]:
        raise ProtocolError("最低電壓不可高於最高電壓")
    if group == "回生" and values["brake_on"] < values["brake_off"]:
        raise ProtocolError("回生關閉電壓不可高於啟動電壓")
    if group == "位置":
        # MCU ctl.c does `pos.setmax = PCTL.soft_max_pct / 10` (integer
        # division), likewise setmin. Fractions of a percent are truncated.
        # Reject rather than silently accepting 60.5% then storing 60%.
        for field in ('pos_max', 'pos_min'):
            if Decimal(str(values[field])) != Decimal(str(values[field])).to_integral_value():
                raise ProtocolError(f'{FIELDS[field][0]} 僅支援整數百分比 (0～100%)')
        if values["pos_min"] > values["pos_max"]:
            raise ProtocolError("位置下極限不可高於上極限")
    payload = pack_u16(tuple(to_raw(values[k], FIELDS[k][2]) for k in keys))
    return write_cmd, payload


def read_info(payload: bytes) -> str:
    if len(payload) != 3 or payload[0] != 1:
        raise ProtocolError("Firmware/device response payload format unexpected")
    return f"0x{int.from_bytes(payload[1:], 'little'):04X}"


SENSOR_MODE_LABELS = {1: '雙 Hall', 2: 'POT'}

def validate_sensor_mode(mode: int) -> int:
    if type(mode) is not int or mode not in SENSOR_MODE_LABELS:
        raise ProtocolError('感測器只能選擇雙 Hall (0x01) 或 POT (0x02)')
    return mode

def build_sensor_write(mode: int) -> tuple[int, bytes]:
    return 0x04, bytes([validate_sensor_mode(mode)])

def parse_sensor_status(payload: bytes) -> int:
    if len(payload) != 2:
        raise ProtocolError('系統狀態 (0x13) 回覆必須為 2 Bytes')
    mode = payload[1]
    return validate_sensor_mode(mode)

def parse_motor_seconds(payload: bytes) -> int:
    if len(payload) != 4:
        raise ProtocolError('累積運轉時間 (0x14) 回覆必須為 4 Bytes')
    return int.from_bytes(payload, byteorder='little', signed=False)

def format_motor_seconds(total_seconds: int) -> str:
    if not isinstance(total_seconds, int) or total_seconds < 0:
        raise ValueError('累積運轉時間不能為負數')
    days, rest = divmod(total_seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{days} 天 {hours:02} 時 {minutes:02} 分 {seconds:02} 秒'


def require_stopped_motor(payload: bytes) -> None:
    """Disallow sensor switching except with explicit 0x12 stop code 0x01."""
    if len(payload) != 1 or payload[0] != 1:
        raise ProtocolError('感測器切換遭拒：控制器未回報完全停止 (0x01)')


def parse_error_counters(payload: bytes) -> dict[str, int]:
    """0x16: four unsigned 16-bit counters, little-endian."""
    if len(payload) != 8:
        raise ProtocolError('故障次數回覆應為 8 Bytes')
    values = unpack_u16(payload)
    return dict(zip(('voltage', 'current', 'position', 'total'), values))


def build_motor_time_reset() -> tuple[int, bytes]:
    """0x0F 0x03: clear MotorCNT in RAM; separate power-cycle validation required."""
    return (0x0F, b'\x03')
