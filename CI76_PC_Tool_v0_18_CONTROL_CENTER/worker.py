"""CI76 serial worker: a single thread owns the port; polling never stacks.

Fast samples: 0x10 current and 0x11 position.
Slow health: 0x12 every ~0.5s, 0x13/0x17 every ~1s, 0x14 ~1s.
"""
from __future__ import annotations
import time
from queue import Queue, Empty
from PySide6.QtCore import QThread, Signal
from protocol import (GROUPS, parse_group, build_write, read_info,
                      build_sensor_write, parse_sensor_status, require_stopped_motor,
                      parse_motor_seconds, parse_error_counters, build_motor_time_reset,
                      ProtocolError)
from monitoring import decode_monitor, scheduled_monitor_commands
from transport import DeviceClient
from motion import (firmware_motion_supported, motor_position_command,
                    motor_speed_command, validate_start, MOTOR_HEARTBEAT_SECONDS)
from lab_features import (learning_payload, learning_preflight, demo_current_write,
                          learning_observation, error_clear_payload, validate_demo_speed)


class SerialWorker(QThread):
    success = Signal(str, object)
    error = Signal(str, str)
    trace = Signal(str)

    def __init__(self):
        super().__init__()
        self.jobs = Queue()
        self.urgent = Queue()
        self.motor_direction = None
        self.motor_last_tick = 0.0
        self.motor_supported = False
        # Legacy FW 0x0B01: explicit, acknowledged UART mode and short PC-host-timed jog.
        # NO firmware watchdog on this version. A real independent hardware cutout is mandatory.
        self.bench_uart_enabled = False
        self.bench_limited_motion = False
        self.bench_deadline = 0.0
        self.abort_motion_request = False
        self.previous_speed_raw = None
        self.learning_active = False
        self.learning_seen = False
        self.learning_abort_requested = False
        self.learning_started_at = 0.0
        self.last_learning_stage = None
        self.last_learn_status = None
        self.last_learn_flags = None
        self.demo_original_current = None  # raw 0x19 snapshot, restore on explicit request
        self.demo_original_speed = None  # raw 0x20 first 2 bytes; restore on explicit request
        self.client = None
        self.running = True
        self._mute_trace = False
        self._slow_time = {0x12: 0.0, 0x13: 0.0, 0x17: 0.0, 0x14: 0.0}

    def submit(self, action, data=None):
        if action in ('motor_stop', 'learning_abort'):
            if action == 'learning_abort':
                self.learning_abort_requested = True
            # Cancels even a motor-start command still waiting in the normal queue.
            self.abort_motion_request = True
            self.urgent.put((action, data))
        else:
            if action == 'learning_start':
                self.learning_abort_requested = False
            if action in ('motor_start', 'bench_start'):
                self.abort_motion_request = False
            self.jobs.put((action, data))

    def halt(self):
        self.running = False
        self.jobs.put(('disconnect', None))

    def _stop_motor(self):
        """Acknowledged stop; firmware watchdog remains the last line of defense."""
        if self.learning_active:
            # Explicitly request learning abort before ordinary motion STOP.
            self._abort_learning()
        if not self.client:
            self.motor_direction = None
            return {'ack': False, 'status': None}
        # Disarm host heartbeats FIRST. If UART STOP fails, the MCU watchdog
        # can still expire instead of the host keeping the motor latched on.
        self.motor_direction = None
        self.motor_last_tick = 0.0
        self.bench_limited_motion = False
        self.bench_deadline = 0.0
        cmd, payload = motor_position_command('stop')
        self.client.write_cmd(cmd, payload, timeout=0.30)
        status = None
        # Motor inertia/ramp: an ACK is not proof of a physical standstill.
        for _ in range(3):
            try:
                status = self.client.read_cmd(0x12, timeout=0.16)
                if status[0] in (1, 4, 6, 7):
                    break
            except Exception:
                pass
            time.sleep(0.07)
        if status and status[0] in (1, 4, 6, 7):
            try:
                # Restore device's speed setting after temporary PC speed test.
                if self.previous_speed_raw is not None:
                    self.client.write_cmd(0x07, int(self.previous_speed_raw).to_bytes(2,'little'), timeout=0.22)
                    self.previous_speed_raw = None
                # In legacy lab mode, UART MODE is explicitly controlled by its own button;
                # after STOP, leave it enabled for a subsequent bounded jog.
                if not self.bench_uart_enabled:
                    self.client.write_cmd(0x03, b'\x00', timeout=0.20)
            except Exception:
                # The safety STOP is already ACKed. Speed restore and mode
                # disable are best effort; inspect 0x20 before new testing.
                pass
        return {'ack': True, 'status': status[0] if status else None}

    def _heartbeat(self):
        if not self.motor_direction or not self.client or self.bench_limited_motion:
            return
        if time.monotonic() - self.motor_last_tick < MOTOR_HEARTBEAT_SECONDS:
            return
        try:
            cmd, payload = motor_position_command(self.motor_direction)
            self.client.write_cmd(cmd, payload, timeout=0.22)
            self.motor_last_tick = time.monotonic()
        except Exception as exc:
            self.motor_direction = None
            # The version-gated firmware watchdog halts if these packets cease.
            self.error.emit('motor_lost', f'維持運轉指令失敗，MCU 應於逾時後停止：{exc}')

    def _check_bench_deadline(self):
        """Host-side bound ONLY: cannot protect against USB loss or PC process crash."""
        if self.bench_limited_motion and self.motor_direction and time.monotonic() >= self.bench_deadline:
            try:
                result = self._stop_motor()
                result['reason'] = 'host_2s_timeout'
                self.success.emit('motor_autostop', result)
            except Exception as exc:
                self.error.emit('motor_lost',
                    'PC 端 2 秒限時停止失敗！舊韌體不會因 UART 中斷自動停車，請立即使用獨立硬體斷電：' + str(exc))

    def _bench_uart_mode(self, enabled: bool):
        if self.learning_active:
            raise ProtocolError('學習中不能啟用 UART MODE')
        if not enabled and self.demo_original_current is not None:
            raise ProtocolError('請先在展示分頁還原原限流值，才能關閉 UART MODE')
        if self.motor_direction:
            raise ProtocolError('請先停止並確認推桿停止，才能切換 UART MODE')
        fw = read_info(self.client.read_cmd(0x70))
        device = read_info(self.client.read_cmd(0x71))
        if (fw, device) != ('0x0B01', '0x0B01'):
            raise ProtocolError('免更新韌體內測模式限定 0x0B01，其他版本請用相應的安全測試流程')
        if enabled:
            status = self.client.read_cmd(0x12)
            errors = self.client.read_cmd(0x17)
            if status not in (b'\x01', b'\x04', b'\x06', b'\x07'):
                raise ProtocolError(f'推桿狀態 0x{status.hex().upper()}：並非已確認停止，禁止進入 UART MODE；尚未發出 STOP 或 MODE 指令')
            if errors != b'\x00\x00':
                faults = errors.hex(' ').upper()
                if errors[0] & 0x20:
                    raise ProtocolError(
                        f'錯誤旗標 0x{faults}：存在位置回授異常（0x20）。'
                        '韌體在沒有有效行程資料時可能處於待學習的速度模式，'
                        'UART 伸縮需先具備有效行程學習與位置回授。'
                        '請先檢查 Hall／POT 接線及學習結果；尚未發出 STOP 或 MODE 指令')
                raise ProtocolError(f'錯誤旗標 0x{faults}：目前有故障，禁止進入 UART MODE；尚未發出 STOP 或 MODE 指令')
            # Clear any latched direction from an earlier app crash before enabling.
            cmd, payload = motor_position_command('stop')
            self.client.write_cmd(cmd, payload, timeout=0.3)
            self.client.write_cmd(0x03, b'\x01', timeout=0.3)
        else:
            # Disable must always send STOP first, independent of UI state.
            cmd, payload = motor_position_command('stop')
            self.client.write_cmd(cmd, payload, timeout=0.3)
            self.client.write_cmd(0x03, b'\x00', timeout=0.3)
        actual = self.client.read_cmd(0x13, timeout=0.4)
        if len(actual) != 2 or actual[0] != int(enabled):
            raise ProtocolError('UART MODE 命令已傳送，但 0x13 狀態讀回不一致；請先確定馬達停住')
        self.bench_uart_enabled = bool(enabled)
        return {'enabled': bool(enabled), 'readback': int(actual[0])}

    def _start_bench(self, direction: str, speed: int):
        if self.learning_active:
            raise ProtocolError('學習中禁止手動伸縮')
        if direction not in ('extend', 'retract'):
            raise ProtocolError('測試方向錯誤')
        if type(speed) is not int or not 1 <= speed <= 100:
            raise ProtocolError('馬達啟動速度需為 1～100%；0% 僅可設定停轉')
        if not self.bench_uart_enabled:
            raise ProtocolError('請先按「UART MODE：OFF」並成功啟用')
        if self.abort_motion_request:
            raise ProtocolError('已要求停止，取消尚未執行的馬達啟動')
        if self.motor_direction:
            result = self._stop_motor()
            if result.get('status') not in (1, 4, 6, 7):
                raise ProtocolError('方向切換時停止狀態未確認，拒絕反轉')
            time.sleep(0.15)
        fw = read_info(self.client.read_cmd(0x70))
        device = read_info(self.client.read_cmd(0x71))
        if (fw, device) != ('0x0B01', '0x0B01'):
            raise ProtocolError('設備版本不符，禁止進行 0x0B01 內部測試')
        status = self.client.read_cmd(0x12)
        system = self.client.read_cmd(0x13)
        errors = self.client.read_cmd(0x17)
        validate_start(status, system, errors)
        if system[0] != 1:
            raise ProtocolError('UART MODE 目前並未開啟')
        # Avoid starting toward an already near end. Assumes calibrated position.
        pos_payload = self.client.read_cmd(0x11)
        if len(pos_payload) != 2:
            raise ProtocolError('未取得位置數值，禁止點動')
        pos_percent = int.from_bytes(pos_payload, 'little') / 10.0
        if not 0.0 <= pos_percent <= 100.0:
            raise ProtocolError('位置回報超出 0～100% 範圍，禁止點動')
        if (direction == 'extend' and pos_percent >= 95) or (direction == 'retract' and pos_percent <= 5):
            raise ProtocolError(f'目前位置 {pos_percent:.1f}% 接近目標方向端點，禁止此方向點動')
        if self.abort_motion_request:
            raise ProtocolError('已要求停止，取消馬達啟動')
        try:
            raw_speed = self.client.read_cmd(0x20)
            if len(raw_speed) != 10:
                raise ProtocolError('速度原始參數讀取失敗，禁止馬達啟動')
            self.previous_speed_raw = int.from_bytes(raw_speed[:2], 'little')
            speed_cmd, speed_payload = motor_speed_command(speed)
            self.client.write_cmd(speed_cmd, speed_payload, timeout=0.3)
            if self.abort_motion_request:
                raise ProtocolError('已要求停止，取消馬達啟動')
            cmd, payload = motor_position_command(direction)
            self.client.write_cmd(cmd, payload, timeout=0.3)
            self.motor_direction = direction
            self.motor_last_tick = time.monotonic()
            self.bench_limited_motion = True
            self.bench_deadline = self.motor_last_tick + 2.0
            return {'direction': direction, 'speed': speed, 'host_duration_s': 2.0, 'legacy_fw': True}
        except Exception:
            try:
                self._stop_motor()
            except Exception:
                pass
            raise

    def _start_learning(self):
        """ACK is only acceptance of a request; never claim learning completed."""
        if self.motor_direction or self.learning_active or self.bench_uart_enabled:
            raise ProtocolError('先停止推桿並關閉 UART MODE')
        fw = read_info(self.client.read_cmd(0x70, timeout=0.35))
        device = read_info(self.client.read_cmd(0x71, timeout=0.35))
        if (fw, device) != ('0x0B01', '0x0B01'):
            raise ProtocolError('學習控制尚未驗證其他韌體版本')
        learning_preflight(self.client.read_cmd(0x12, timeout=0.3),
                           self.client.read_cmd(0x13, timeout=0.3),
                           self.client.read_cmd(0x17, timeout=0.3))
        if self.learning_abort_requested:
            raise ProtocolError('學習已被使用者取消')
        command, payload = learning_payload(True)
        self.client.write_cmd(command, payload, timeout=0.35)
        self.learning_active = True
        self.learning_seen = False
        self.learning_started_at = time.monotonic()
        self.last_learning_stage = 'request_sent'
        self.last_learn_status = None
        self.last_learn_flags = None
        return {'request_ack': True, 'complete': False}

    def _abort_learning(self):
        # Acknowledge stop before claiming any requested cancellation.
        command, payload = learning_payload(False)
        try:
            self.client.write_cmd(command, payload, timeout=0.35)
            # Firmware may still be executing a motor-control loop. Also attempt STOP.
            self.client.write_cmd(0x09, b'\x00\x00\x01', timeout=0.35)
        finally:
            self.learning_active = False
            self.learning_seen = False
            self.last_learning_stage = None
            # Keep cancellation latched so an already queued start stays cancelled.
        return {'abort_ack': True, 'physical_stop_verified': False}

    def _write_group(self, group, values):
        """Write/readback ordinary Page-1 parameters; retire an old Demo snapshot.

        If a user explicitly writes current parameters from Page 1 after a
        Demo session, that confirmed choice supersedes the earlier Demo
        original. Restore must never silently revert it.
        """
        cmd, payload = build_write(group, values)
        self.client.write_cmd(cmd, payload)
        actual = parse_group(group, self.client.read_cmd(GROUPS[group][0]))
        if group == '電流' and all(abs(actual[k] - values[k]) <= 0.011 for k in values):
            self.demo_original_current = None
        return actual

    def _demo_limit(self, limit, *, high_current_approved=False):
        # high_current_approved kept for compatibility; no UI opt-in in v0.17.
        # Validated firmware limits / overload-threshold and readback still apply.
        if self.learning_active:
            raise ProtocolError('行程學習中禁止調整展示限流')
        fw = read_info(self.client.read_cmd(0x70))
        device = read_info(self.client.read_cmd(0x71))
        if device != '0x0B01':
            raise ProtocolError('Demo 僅允許 CI76 Device Code 0x0B01')
        # Before learning, the 0x20 feedback fault is expected and allowed for physical I1/I2.
        errors = self.client.read_cmd(0x17)
        if len(errors) != 2 or (errors[0] & ~0x20) or errors[1]:
            raise ProtocolError('存在非待學習的故障旗標，不能調整 Demo 限流')
        status = self.client.read_cmd(0x12)
        if len(status) != 1:
            raise ProtocolError('未收到有效的馬達狀態')
        # Prefer manual control owner and known 0x0B01 FW.
        raw = self.client.read_cmd(0x19, timeout=0.28)
        command, payload, old, requested = demo_current_write(raw, float(limit))
        if self.demo_original_current is None:
            self.demo_original_current = raw
        self._service_urgent()
        self._check_bench_deadline()
        if self.learning_active:
            raise ProtocolError('正在學習，拒絕變更限流')
        self.client.write_cmd(command, payload, timeout=0.28)
        actual = None
        for attempt in range(4):
            self._service_urgent()
            self._check_bench_deadline()
            actual = parse_group('電流', self.client.read_cmd(0x19, timeout=0.25))
            if abs(actual['current_limit'] - requested['current_limit']) <= 0.011:
                break
            time.sleep(0.04)
        else:
            raise ProtocolError(f'限流讀回 {actual["current_limit"]:.2f} A 與要求值不一致')
        return {'requested_A': float(limit), 'actual_A': actual['current_limit'],
                'current_group': actual, 'saved_original': True}

    def _demo_restore(self):
        if self.motor_direction or self.learning_active:
            raise ProtocolError('先停止並確認馬達已停止，才能還原展示參數')
        if self.demo_original_current is None and self.demo_original_speed is None:
            return {'restored': False, 'reason': '本次連線尚未修改展示電流／速度'}
        status = self.client.read_cmd(0x12, timeout=0.3)
        if status not in (b'\x01', b'\x04', b'\x06', b'\x07'):
            raise ProtocolError('未確認馬達停止，拒絕還原參數')
        actual = None
        if self.demo_original_current is not None:
            original = parse_group('電流', self.demo_original_current)
            command, payload = build_write('電流', original)
            self.client.write_cmd(command, payload, timeout=0.3)
            actual = parse_group('電流', self.client.read_cmd(0x19, timeout=0.3))
            if any(abs(actual[k] - original[k]) > 0.011 for k in original):
                raise ProtocolError('原始電流參數讀回不一致，請人工核對')
        if self.demo_original_speed is not None:
            self.client.write_cmd(0x07, self.demo_original_speed, timeout=0.3)
            raw = self.client.read_cmd(0x20, timeout=0.3)
            if raw[:2] != self.demo_original_speed:
                raise ProtocolError('原始速度參數讀回不一致，請人工核對')
        self.demo_original_current = None
        self.demo_original_speed = None
        return {'restored': True, 'current_group': actual}

    def _demo_speed(self, percent):
        raw_value = validate_demo_speed(percent)
        if self.learning_active or self.motor_direction:
            raise ProtocolError('先停止 PC 控制並確認，才可改變 Demo 速度')
        fw = read_info(self.client.read_cmd(0x70))
        device = read_info(self.client.read_cmd(0x71))
        if (fw,device) != ('0x0B01','0x0B01'):
            raise ProtocolError('不支援的韌體')
        status = self.client.read_cmd(0x12)
        if status not in (b'\x01',b'\x04',b'\x06',b'\x07'):
            raise ProtocolError('請先釋放 I1／I2 並確認馬達停止，才能改變展示速度')
        original = self.client.read_cmd(0x20,timeout=0.35)
        if len(original)!=10:
            raise ProtocolError('速度設定讀回長度錯誤')
        if self.demo_original_speed is None:
            self.demo_original_speed = original[:2]
        payload = raw_value.to_bytes(2, 'little')
        self.client.write_cmd(0x07,payload,timeout=0.3)
        current = self.client.read_cmd(0x20,timeout=0.3)
        if len(current)!=10 or current[:2]!=payload:
            raise ProtocolError('速度命令 ACK，但 0x20 讀回與要求值不一致')
        return {'speed':percent,'original_saved':True}

    def _clear_active_faults(self):
        # Only clear CURRENT faults; never erase historical counters 0x16.
        if self.learning_active or self.motor_direction:
            raise ProtocolError('正在學習或 PC 控制動作中，不能清除錯誤旗標')
        state = self.client.read_cmd(0x12,timeout=0.3)
        if state not in (b'\x01',b'\x04',b'\x06',b'\x07'):
            raise ProtocolError('未確認馬達停止，請先釋放 I1／I2 並停機')
        old = self.client.read_cmd(0x17,timeout=0.3)
        command,payload=error_clear_payload()
        self.client.write_cmd(command,payload,timeout=0.3)
        time.sleep(0.12)
        new=self.client.read_cmd(0x17,timeout=0.3)
        if len(old)!=2 or len(new)!=2:
            raise ProtocolError('清除後讀回故障資料格式錯誤')
        return {'before':old.hex(' ').upper(),'after':new.hex(' ').upper(),'cleared':new==b'\x00\x00'}

    def _service_urgent(self):
        try:
            action, data = self.urgent.get_nowait()
        except Empty:
            return
        if action == 'learning_abort':
            try:
                self.success.emit('learning_abort', self._abort_learning())
            except Exception as exc:
                self.error.emit('learning_abort', '學習取消指令無法確認，請使用獨立硬體停止：' + str(exc))
        elif action == 'motor_stop':
            try:
                self.success.emit('motor_stop', self._stop_motor())
            except Exception as exc:
                self.motor_direction = None
                self.error.emit('motor_stop', f'停止命令未確認，請立即使用硬體停止裝置：{exc}')

    def _start_motor(self, direction, percent):
        if direction not in ('extend','retract'):
            raise ProtocolError('方向錯誤')
        if self.motor_direction:
            self._stop_motor()
        # Always verify live version, not only an old cached GUI reading.
        fw = read_info(self.client.read_cmd(0x70))
        device = read_info(self.client.read_cmd(0x71))
        if not firmware_motion_supported(fw, device):
            raise ProtocolError('現有 FW 不含失聯停止保護（需安全版 0x0B02 或更新）；馬達控制未開放')
        status = self.client.read_cmd(0x12)
        system = self.client.read_cmd(0x13)
        errors = self.client.read_cmd(0x17)
        validate_start(status, system, errors)
        try:
            self.client.write_cmd(0x03, b'\x01')
            time.sleep(0.035)
            system = self.client.read_cmd(0x13)
            if not system or system[0] != 1:
                raise ProtocolError('UART 模式啟用後讀回失敗')
            # Read current speed from 0x20 (first little-endian 16-bit value)
            # so a temporary motor-test speed does not silently replace it.
            raw_speed = self.client.read_cmd(0x20)
            if len(raw_speed) != 10:
                raise ProtocolError('無法讀取原始速度設定，禁止啟動')
            self.previous_speed_raw = int.from_bytes(raw_speed[:2], 'little')
            cmd, payload = motor_speed_command(percent)
            self.client.write_cmd(cmd, payload)
            cmd, payload = motor_position_command(direction)
            self.client.write_cmd(cmd, payload)
            self.motor_direction = direction
            self.motor_last_tick = time.monotonic()
            return {'direction': direction, 'speed': percent}
        except Exception:
            try:
                self._stop_motor()
            except Exception:
                pass
            raise

    def _diagnostics(self):
        info = {'version': read_info(self.client.read_cmd(0x70)),
                'device': read_info(self.client.read_cmd(0x71))}
        info['device_id'] = int.from_bytes(self.client.read_cmd(0x15), 'little')
        info['motor_seconds'] = parse_motor_seconds(self.client.read_cmd(0x14))
        info['counters'] = parse_error_counters(self.client.read_cmd(0x16))
        info['error_bytes'] = self.client.read_cmd(0x17).hex(' ').upper()
        info['system'] = self.client.read_cmd(0x13).hex(' ').upper()
        info['current_A'] = int.from_bytes(self.client.read_cmd(0x10),'little') / 100.0
        info['position_pct'] = int.from_bytes(self.client.read_cmd(0x11),'little') / 10.0
        info['actuator_status'] = self.client.read_cmd(0x12)[0]
        info['parameters'] = {}
        for name, spec in GROUPS.items():
            try:
                info['parameters'][name] = parse_group(name, self.client.read_cmd(spec[0]))
            except Exception as exc:
                info['parameters'][name] = {'read_error': str(exc)}
        return info

    def _monitor(self, data):
        config = data or {}
        auto = bool(config.get('auto', False))
        fast_demo = bool(config.get('fast_demo', False))
        # The worker owns the authoritative motion state. Never trust a stale
        # UI request to suppress status/fault reads during PC motion/learning.
        current_only = bool(auto and fast_demo and config.get('current_only', False)
                            and not (self.motor_direction or self.bench_uart_enabled
                                     or self.bench_limited_motion or self.learning_active
                                     or not self.urgent.empty()))
        log_frames = bool(config.get('log_frames', False))
        # Short per-request deadline when auto polling; no blocking for 1.2s.
        timeout = 0.12 if auto else 0.5
        start = time.monotonic()
        self._mute_trace = auto and not log_frames
        ok, failed = [], []
        try:
            commands = scheduled_monitor_commands(
                auto=auto,
                now=time.monotonic(), last=self._slow_time,
                fast_demo=fast_demo, current_only=current_only,
            )
            learning_status, learning_flags = None, None
            for cmd in commands:
                self._service_urgent()
                self._check_bench_deadline()
                self._heartbeat()
                try:
                    payload = self.client.read_cmd(cmd, timeout=timeout)
                    values = decode_monitor(cmd, payload)
                    if cmd == 0x12:
                        learning_status = payload
                        self.last_learn_status = payload
                    if cmd == 0x17:
                        learning_flags = payload
                        self.last_learn_flags = payload
                    self.success.emit('monitor_item', values)
                    ok.extend(values)
                    if (self.motor_direction and
                        ((cmd == 0x17 and payload != b'\x00\x00') or
                         (cmd == 0x13 and len(payload) == 2 and payload[0] != 1) or
                         (cmd == 0x12 and payload in (b'\x04', b'\x06', b'\x07')
                          and time.monotonic() - self.motor_last_tick >= 0.4))):
                        try:
                            self.success.emit('motor_autostop', self._stop_motor())
                        except Exception as stop_exc:
                            self.error.emit('motor_lost', f'自動停止命令失敗：{stop_exc}')
                except Exception as exc:
                    # Old FW never self-stops on loss of UART: keep attempting STOP
                    # but never claim this is an independent safety mechanism.
                    if self.bench_limited_motion and self.motor_direction and cmd in (0x12, 0x17):
                        try:
                            self.success.emit('motor_autostop', self._stop_motor())
                        except Exception as stop_exc:
                            self.error.emit('motor_lost', '監控失聯且 STOP 無回覆，請立刻使用硬體斷電：' + str(stop_exc))
                    self.success.emit('monitor_problem', (cmd, str(exc)))
                    failed.append(f'0x{cmd:02X}: {exc}')
            if self.learning_active:
                # A visible 0x05 confirms learning motor state; completion is
                # inferred only after 0x05 was observed and fault=0/stopped.
                stage = learning_observation(self.learning_seen, self.last_learn_status, self.last_learn_flags)
                if stage == 'learning': self.learning_seen = True
                if stage != self.last_learning_stage and stage != 'pending':
                    self.last_learning_stage = stage
                    self.success.emit('learning_stage', stage)
                if stage in ('failed', 'completed_candidate'):
                    self.learning_active = False
                    self.success.emit('learning_result', {'stage': stage})
            self.success.emit('monitor', {
                'ok': ok, 'failed': failed, 'auto': auto,
                'elapsed_ms': round((time.monotonic() - start) * 1000),
                'sample_at': time.monotonic(),
                'current_only': current_only,
            })
        finally:
            self._mute_trace = False

    def run(self):
        while self.running:
            self._service_urgent()
            self._check_bench_deadline()
            self._heartbeat()
            try:
                action, data = self.jobs.get(timeout=0.04)
            except Empty:
                continue
            try:
                if action == 'connect':
                    if self.client:
                        if self.motor_direction:
                            self._stop_motor()
                        self.client.close()
                    self.client = DeviceClient.open(data, self._trace)
                    self.motor_direction = None
                    self.bench_uart_enabled = False
                    self.bench_limited_motion = False
                    self.bench_deadline = 0.0
                    self.abort_motion_request = False
                    self.previous_speed_raw = None
                    self.learning_active = False
                    self.learning_seen = False
                    self.learning_abort_requested = False
                    self.demo_original_current = None
                    self.demo_original_speed = None
                    self._slow_time = {0x12: 0.0, 0x13: 0.0, 0x17: 0.0, 0x14: 0.0}
                    self.success.emit('connect', data)
                elif action == 'disconnect':
                    if self.learning_active:
                        raise ProtocolError('學習尚未確認結束，請先取消學習並現場確認停止')
                    if self.demo_original_current is not None or self.demo_original_speed is not None:
                        raise ProtocolError('展示限流／速度仍被修改，請先按「還原原設定」並確認讀回')
                    if self.client:
                        if self.motor_direction:
                            self._stop_motor()
                        if self.bench_uart_enabled:
                            self._bench_uart_mode(False)
                        self.client.close()
                        self.client = None
                    self.success.emit('disconnect', None)
                elif self.client is None:
                    raise RuntimeError('請先連線 COM Port')
                elif action == 'identity':
                    info = {'version': read_info(self.client.read_cmd(0x70)),
                            'device': read_info(self.client.read_cmd(0x71))}
                    try:
                        info['sensor_mode'] = parse_sensor_status(self.client.read_cmd(0x13))
                    except Exception:
                        info['sensor_mode'] = None
                    try:
                        info['motor_seconds'] = int.from_bytes(self.client.read_cmd(0x14), 'little')
                    except Exception:
                        info['motor_seconds'] = None
                    self.success.emit('identity', info)
                elif action == 'readgroup':
                    payload = self.client.read_cmd(GROUPS[data][0])
                    self.success.emit('readgroup', (data, parse_group(data, payload)))
                elif action == 'readall':
                    ok, failed = [], []
                    for group, spec in GROUPS.items():
                        try:
                            values = parse_group(group, self.client.read_cmd(spec[0]))
                            self.success.emit('readgroup_part', (group, values))
                            ok.append(group)
                        except Exception as exc:
                            failed.append((group, str(exc)))
                            self.success.emit('group_problem', (group, str(exc)))
                    self.success.emit('readall', {'ok': ok, 'failed': failed})
                elif action == 'writegroup':
                    group, values = data
                    actual = self._write_group(group, values)
                    self.success.emit('writegroup', (group, actual, values))
                elif action == 'sensor_read':
                    raw = self.client.read_cmd(0x13)
                    self.success.emit('sensor_read', parse_sensor_status(raw))
                elif action == 'sensor_write':
                    # Confirm idle from device, not from an untrusted cached UI value.
                    status = self.client.read_cmd(0x12)
                    require_stopped_motor(status)
                    command, payload = build_sensor_write(data)
                    self.client.write_cmd(command, payload)
                    # Controller applies sensor-mode on the next control loop.
                    latest = None
                    for _ in range(4):
                        time.sleep(0.05)
                        latest = parse_sensor_status(self.client.read_cmd(0x13))
                        if latest == data:
                            break
                    if latest != data:
                        raise ProtocolError('感測器 ACK 已回覆，但狀態讀回不一致')
                    self.success.emit('sensor_write', latest)
                elif action == 'motor_time_read':
                    self.success.emit('monitor_item', decode_monitor(0x14, self.client.read_cmd(0x14)))
                    self.success.emit('motor_time_read', None)
                elif action == 'motor_time_reset':
                    if self.motor_direction:
                        raise ProtocolError('推桿執行中，不能歸零運轉時間')
                    status = self.client.read_cmd(0x12)
                    if len(status) != 1 or status[0] not in (1, 4, 6, 7):
                        raise ProtocolError('停止狀態未確認，不能歸零')
                    cmd, payload = build_motor_time_reset()
                    self.client.write_cmd(cmd, payload)
                    time.sleep(0.06)
                    seconds = parse_motor_seconds(self.client.read_cmd(0x14))
                    if seconds != 0:
                        raise ProtocolError(f'歸零命令 ACK，但讀回仍為 {seconds} 秒')
                    self.success.emit('motor_time_reset', {'seconds': seconds, 'power_cycle_verified': False})
                elif action == 'diagnostics':
                    if self.motor_direction:
                        raise ProtocolError('請先停止推桿，再執行完整診斷')
                    self.success.emit('diagnostics', self._diagnostics())
                elif action == 'learning_start':
                    self.success.emit('learning_start', self._start_learning())
                elif action == 'learning_abort':
                    self.success.emit('learning_abort', self._abort_learning())
                elif action == 'demo_limit':
                    limit = data[0] if isinstance(data, tuple) else data
                    self.success.emit('demo_limit', self._demo_limit(limit))
                elif action == 'demo_restore':
                    self.success.emit('demo_restore', self._demo_restore())
                elif action == 'demo_speed':
                    self.success.emit('demo_speed', self._demo_speed(data))
                elif action == 'error_clear':
                    self.success.emit('error_clear', self._clear_active_faults())
                elif action == 'bench_uart_mode':
                    self.success.emit('bench_uart_mode', self._bench_uart_mode(bool(data)))
                elif action == 'bench_start':
                    direction, speed = data
                    self.success.emit('motor_start', self._start_bench(direction, speed))
                elif action == 'motor_start':
                    if self.abort_motion_request:
                        raise ProtocolError('已發送 STOP，取消啟動')
                    direction, speed = data
                    self.success.emit('motor_start', self._start_motor(direction, speed))
                elif action == 'motor_stop':
                    self.success.emit('motor_stop', self._stop_motor())
                elif action == 'monitor':
                    self._monitor(data)
                else:
                    raise ValueError(f'不支援的工作：{action}')
            except Exception as exc:
                self.error.emit(action, str(exc))
        if self.client:
            if self.motor_direction:
                try:
                    self._stop_motor()
                except Exception as exc:
                    self.error.emit('motor_lost', '程式退出時 STOP 失敗：' + str(exc))
            if self.bench_uart_enabled:
                try:
                    self._bench_uart_mode(False)
                except Exception as exc:
                    self.error.emit('motor_lost', '程式退出時 UART MODE 關閉失敗：' + str(exc))
            self.client.close()

    def _trace(self, direction, raw):
        if not self._mute_trace:
            self.trace.emit(f'{direction}  {raw.hex(" ").upper()}')
