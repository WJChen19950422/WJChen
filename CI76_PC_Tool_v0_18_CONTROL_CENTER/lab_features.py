"""CI76 FW 0x0B01 lab-only learning and current-limit demo rules.
No direct setting of motor force exists: 0x06 specifies a current ceiling.
"""
from __future__ import annotations
from protocol import ProtocolError, parse_group, build_write
from current_limits import CURRENT_SLIDER_MIN_A, CURRENT_SLIDER_MAX_A, CURRENT_HIGH_CONFIRM_A

def error_clear_payload():
    """FW 0x0B01 0x0F / 0x02: request clear of active fault bits, not historical counts."""
    return (0x0F, b"\x02")

def validate_demo_speed(percent):
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ProtocolError("速度設定需為 0～100%")
    return percent * 10


DEMO_MIN_A = CURRENT_SLIDER_MIN_A
DEMO_MAX_A = CURRENT_SLIDER_MAX_A
DEMO_HIGH_CONFIRM_A = CURRENT_HIGH_CONFIRM_A

def learning_payload(start: bool) -> tuple[int, bytes]:
    return (0x02, b"\x01" if start else b"\x00")

def learning_preflight(status: bytes, system: bytes, faults: bytes):
    if status not in (b"\x01", b"\x04", b"\x06", b"\x07"):
        raise ProtocolError('目前未確認停止，不能開始學習')
    if len(system) != 2 or system[0] != 0:
        raise ProtocolError('先關閉 UART MODE 才能進行行程學習')
    if len(faults) != 2 or (faults[0] & ~0x20) or faults[1]:
        raise ProtocolError('除待學習的 0x20 外仍有其他故障，不允許開始學習')
    return True

def demo_current_write(current_payload: bytes, limit_amps: float):
    """Keep overload and duration exactly as the device reports.
    UART CMD 0x06 writes all THREE settings, not just current limit.
    """
    if not DEMO_MIN_A <= limit_amps <= DEMO_MAX_A:
        raise ProtocolError(f'展示限流必須在 {DEMO_MIN_A:.2f}～{DEMO_MAX_A:.2f} A 之間')
    old = parse_group('電流', current_payload)
    if limit_amps > old['current_overload']:
        raise ProtocolError(f'限流 {limit_amps:.2f} A 高於目前過載門檻 {old["current_overload"]:.2f} A；請先核對電流參數')
    requested = dict(old, current_limit=round(limit_amps, 2))
    command, payload = build_write('電流', requested)
    return command, payload, old, requested

def learning_observation(seen_learning: bool, status: bytes|None, flags: bytes|None):
    if flags and len(flags)==2 and (flags[0] & 0x40):
        return 'failed'
    if status == b"\x05":
        return 'learning'
    if seen_learning and status in (b"\x01", b"\x04", b"\x06", b"\x07") and flags == b"\x00\x00":
        return 'completed_candidate'
    return 'pending'
