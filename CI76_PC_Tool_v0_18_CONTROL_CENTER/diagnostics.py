"""CI76 active Error Flags, mapped exactly to FW Core/Inc/ics.h (2026-11-04).
Read-only; CMD 0x17 / ACK 0x97 has two bytes: sys.errBit0, sys.errBit1.
"""
from __future__ import annotations
from dataclasses import dataclass
from protocol import ProtocolError

@dataclass(frozen=True)
class ErrorDefinition:
    key: str
    byte: int
    mask: int
    label: str
    category: str  # visual category only: not a statement about physical severity

FLAGS = (
    ErrorDefinition('short',     0, 0x01, '短路保護', 'power'),
    ErrorDefinition('low_volt',  0, 0x02, '電源低壓', 'power'),
    ErrorDefinition('high_volt', 0, 0x04, '電源過壓', 'power'),
    ErrorDefinition('overload',  0, 0x08, '過載電流', 'power'),
    ErrorDefinition('brake',     0, 0x10, '回生超載', 'power'),
    ErrorDefinition('feedback',  0, 0x20, '位置回授', 'control'),
    ErrorDefinition('learning',  0, 0x40, '學習異常', 'control'),
    ErrorDefinition('mode',      0, 0x80, '控制模式', 'control'),
    ErrorDefinition('input',     1, 0x01, '輸入模式', 'control'),
)


def decode_error_flags(payload: bytes) -> dict:
    if len(payload) != 2:
        raise ProtocolError(f'0x17 錯誤旗標回覆需 2 Bytes，收到 {len(payload)}')
    b0, b1 = payload
    active = [item.key for item in FLAGS if payload[item.byte] & item.mask]
    # Byte1 bits1..7 are not defined in 2026-11-04 firmware; never silently call OK.
    reserved_bits = b1 & 0xFE
    return {'byte0': b0, 'byte1': b1, 'active': tuple(active),
            'reserved_bits': reserved_bits}


def error_summary(data: dict) -> str:
    n = len(data['active'])
    raw = f"0x{data['byte0']:02X} / 0x{data['byte1']:02X}"
    if data['reserved_bits']:
        return f'{raw}（未知旗標，請檢查）'
    if n:
        return f'{raw}（{n} 項異常）'
    return f'{raw}（無異常旗標）'
