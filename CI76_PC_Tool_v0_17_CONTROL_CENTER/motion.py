"""Guarded CI76 command definitions. Firmware 0x0B02 or newer must implement motion watchdog."""
from __future__ import annotations
from dataclasses import dataclass
from protocol import ProtocolError

SAFE_MOTION_FW_MIN = 0x0B02
MOTOR_DIRECTIONS = {'extend': 0x02, 'retract': 0x03, 'stop': 0x01}
MOTOR_HEARTBEAT_SECONDS = 0.20


def firmware_motion_supported(version: str, device: str) -> bool:
    try:
        return device == '0x0B01' and int(version, 16) >= SAFE_MOTION_FW_MIN
    except (TypeError, ValueError):
        return False


def motor_position_command(direction: str) -> tuple[int, bytes]:
    if direction not in MOTOR_DIRECTIONS:
        raise ProtocolError('方向僅支援伸出、縮回與停止')
    # target percentage unused by button-mode in current FW
    return 0x09, bytes((0, 0, MOTOR_DIRECTIONS[direction]))


def motor_speed_command(percent: int) -> tuple[int, bytes]:
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ProtocolError('速度必須為 0～100%')
    return 0x07, (percent * 10).to_bytes(2, 'little')


def validate_start(status: bytes, system: bytes, errors: bytes) -> None:
    if len(status) != 1 or status[0] not in (1, 4, 6, 7):
        raise ProtocolError('推桿未停止、正在學習或狀態未知；禁止啟動')
    if len(system) != 2 or len(errors) != 2:
        raise ProtocolError('系統狀態或故障查詢格式異常')
    if errors != b'\x00\x00':
        raise ProtocolError(f'存在故障旗標 {errors.hex(" ").upper()}，禁止啟動')
