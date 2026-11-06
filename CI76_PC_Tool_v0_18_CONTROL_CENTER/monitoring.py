"""Read-only CI76 live telemetry (2026-11-04 firmware, Protocol 251110).
No VBUS or motor-terminal-voltage telemetry exists in this protocol.
"""
from __future__ import annotations
from protocol import ProtocolError, parse_motor_seconds, format_motor_seconds
from diagnostics import decode_error_flags, error_summary

STATUS_NAMES = {
    1: '停止', 2: '伸出中', 3: '縮回中', 4: '到達目標',
    5: '學習中', 6: '軟體下極限', 7: '軟體上極限',
}


def u16_payload(data: bytes, *, name: str) -> int:
    if len(data) != 2:
        raise ProtocolError(f'{name} 回覆長度不正確：{len(data)}（應為 2）')
    return int.from_bytes(data, 'little')


def decode_monitor(cmd: int, payload: bytes) -> dict[str, object]:
    if cmd == 0x10:
        # firmware PCTL.dp_cur = abs(m1.dp_curAvg) / 10; protocol scale = 100
        return {'current': u16_payload(payload, name='馬達電流') / 100.0}
    if cmd == 0x11:
        return {'position': u16_payload(payload, name='推桿位置') / 10.0}
    if cmd == 0x12:
        if len(payload) != 1:
            raise ProtocolError('推桿狀態必須為 1 Byte')
        return {'motor': STATUS_NAMES.get(payload[0], f'未知 (0x{payload[0]:02X})')}
    if cmd == 0x13:
        if len(payload) != 2:
            raise ProtocolError('系統狀態必須為 2 Bytes')
        return {'uart': '啟用' if payload[0] else '關閉',
                'sensor': {1: '雙 Hall', 2: 'POT'}.get(payload[1], f'未知 (0x{payload[1]:02X})'),
                'sensor_mode': payload[1] if payload[1] in (1,2) else None}
    if cmd == 0x14:
        seconds = parse_motor_seconds(payload)
        return {'motor_time': format_motor_seconds(seconds), 'motor_seconds': seconds}
    if cmd == 0x17:
        flags = decode_error_flags(payload)
        return {'errors': error_summary(flags), 'error_flags': flags}
    raise ValueError(f'不支援監控命令 0x{cmd:02X}')


def gauge_value(value: float, maximum: float) -> int:
    if maximum <= 0:
        return 0
    return max(0, min(1000, round(value * 1000.0 / maximum)))


def scheduled_monitor_commands(*, auto: bool, now: float, last: dict[int, float],
                               fast_demo: bool = False,
                               current_only: bool = False) -> list[int]:
    """Schedule read-only commands without creating a backlog.

    Normal Page 1 retains its original polling pattern. In Demo mode, the
    motor-current 0x10 has priority every poll; at most one background read is
    added every 0.22 s. This limits jitter from slow status/fault responses.
    Poll period is a TARGET; real UART/USB/MCU latency can still exceed it.
    """
    if not auto:
        return [0x10, 0x11, 0x12, 0x13, 0x17, 0x14]

    # Opt-in only for the tuning page's idle automatic polling. Manual reads
    # and Page 1 keep their full schedules. The worker enforces safety gates.
    if fast_demo and current_only:
        return [0x10]

    if fast_demo:
        result = [0x10]
        # Never let 5 extra status packets make the current measurement wait
        # for a 0.5-second batch. Limit background bandwidth in the Demo.
        if now - last.get(0xFE, float('-inf')) < 0.22:
            return result
        # Stable order for first poll, then oldest due command first (fair).
        periods = ((0x17, 1.0), (0x12, 0.5), (0x11, 0.4),
                   (0x13, 1.5), (0x14, 1.5))
        due = [(last.get(cmd, float('-inf')), index, cmd)
               for index, (cmd, period) in enumerate(periods)
               if now - last.get(cmd, float('-inf')) >= period]
        if due:
            _, _, chosen = min(due)
            result.append(chosen)
            last[chosen] = now
            last[0xFE] = now
        return result

    result = [0x10, 0x11]
    for cmd, every_seconds in ((0x12, 0.5), (0x13, 1.0),
                               (0x17, 1.0), (0x14, 1.0)):
        if now - last.get(cmd, float('-inf')) >= every_seconds:
            result.append(cmd)
            last[cmd] = now
    return result
