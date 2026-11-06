"""MOTECK CI76 Configuration Tool v0.18 CONTROL CENTER (LAB).
Experimental time-limited host-controlled jogging for unmodified 0x0B01 firmware.
A physical independent motor-power cutoff is MANDATORY; I1 is not E-stop.
"""
from __future__ import annotations
import sys
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QTabWidget,
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QPlainTextEdit, QGroupBox,
    QFormLayout, QDoubleSpinBox, QSpinBox, QCheckBox, QFileDialog,
    QMessageBox, QSizePolicy, QFrame, QProgressBar, QSlider, QScrollArea,
)
from serial.tools import list_ports
from protocol import FIELDS, GROUPS, ProtocolError, build_write, SENSOR_MODE_LABELS, format_motor_seconds
from ui_ranges import field_editor_spec
from worker import SerialWorker
from monitoring import gauge_value
from diagnostics import FLAGS
from config_io import save_profile, load_profile
from motion import firmware_motion_supported
from current_limits import (CURRENT_SLIDER_MIN_A, CURRENT_SLIDER_MAX_A,
                            amps_to_ticks, ticks_to_amps, within_slider_range)
from eventlog import EventLog
from dial import CurrentDial
from hud_widgets import HudRingDial

# Shared theme is applied by CI76Window too, including script/test entrypoints.
from theme import STYLESHEET, apply_theme, configure_port_popup, brand_label
from settings_store import SettingsStore, PortIdentity, match_port

GROUP_LAYOUT = (('電壓','回生','電流'), ('速度','位置'))
LIVE_FIELDS = (('motor','推桿狀態'), ('uart','UART 模式'),
               ('sensor','感測器'), ('errors','錯誤碼'))

GAUGES = (
    ('current', '馬達電流（估算）', 'A', 10.0, '#40D3BF'),
    ('position', '目前位置', '%', 100.0, '#3BA7FF'),
)


class CI76Window(QMainWindow):
    def __init__(self, *, settings_store=None):
        super().__init__()
        apply_theme()
        self.preferences = settings_store or SettingsStore()
        self._port_inventory = []
        self._connecting_port = None
        self._connection_pending = False
        self._startup_attempted = False
        self._user_disconnected = False
        self._connection_failure = None
        self._link_stale = False
        self._current_draft_dirty = False
        self._applying_group = False
        self.setWindowTitle('MOTECK | CI76 Control Center v0.18 R4 LAB')
        self.resize(1360, 820)
        self.setMinimumSize(1100, 660)
        self.connected = False
        self.pending = 0
        self._foreground_pending = False
        self._last_monitor_ts = None
        self._last_demo_current_ts = None
        self._background_paused = False
        self._current_only_failures = 0
        self._last_issue_at = {}
        self.last_error_bits = None
        self.fields = {}
        self.last_values = {}
        self.identity_verified = False
        self.group_read_ok = set()
        self.write_buttons = {}
        self.sensor_mode_current = None
        self.sensor_mode_ready = False
        self.local_profile_loaded = False
        self.motion_active = None
        self.motion_supported = False
        self.motion_approved = False
        self.stop_pending = False
        self.legacy_fw = False
        self.bench_uart_enabled = False
        self.latest_monitor = {}
        self.learning_requested = False
        self.learning_seen = False
        self.interlock_fault = False
        self.demo_dirty = False
        self.demo_verified_limit = None
        self.demo_speed_modified = False
        self._demo_pending_value = None
        self._demo_write_inflight = False
        self._demo_last_sent = None
        self.latest_diagnostics = None
        self._last_telemetry_log = 0.0
        self.event_store = EventLog()
        self.worker = SerialWorker()
        self.worker.success.connect(self.on_success)
        self.worker.error.connect(self.on_error)
        self.worker.trace.connect(self.log)
        self.worker.start()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll_once)
        self.demo_update_timer = QTimer(self)
        self.demo_update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.demo_update_timer.setInterval(50)
        self.demo_update_timer.timeout.connect(self._flush_demo_limit)

        central = QWidget()
        central.setObjectName('centralRoot')
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 6, 10, 4)
        root.setSpacing(4)

        # Text-based MOTECK brand lockup; the accent colors are a design
        # treatment, not a claim that this is an official corporate logo.
        brand = QFrame()
        brand.setObjectName('brandBar')
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(12, 5, 12, 5)
        brand_row.setSpacing(12)
        brand_names = QVBoxLayout()
        brand_names.setSpacing(1)
        brand_word = brand_label()
        brand_names.addWidget(brand_word)
        brand_detail = QLabel('CI76  /  MOTION CONTROL SYSTEMS')
        brand_detail.setObjectName('brandDetail')
        brand_names.addWidget(brand_detail)
        brand_row.addLayout(brand_names)
        brand_row.addStretch()
        right_head = QVBoxLayout()
        right_head.setSpacing(3)
        hero = QLabel('CI76 CONTROL CENTER')
        hero.setObjectName('heroTitle')
        hero.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_head.addWidget(hero)
        tag = QLabel('LAB v0.18 · R4   •   UART 115200 / 8N1   •   Protocol 251110')
        tag.setObjectName('buildTag')
        tag.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_head.addWidget(tag)
        brand_row.addLayout(right_head)
        self.header_firmware = QLabel('FW —')
        self.header_firmware.setObjectName('brandDetail')
        brand_row.addWidget(self.header_firmware)
        root.addWidget(brand)

        tools = QHBoxLayout()
        config_load = QPushButton('載入 .config')
        config_load.setToolTip('僅載入到畫面，不會自動寫入 CI76')
        config_load.clicked.connect(self.load_config)
        config_save = QPushButton('匯出 .config')
        config_save.setToolTip('將目前顯示的參數匯出到本機檔案')
        config_save.clicked.connect(self.save_config)
        tools.addWidget(config_load)
        tools.addWidget(config_save)

        conn = QGroupBox('COM 連線')
        conn_row = QHBoxLayout(conn)
        conn_row.setContentsMargins(10, 6, 10, 6)
        conn_row.setSpacing(6)
        self.ports = QComboBox()
        configure_port_popup(self.ports)
        self.refresh_ports()
        self.refresh_btn = QPushButton('掃描')
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn = QPushButton('連線')
        self.connect_btn.setObjectName('primary')
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.auto_connect_check = QCheckBox('啟動時自動連線')
        self.auto_connect_check.setChecked(self.preferences.auto_connect)
        self.auto_connect_check.setToolTip('預設關閉；僅對唯一符合上次已驗證紀錄的裝置嘗試一次，並先讀取 Device Code')
        self.auto_connect_check.toggled.connect(self.preferences.set_auto_connect)
        self.connection_label = QLabel('● 未連線')
        self.connection_label.setStyleSheet('color:#D68C95;font-weight:700')
        conn_row.addWidget(QLabel('Port'))
        conn_row.addWidget(self.ports, 1)
        conn_row.addWidget(self.refresh_btn)
        conn_row.addWidget(self.connect_btn)
        conn_row.addWidget(self.auto_connect_check)
        conn_row.addWidget(self.connection_label)
        root.addWidget(conn)

        actions = QHBoxLayout()
        self.identity_btn = QPushButton('讀取設備資訊')
        self.identity_btn.clicked.connect(lambda: self.submit('identity'))
        self.readall_btn = QPushButton('讀取全部參數')
        self.readall_btn.setObjectName('primary')
        self.readall_btn.clicked.connect(lambda: self.submit('readall'))
        self.monitor_btn = QPushButton('立即讀取狀態')
        self.monitor_btn.clicked.connect(self.read_status_once)
        self.auto_poll = QCheckBox('自動監控')
        self.auto_poll.toggled.connect(self.poll_toggled)
        self.poll_period = QComboBox()
        for ms in (50, 100, 200, 500, 1000, 1500):
            self.poll_period.addItem(f'{ms} ms', ms)
        self.poll_period.currentIndexChanged.connect(self.poll_period_changed)
        self.poll_rate = QLabel('電流實際：—')
        self.poll_rate.setMinimumWidth(115)
        self.poll_rate.setStyleSheet('color:#7ACCC8')
        for b in (self.identity_btn, self.readall_btn, self.monitor_btn):
            actions.addWidget(b)
        actions.addWidget(self.auto_poll)
        actions.addWidget(self.poll_period)
        actions.addWidget(self.poll_rate)
        self.poll_trace = QCheckBox('記錄輪詢封包')
        self.poll_trace.toggled.connect(self._sync_demo_monitor)
        self.poll_trace.setToolTip('50/100ms 自動輪詢時關閉可避免 UART log 每秒大量刷屏')
        tools.insertWidget(0, self.poll_trace)
        actions.addLayout(tools)
        root.addLayout(actions)

        # Keep the familiar one-page settings screen intact inside its own tab.
        main_tab = QWidget()
        main_tab.setObjectName('settingsPage')
        main_tab_layout = QVBoxLayout(main_tab)
        main_tab_layout.setContentsMargins(0, 0, 0, 0)
        main_tab_layout.setSpacing(5)
        # One compact cross-column control strip. Never squeeze the monitoring panel.
        motor_box = QGroupBox('推桿控制 / 內部安全測試台')
        motor_layout = QVBoxLayout(motor_box)
        motor_layout.setContentsMargins(8, 6, 8, 5)
        motor_layout.setSpacing(2)
        motor_row = QHBoxLayout()
        motor_layout.addLayout(motor_row)
        motor_row.setContentsMargins(8, 6, 8, 5)
        motor_row.setSpacing(5)
        self.uart_mode_btn = QPushButton('UART MODE：OFF')
        self.uart_mode_btn.setToolTip('僅供舊 FW 0x0B01 內部短時測試；切換時讀回 0x13。I1 不是緊急停止。')
        self.uart_mode_btn.clicked.connect(self.toggle_bench_uart_mode)
        motor_row.addWidget(self.uart_mode_btn)
        motor_row.addWidget(QLabel('速度'))
        self.motor_speed = QSpinBox()
        self.motor_speed.setRange(0, 100)
        self.motor_speed.setValue(20)
        self.motor_speed.setSuffix(' %')
        self.motor_speed.setToolTip('設定 0～100%；FW 0x0B01 運轉仍限 PC 端 2 秒，0% 不啟動')
        motor_row.addWidget(self.motor_speed)
        self.extend_btn = QPushButton('伸出 ▶')
        self.retract_btn = QPushButton('◀ 縮回')
        self.stop_btn = QPushButton('■ 停止（Esc）')
        self.stop_btn.setObjectName('stopButton')
        self.extend_btn.clicked.connect(lambda: self.request_motion('extend'))
        self.retract_btn.clicked.connect(lambda: self.request_motion('retract'))
        self.stop_btn.clicked.connect(self.request_stop)
        motor_row.addWidget(self.extend_btn)
        motor_row.addWidget(self.retract_btn)
        motor_row.addWidget(self.stop_btn)
        self.motor_feedback = QLabel('需具備 800 ms 失聯停止保護的韌體')
        self.motor_feedback.setMinimumWidth(130)
        self.motor_feedback.setStyleSheet('color:#E8B17C;font-size:8pt')
        diagnostic_row = QHBoxLayout()
        diagnostic_row.setSpacing(7)
        diagnostic_row.addWidget(self.motor_feedback, 1)
        self.diagnostic_btn = QPushButton('擷取診斷')
        self.diagnostic_btn.clicked.connect(lambda: self.submit('diagnostics'))
        diagnostic_row.addWidget(self.diagnostic_btn)
        self.clear_fault_btn = QPushButton('清除錯誤')
        self.clear_fault_btn.setToolTip('僅發送 0x0F/02 清除目前故障位，0x16 歷史次數保留；未解決的故障仍會存在')
        self.clear_fault_btn.clicked.connect(self.request_clear_faults)
        diagnostic_row.addWidget(self.clear_fault_btn)
        self.logs_btn = QPushButton('Log 資料夾')
        self.logs_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.event_store.folder))))
        diagnostic_row.addWidget(self.logs_btn)
        warning = QLabel('⚠ FW 0x0B01：每次最多 2 秒（僅 PC 端計時）。斷線可能無法自停；I1 不是緊急停止。請備獨立硬體斷電。')
        motor_box.setToolTip(warning.text())
        self.learn_btn = QPushButton('開始行程學習')
        self.learn_btn.setToolTip('UART 0x02/01；學習將自行走完整個行程，需具備獨立硬體停止設備')
        self.learn_btn.clicked.connect(self.request_learning_start)
        self.learn_abort_btn = QPushButton('取消學習')
        self.learn_abort_btn.clicked.connect(self.request_learning_abort)
        self.learn_feedback = QLabel('尚未開始行程學習')
        self.learn_feedback.setStyleSheet('color:#93B9C8;font-size:8pt')
        motor_row.addWidget(self.learn_btn)
        motor_row.addWidget(self.learn_abort_btn)
        motor_row.addWidget(self.learn_feedback, 1)
        self.learn_feedback.setWordWrap(True)
        self.motor_feedback.setToolTip(warning.text())
        motor_layout.addLayout(diagnostic_row)
        main_tab_layout.addWidget(motor_box)
        self.stop_shortcut = QShortcut(QKeySequence('Esc'), self)
        self.stop_shortcut.activated.connect(self.request_stop)

        # The central content has a natural height and is NEVER compressed
        # below it. On smaller screens only, the scroll area provides a safe
        # vertical scrollbar instead of clipping / overlapping widgets.
        content = QWidget()
        content.setObjectName('settingsContent')
        grid = QGridLayout(content)
        grid.setContentsMargins(1, 1, 1, 1)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        for col, groups in enumerate(GROUP_LAYOUT):
            stack = QVBoxLayout()
            stack.setSpacing(5)
            for group in groups:
                stack.addWidget(self._create_group(group))
            stack.addStretch()
            grid.addLayout(stack, 0, col)

        right = QVBoxLayout()
        right.setSpacing(5)
        ident = QGroupBox('設備資訊')
        self.device_group = ident
        id_form = QFormLayout(ident)
        id_form.setContentsMargins(9, 5, 7, 5)
        id_form.setVerticalSpacing(2)
        self.fw_label = QLabel('—')
        self.device_label = QLabel('—')
        self.sensor_current_label = QLabel('—（尚未讀取）')
        self.motor_time_label = QLabel('—（尚未讀取）')
        self.motor_time_label.setToolTip('UART 0x14：馬達累積運轉時間，單位秒；並非設備上電總時間')
        id_form.addRow('Firmware Version', self.fw_label)
        id_form.addRow('Device Code', self.device_label)
        id_form.addRow('感測器（目前）', self.sensor_current_label)
        time_controls = QWidget()
        time_row = QHBoxLayout(time_controls)
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(3)
        time_row.addWidget(self.motor_time_label, 1)
        self.time_reset_btn = QPushButton('歸零')
        self.time_reset_btn.setToolTip('UART 0x0F/0x03。清除後讀回驗證；斷電保存需另做實板測試')
        self.time_reset_btn.clicked.connect(self.request_motor_time_reset)
        time_row.addWidget(self.time_reset_btn)
        id_form.addRow('累積運轉時間', time_controls)
        right.addWidget(ident)

        sensor_setting = QWidget()
        sensor_row = QHBoxLayout(sensor_setting)
        sensor_row.setContentsMargins(0, 0, 0, 0)
        sensor_row.setSpacing(3)
        self.sensor_select = QComboBox()
        self.sensor_select.addItem('雙 Hall', 1)
        self.sensor_select.addItem('POT', 2)
        self.sensor_select.currentIndexChanged.connect(self._update_sensor_button)
        self.sensor_apply_btn = QPushButton('套用')
        self.sensor_apply_btn.setToolTip('需先讀取當前感測器；確認完全停止後才可切換')
        self.sensor_apply_btn.clicked.connect(self.apply_sensor_mode)
        sensor_row.addWidget(self.sensor_select, 1)
        sensor_row.addWidget(self.sensor_apply_btn)
        id_form.addRow('切換感測器', sensor_setting)

        monitor = QGroupBox('即時監控（唯讀）')
        self.monitor_group = monitor
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(9, 5, 9, 6)
        monitor_layout.setSpacing(3)
        self.live = {}
        self.gauge_bars = {}
        for key, label, unit, maximum, color in GAUGES:
            meter = QWidget()
            meter_layout = QVBoxLayout(meter)
            meter_layout.setContentsMargins(0, 0, 0, 0)
            meter_layout.setSpacing(1)
            meter_header = QHBoxLayout()
            meter_header.addWidget(QLabel(label))
            meter_header.addStretch()
            display = QLabel('— ' + unit)
            display.setStyleSheet('color:#B2F0E9;font-size:12pt;font-weight:700')
            meter_header.addWidget(display)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setObjectName('positionBar' if key == 'position' else 'telemetryBar')
            meter_layout.addLayout(meter_header)
            meter_layout.addWidget(bar)
            self.live[key] = display
            self.gauge_bars[key] = (bar, maximum, unit)
            monitor_layout.addWidget(meter)
        # 2 x 2 status tiles replace four tall form rows, reducing the
        # height by half without losing any information.
        status_grid = QGridLayout()
        status_grid.setContentsMargins(0, 1, 0, 1)
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(2)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        for index, (key, label) in enumerate(LIVE_FIELDS):
            cell = QWidget()
            cell_row = QHBoxLayout(cell)
            cell_row.setContentsMargins(0, 0, 0, 0)
            cell_row.setSpacing(3)
            description = QLabel(label + '：')
            description.setStyleSheet('color:#90AFBE;font-size:8pt;')
            value = QLabel('—')
            value.setMinimumWidth(0)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            value.setToolTip(label)
            self.live[key] = value
            cell_row.addWidget(description)
            cell_row.addWidget(value, 1)
            status_grid.addWidget(cell, index // 2, index % 2)
        monitor_layout.addLayout(status_grid)
        flag_header = QHBoxLayout()
        flag_header.addWidget(QLabel('錯誤旗標（0x17）'))
        flag_header.addStretch()
        self.error_overview = QLabel('尚未查詢')
        self.error_overview.setStyleSheet('color:#98B8C5;font-weight:600;')
        flag_header.addWidget(self.error_overview)
        monitor_layout.addLayout(flag_header)
        flag_grid = QGridLayout()
        flag_grid.setHorizontalSpacing(3)
        flag_grid.setVerticalSpacing(2)
        self.flag_labels = {}
        for index, definition in enumerate(FLAGS):
            item = QLabel('— ' + definition.label)
            item.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setMinimumHeight(22)
            item.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            item.setToolTip(f'Byte {definition.byte} / Mask 0x{definition.mask:02X}')
            item.setStyleSheet(self._flag_style('unknown'))
            self.flag_labels[definition.key] = item
            flag_grid.addWidget(item, index // 3, index % 3)
        monitor_layout.addLayout(flag_grid)
        right.addWidget(monitor)
        right.addStretch()
        grid.addLayout(right, 0, 2)
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll.setWidget(content)
        main_tab_layout.addWidget(self.main_scroll, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(main_tab, 'CONTROL   /   參數設定')
        self.demo_tab = self._build_demo_tab()
        self.tabs.addTab(self.demo_tab, 'TUNING   /   電流展示')
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        # Keep recording every UART event, but avoid occupying 135px of
        # permanent screen height. The user can expand it at any time.
        log_head = QHBoxLayout()
        self.log_title = QLabel('UART TX / RX 通訊紀錄（收合）')
        log_head.addWidget(self.log_title)
        log_head.addStretch()
        self.log_toggle = QPushButton('展開紀錄')
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self.toggle_log)
        log_head.addWidget(self.log_toggle)
        log_clear = QPushButton('清除')
        log_clear.clicked.connect(self._clear_log)
        log_head.addWidget(log_clear)
        root.addLayout(log_head)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(900)
        self.console.setMinimumHeight(85)
        self.console.setMaximumHeight(155)
        root.addWidget(self.console)
        self.console.setVisible(False)
        self.statusBar().showMessage('MOTECK CI76 · LAB 版  |  參數以 MCU 讀回為準  |  未改變既有馬達安全限制  |  Flash 保存待驗證')
        self.set_connected(False)
        QTimer.singleShot(0, self._startup_connection)

    def _build_demo_tab(self):
        """Reference-photo-inspired cockpit HUD; existing UART logic is unchanged."""
        page = QWidget()
        page.setObjectName('hudPage')
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QVBoxLayout(page)
        root.setContentsMargins(13, 11, 13, 10)
        root.setSpacing(8)

        def panel(name='hudPanel'):
            w = QFrame()
            w.setObjectName(name)
            return w

        header = QHBoxLayout()
        heading_col = QVBoxLayout()
        heading_col.setSpacing(1)
        heading = QLabel('CURRENT TUNING   /   LIVE TELEMETRY')
        heading.setObjectName('hudHeading')
        heading_col.addWidget(heading)
        sub = QLabel('MOTECK  ·  CI76 SERIES  ·  BRUSHED DC MOTOR  ·  UART DATA')
        sub.setObjectName('hudCaption')
        heading_col.addWidget(sub)
        header.addLayout(heading_col, 1)
        header.addWidget(QLabel('DISPLAY'), 0, Qt.AlignmentFlag.AlignVCenter)
        self.demo_view_combo = QComboBox()
        self.demo_view_combo.addItem('Bar + Gauge', 'both')
        self.demo_view_combo.addItem('Bar only', 'bar')
        self.demo_view_combo.addItem('Gauge only', 'dial')
        self.demo_view_combo.currentIndexChanged.connect(self._update_demo_view)
        header.addWidget(self.demo_view_combo)
        root.addLayout(header)
        notes = QLabel('限流滑桿調整的是「最大允許電流」，並非固定輸出電流或實際推力。實際電流由 UART 0x10 回報；請勿用手阻擋推桿測力。')
        notes.setObjectName('hudCaption')
        notes.setWordWrap(True)
        root.addWidget(notes)

        main_row = QHBoxLayout()
        main_row.setSpacing(8)
        # LEFT: measured current, shown as a dial and a compact bar.
        left_card = panel()
        left = QVBoxLayout(left_card)
        left.setContentsMargins(8, 6, 8, 6)
        left.setSpacing(1)
        self.demo_current_dial = HudRingDial('ACTUAL MOTOR CURRENT')
        left.addWidget(self.demo_current_dial, 1)
        self.demo_actual = QLabel('— A')
        self.demo_actual.setObjectName('hudNum')
        self.demo_actual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.demo_actual)
        self.demo_current_bar = QProgressBar()
        self.demo_current_bar.setRange(0, 1000)
        self.demo_current_bar.setValue(0)
        self.demo_current_bar.setTextVisible(False)
        left.addWidget(self.demo_current_bar)
        self.demo_sample_rate = QLabel('電流刷新：—')
        self.demo_sample_rate.setObjectName('hudCaption')
        self.demo_sample_rate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.demo_sample_rate)
        main_row.addWidget(left_card, 1)

        # Central illustration removed: measured and configured current are the focus.

        # RIGHT: interactive setpoint shown by a second, visually matched dial.
        right_card = panel()
        right = QVBoxLayout(right_card)
        right.setContentsMargins(8, 6, 8, 6)
        right.setSpacing(1)
        self.hud_limit_dial = HudRingDial('CURRENT LIMIT SETPOINT')
        self.hud_limit_dial.setReading(1.0)
        # Compatibility readout model; only actual current needs a gauge.
        self.hud_limit_dial.setParent(right_card)
        self.hud_limit_dial.hide()
        right.addWidget(QLabel('CURRENT LIMIT CONTROL / 最大允許電流'))
        self.demo_target = QLabel('1.00 A')
        self.demo_target.setObjectName('hudNum')
        self.demo_target.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.demo_target)
        self.demo_applied = QLabel('MCU 已確認：— A')
        self.demo_applied.setObjectName('hudStatus')
        self.demo_applied.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.demo_applied)
        main_row.addWidget(right_card, 1)
        root.addLayout(main_row, 4)

        controls = panel()
        control_layout = QVBoxLayout(controls)
        control_layout.setContentsMargins(12, 7, 12, 7)
        control_layout.setSpacing(4)
        slider_title = QHBoxLayout()
        slider_title.addWidget(QLabel('CURRENT LIMIT CONTROL  /  0.00 – 8.00 A'))
        slider_title.addStretch()
        self.demo_target_spin = QDoubleSpinBox()
        self.demo_target_spin.setDecimals(2)
        self.demo_target_spin.setRange(CURRENT_SLIDER_MIN_A, CURRENT_SLIDER_MAX_A)
        self.demo_target_spin.setSingleStep(0.05)
        self.demo_target_spin.setSuffix(' A')
        self.demo_target_spin.setValue(1.00)
        self.demo_target_spin.setMinimumWidth(116)
        self.demo_target_spin.valueChanged.connect(self._demo_spin_to_slider)
        slider_title.addWidget(self.demo_target_spin)
        control_layout.addLayout(slider_title)
        self.demo_slider = QSlider(Qt.Orientation.Horizontal)
        self.demo_slider.setRange(amps_to_ticks(CURRENT_SLIDER_MIN_A), amps_to_ticks(CURRENT_SLIDER_MAX_A))
        self.demo_slider.setValue(100)
        self.demo_slider.setSingleStep(5)
        self.demo_slider.setPageStep(10)
        self.demo_slider.valueChanged.connect(self._on_demo_slider_changed)
        self.demo_slider.sliderReleased.connect(self._flush_demo_limit)
        control_layout.addWidget(self.demo_slider)
        slider_ends = QHBoxLayout()
        low = QLabel('0.00 A  /  MIN')
        low.setObjectName('hudCaption')
        high = QLabel('8.00 A  /  MAX')
        high.setObjectName('hudCaption')
        slider_ends.addWidget(low)
        slider_ends.addStretch()
        slider_ends.addWidget(high)
        control_layout.addLayout(slider_ends)
        control_row = QHBoxLayout()
        note = QLabel('0–8 A 可直接設定  ·  限流不得高於 MCU 過載門檻  ·  僅限已驗證治具')
        note.setObjectName('hudCaption')
        control_row.addWidget(note, 1)
        self.demo_apply_btn = QPushButton('立即套用 / 重試')
        self.demo_apply_btn.clicked.connect(self._demo_apply_now)
        control_row.addWidget(self.demo_apply_btn)
        self.demo_restore_btn = QPushButton('還原展示前設定')
        self.demo_restore_btn.clicked.connect(self.request_demo_restore)
        control_row.addWidget(self.demo_restore_btn)
        control_layout.addLayout(control_row)
        self.demo_write_status = QLabel('每 50 ms 合併最新目標；寫入期間穿插電流監控，MCU 讀回後才確認生效')
        self.demo_write_status.setObjectName('hudCaption')
        self.demo_write_status.setWordWrap(True)
        control_layout.addWidget(self.demo_write_status)
        right.addWidget(controls)
        right.addStretch()

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        for name, attr, initial in [
            ('MOTOR STATUS', 'hud_motor_state', 'NO DATA'),
            ('COM LINK', 'hud_link', 'DISCONNECTED'),
            ('SENSOR SELECTED', 'hud_sensor', 'UNKNOWN'),
            ('FAULT FLAGS', 'hud_fault', 'NOT READ'),
        ]:
            card = panel('hudStatusPanel')
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 5, 8, 5)
            cl.setSpacing(2)
            lab = QLabel(name)
            lab.setObjectName('hudCaption')
            cl.addWidget(lab)
            status = QLabel(initial)
            status.setObjectName('hudStatus')
            cl.addWidget(status)
            setattr(self, attr, status)
            status_row.addWidget(card, 1)
        root.addLayout(status_row)
        foot = QLabel('MOTECK CI76  /  LIVE CURRENT TELEMETRY  ·  限流設定 ≠ 固定輸出電流  ·  無 RPM 或推力實測')
        foot.setObjectName('hudCaption')
        foot.setWordWrap(True)
        root.addWidget(foot)
        self.demo_poll_scope = foot
        self.demo_poll_scope.setText('自動監控：第二頁僅讀電流；PC 控制／學習時保留安全監控 · 無 RPM 或推力實測')

        self._update_demo_view()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def _update_demo_view(self, *_):
        mode = self.demo_view_combo.currentData()
        self.demo_current_dial.setVisible(mode in ('both','dial'))
        self.demo_current_bar.setVisible(mode in ('both','bar'))
        # The dial shows a large right-hand number; prevent duplicate
        # digital values in mixed/dial modes, retain the label for bar-only.
        self.demo_actual.setVisible(mode == 'bar')
        self.demo_target.setVisible(True)

    def request_clear_faults(self):
        if not (self.connected and self.identity_verified) or self.motion_active or self.learning_requested:
            QMessageBox.warning(self,'無法清除','請先停止馬達／學習並確認設備連線。')
            return
        if self._foreground_pending: return
        resp=QMessageBox.question(self,'清除目前故障旗標',
            '將送出 UART 0x0F/02，僅請求清除目前故障旗標，不清除故障歷史次數。\n'
            '若尚未學習，0x20 位置回授旗標不會因此解除；其他未排除的故障也可能保留。\n'
            '請先確認馬達已停止、已排除故障原因。確定？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resp==QMessageBox.StandardButton.Yes:
            self.submit('error_clear')

    def request_learning_start(self):
        if not (self.connected and self.identity_verified and self.legacy_fw): return
        if self.learning_requested or self.motion_active or self.bench_uart_enabled:
            QMessageBox.warning(self, '不能開始學習', '請先停止推桿並關閉 UART MODE。')
            return
        if self._foreground_pending: return
        confirm = QMessageBox.warning(self, '開始自動行程學習',
            '這會讓推桿自動往返至機械行程端點，可能以較高 PWM 執行學習！\n'
            '不可用手或身體接觸移動結構；請先確認 Hall/POT、固定治具、獨立馬達斷電有效，'
            '且推桿全行程沒有夾壓風險。\n\n'
            'CI76 FW 0x0B01 沒有 UART 失聯停止保護。\n'
            '0x02 ACK 僅代表收到要求，約數秒後才進入學習，不代表學習成功。\n'
            '警告：舊韌體可能在 Hall/POT 未接線時誤判學習完成，請驗證實際行程。\n\n'
            '確認在內部安全測試台執行？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes: return
        if not self.auto_poll.isChecked(): self.auto_poll.setChecked(True)
        self.submit('learning_start')
        self.learning_requested = True
        self._render_motion_state()
        self.learn_feedback.setText('要求開始學習，等待 ACK…')

    def request_learning_abort(self):
        if not self.connected or not self.identity_verified: return
        self.demo_update_timer.stop()
        self.worker.submit('learning_abort')
        self.learn_feedback.setText('要求取消學習…請現場確認停止')

    def _set_demo_limit_display(self, amps):
        """Show MCU-confirmed value in Demo controls without scheduling a UART write."""
        ticks = max(self.demo_slider.minimum(),
                    min(self.demo_slider.maximum(), amps_to_ticks(amps)))
        self.demo_slider.blockSignals(True)
        self.demo_target_spin.blockSignals(True)
        try:
            self.demo_slider.setValue(ticks)
            self.demo_target_spin.setValue(ticks_to_amps(ticks))
            self.demo_target.setText(f'{ticks_to_amps(ticks):.2f} A')
            self.hud_limit_dial.setReading(ticks_to_amps(ticks))
        finally:
            self.demo_target_spin.blockSignals(False)
            self.demo_slider.blockSignals(False)

    def _on_tab_changed(self, index):
        """Both pages use ONE global auto-monitor checkbox and period setting.

        Cancel only the unsent Demo slider target on leaving Demo; never
        change the user's global monitoring preference or enqueue stale writes.
        """
        if self.tabs.widget(index) != self.demo_tab:
            if self._demo_pending_value is not None:
                self.demo_update_timer.stop()
                self._demo_pending_value = None
                self._demo_last_sent = None
                self.demo_write_status.setText(
                    '切回參數頁：未送出的 Demo 目標已取消；已送出的寫入仍需 MCU 讀回確認')
                if not self._demo_write_inflight and 'current_limit' in self.last_values:
                    self._set_demo_limit_display(self.last_values['current_limit'])
        elif self._demo_pending_value is None and not self._demo_write_inflight:
            if 'current_limit' in self.last_values:
                self._set_demo_limit_display(self.last_values['current_limit'])
        self._sync_demo_monitor()

    def _demo_spin_to_slider(self, amps):
        self.demo_slider.setValue(amps_to_ticks(amps))

    def _on_demo_slider_changed(self, raw):
        value = ticks_to_amps(raw)
        self.demo_target.setText(f'{value:.2f} A')
        self.hud_limit_dial.setReading(value)
        self.demo_target_spin.blockSignals(True)
        self.demo_target_spin.setValue(value)
        self.demo_target_spin.blockSignals(False)
        # Crucial: do NOT touch self.fields['current_limit'] here.
        # The first page shows MCU-confirmed values only after a successful readback.
        self._demo_pending_value = value
        if self.connected and self.identity_verified and '電流' in self.group_read_ok and not self.learning_requested:
            self.demo_write_status.setText(f'Demo 目標 {value:.2f} A；等待 UART 寫入和讀回確認…')
            if not self.demo_update_timer.isActive():
                self.demo_update_timer.start()
        else:
            self.demo_write_status.setText('只修改本頁輸入；請先連線並讀取電流參數，才會自動寫入')

    def _demo_apply_now(self):
        if not (self.connected and self.identity_verified and '電流' in self.group_read_ok):
            self.demo_write_status.setText('請先連線並讀取全部參數')
            return
        self._demo_pending_value = ticks_to_amps(self.demo_slider.value())
        self._demo_last_sent = None
        self.demo_update_timer.start()
        self._flush_demo_limit()

    def _flush_demo_limit(self):
        value = self._demo_pending_value
        if not (self.connected and self.identity_verified) or self._link_stale or self.learning_requested or self.interlock_fault:
            self.demo_update_timer.stop()
            return
        if value is None or self._demo_write_inflight or self._foreground_pending:
            return
        if not within_slider_range(value):
            self.demo_update_timer.stop()
            self.demo_write_status.setText('超出 0～8 A 快捷滑桿範圍，拒絕寫入')
            return
        if value == self._demo_last_sent and self.demo_verified_limit is not None:
            self.demo_update_timer.stop()
            return
        if '電流' not in self.group_read_ok:
            self.demo_update_timer.stop()
            self.demo_write_status.setText('請先按「讀取全部參數」，確認原始電流參數')
            return
        self._demo_write_inflight = True
        self._demo_last_sent = value
        self.demo_write_status.setText(f'設定 {value:.2f} A → UART 0x06 寫入中，等待 0x19 讀回…')
        self._sync_demo_monitor()
        self.demo_sample_rate.setText('電流實際刷新：寫入步驟間持續監控' if self.auto_poll.isChecked()
                                      else '電流實際刷新：自動監控已關閉')
        self.submit('demo_limit', value)

    def request_demo_restore(self):
        if not (self.connected and self.identity_verified) or self.motion_active or self.learning_requested:
            QMessageBox.warning(self, '不能還原', '請先停止動作／學習。')
            return
        self.demo_update_timer.stop()
        self._demo_pending_value = None
        self.submit('demo_restore')

    def request_motor_time_reset(self):
        if not self.connected or not self.identity_verified or self.motion_active:
            QMessageBox.warning(self, '無法歸零', '需先確認 CI76 設備，且推桿完全停止。')
            return
        answer = QMessageBox.warning(self, '重置累積運轉時間',
            '此操作會要求 MCU 將累積運轉時間設為 0 秒。\n'
            '讀回成功只代表目前 RAM 已歸零；斷電後是否維持，需要實際驗證。\n\n確定執行？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.submit('motor_time_reset')

    def toggle_bench_uart_mode(self):
        if not (self.connected and self.identity_verified and self.legacy_fw):
            QMessageBox.warning(self, 'UART MODE 不適用',
                '此手動按鍵僅支援已識別的舊版 CI76 0x0B01。')
            return
        if self.motion_active:
            QMessageBox.information(self, '先停止', '請先按 STOP 並確認完全停止，再切換 UART MODE。')
            self.request_stop()
            return
        if self._foreground_pending or self.stop_pending:
            return
        enabling = not self.bench_uart_enabled
        if enabling:
            confirm = QMessageBox.warning(self, '內部測試：開啟 UART MODE',
                '目前 FW 0x0B01 沒有 UART 失聯自動停止保護。\n\n'
                '必須親自確認：\n'
                '• 使用安全測試台，推桿完成行程學習，無夾傷風險。\n'
                '• 已備有獨立、可立即切斷馬達驅動的實體停止方式。\n'
                '• I1 不是緊急停止；USB 拔除或 PC 當機後，推桿可能繼續運轉。\n'
                '• 每次控制最長 2 秒是 PC 端軟體限制，無法作為失聯保護。\n\n'
                '你已確認上述條件並同意只供內部測試嗎？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if confirm != QMessageBox.StandardButton.Yes:
                return
        self.submit('bench_uart_mode', enabling)

    def request_motion(self, direction: str):
        if self.learning_requested:
            QMessageBox.warning(self, '正在學習', '先取消學習並確認停止，才能手控推桿')
            return
        if self.motion_active == direction:
            self.request_stop()
            return
        if self._foreground_pending or self.stop_pending:
            return
        bench = self.legacy_fw and self.bench_uart_enabled
        safe = self.motion_supported
        if not (self.connected and self.identity_verified and (bench or safe)):
            QMessageBox.warning(self, '無法控制馬達',
                'FW 0x0B01：請先啟用 UART MODE（內部限時測試）。\n'
                '尚未驗證硬體獨立停止之前，不能以 I1 代替緊急停止。')
            return
        if self.tabs.currentWidget() == self.demo_tab:
            if self.demo_verified_limit is None or not within_slider_range(self.demo_verified_limit):
                QMessageBox.warning(self, '展示限流未設定',
                    '請先在展示分頁確認 MCU 限流已讀回一致（0～8 A），'
                    '再啟動短時伸縮。未設定時不會假設原來的限流符合展示安全範圍。')
                return
        if self.motor_speed.value() == 0:
            QMessageBox.warning(self,'速度為 0%','0% 代表停止，不會啟動馬達')
            return
        if not self.motion_approved:
            notice = ('舊 FW 0x0B01 無失聯自停保護！\n'
                '本次按一下啟動、再按一下停止，最長只允許 2 秒（PC 端）。\n'
                '請確認獨立實體斷電有效，附近無夾壓、可見全行程、已完成學習。\n'
                '任何串口異常立即用獨立硬體停止，不依賴 I1、Esc 或 PC STOP。' if bench else
                '請確認推桿已完成行程學習、故障為零，並備妥獨立硬體停止。')
            response = QMessageBox.warning(self, '首次啟用 PC 推桿控制', notice,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if response != QMessageBox.StandardButton.Yes:
                return
            self.motion_approved = True
        # Keep 0x12/0x13/0x17 health polling active while the bench jog runs.
        if bench and not self.auto_poll.isChecked():
            self.auto_poll.setChecked(True)
        self.submit('bench_start' if bench else 'motor_start',
                    (direction, self.motor_speed.value()))

    def request_stop(self):
        if self.learning_requested:
            self.request_learning_abort()
            return
        # STOP is always available to an identified, connected CI76, even if
        # this GUI currently believes no motion is active (e.g. after app restart).
        if not self.connected or not self.identity_verified or self.stop_pending:
            return
        self.stop_pending = True
        self.pending += 1
        self.worker.submit('motor_stop')
        self.stop_btn.setEnabled(False)
        self.motor_feedback.setText('停止命令已排入優先佇列，等待 MCU 回覆…')

    def _render_motion_state(self):
        bench = self.legacy_fw and self.bench_uart_enabled
        available = self.connected and self.identity_verified and not self._link_stale and (self.motion_supported or bench)
        self.extend_btn.setEnabled(available and not self.stop_pending)
        self.retract_btn.setEnabled(available and not self.stop_pending)
        self.motor_speed.setEnabled(available and not self.motion_active)
        self.motor_speed.setMaximum(100)
        self.stop_btn.setEnabled(self.connected and self.identity_verified)
        self.auto_poll.setEnabled(self.connected and self.identity_verified and not bool(self.motion_active) and not self.learning_requested)
        self.uart_mode_btn.setEnabled(self.connected and self.identity_verified and self.legacy_fw
                                      and not bool(self.motion_active) and not self.stop_pending)
        self.uart_mode_btn.setText('UART MODE：ON' if self.bench_uart_enabled else 'UART MODE：OFF')
        if self.motion_active == 'extend':
            self.extend_btn.setText('■ 停止伸出')
            self.retract_btn.setText('◀ 改為縮回')
            self.motor_feedback.setText('● 伸出中 · 舊 FW 最長2秒' if bench else '● 伸出中')
        elif self.motion_active == 'retract':
            self.extend_btn.setText('改為伸出 ▶')
            self.retract_btn.setText('■ 停止縮回')
            self.motor_feedback.setText('● 縮回中 · 舊 FW 最長2秒' if bench else '● 縮回中')
        else:
            self.extend_btn.setText('伸出 ▶')
            self.retract_btn.setText('◀ 縮回')
            self.motor_feedback.setText('UART 已開 · 最長2秒' if bench else
                ('請先開啟 UART MODE' if self.legacy_fw else
                 ('待命：可操作' if available else '韌體未確認失聯停止')))
        self.time_reset_btn.setEnabled(self.connected and self.identity_verified and not self.motion_active)
        self.diagnostic_btn.setEnabled(self.connected and not self.motion_active and not self.learning_requested)
        self.learn_btn.setEnabled(self.connected and self.identity_verified and self.legacy_fw
                                  and not self.interlock_fault and not self.learning_requested and not self.bench_uart_enabled and not self.motion_active)
        self.learn_abort_btn.setEnabled(self.connected and self.identity_verified and self.learning_requested)
        self.demo_restore_btn.setEnabled(self.connected and self.identity_verified and self.demo_dirty
                                          and not self.motion_active and not self.learning_requested)
        can_demo_write = (self.connected and self.identity_verified
                          and not self._link_stale and '電流' in self.group_read_ok and not self.learning_requested)
        self.demo_slider.setEnabled(can_demo_write)
        self.demo_target_spin.setEnabled(can_demo_write)
        self.demo_apply_btn.setEnabled(can_demo_write and not self._demo_write_inflight)
        self.extend_btn.setEnabled(self.extend_btn.isEnabled() and not self.learning_requested and not self.interlock_fault)
        self.retract_btn.setEnabled(self.retract_btn.isEnabled() and not self.learning_requested and not self.interlock_fault)
        self.uart_mode_btn.setEnabled(self.uart_mode_btn.isEnabled() and not self.learning_requested and not self.interlock_fault)
        self.clear_fault_btn.setEnabled(self.connected and self.identity_verified and not self.learning_requested and not self.motion_active and not self._foreground_pending)

    def toggle_log(self, expanded: bool):
        self.console.setVisible(expanded)
        self.log_toggle.setText('收合紀錄' if expanded else '展開紀錄')
        self.log_title.setText('UART TX / RX 通訊紀錄' if expanded
                               else 'UART TX / RX 通訊紀錄（收合）')

    def _clear_log(self):
        self.console.clear()

    def read_status_once(self):
        self.submit('monitor', {'auto': False, 'log_frames': True})

    def poll_once(self):
        # One global monitor. Demo uses current-priority scheduling; no
        # duplicate checkbox, extra polling thread or queued monitor burst.
        if self.connected and self.auto_poll.isChecked() and self.pending == 0:
            fast_demo = self.tabs.currentWidget() is self.demo_tab
            current_only = fast_demo and not (
                self.motion_active or self.learning_requested or self.bench_uart_enabled
                or self.stop_pending or self.interlock_fault)
            self._set_poll_scope(current_only)
            self.submit('monitor', {
                'auto': True, 'log_frames': self.poll_trace.isChecked(),
                'fast_demo': fast_demo, 'current_only': current_only,
            })

    def _sync_demo_monitor(self):
        self.worker.configure_demo_monitor({
            'auto': self.connected and self.auto_poll.isChecked() and not self._link_stale,
            'fast_demo': self.tabs.currentWidget() is self.demo_tab,
            'current_only': not (self.motion_active or self.learning_requested
                                 or self.bench_uart_enabled or self.stop_pending or self.interlock_fault),
            'period_ms': self.poll_period.currentData(),
            'log_frames': self.poll_trace.isChecked(),
        })

    def _set_poll_scope(self, current_only):
        if current_only:
            self.demo_poll_scope.setText('僅更新實際電流；位置／狀態／故障／運轉時間暫停更新 · 無 RPM 或推力實測')
        else:
            self.demo_poll_scope.setText('完整／安全監控；電流優先，其他資料依原排程更新 · 無 RPM 或推力實測')
        if current_only == self._background_paused:
            return
        self._background_paused = current_only
        if not current_only:
            # Keep paused values UNKNOWN until each read actually succeeds.
            return
        for key in list(self.latest_monitor):
            if key != 'current':
                del self.latest_monitor[key]
        self._gauge_unavailable('position', '第二頁僅讀電流；位置暫停更新')
        for key in ('motor', 'uart', 'sensor', 'errors'):
            self.live[key].setText('—（暫停更新）')
        self.motor_time_label.setText('—（暫停更新）')
        self.hud_motor_state.setText('PAUSED / UNKNOWN')
        self.hud_sensor.setText('PAUSED / UNKNOWN')
        self._reset_error_flags('暫停更新（僅電流）')
        self.hud_fault.setText('PAUSED / UNKNOWN')

    def poll_toggled(self, checked):
        self._sync_demo_monitor()
        self._last_monitor_ts = None
        self._last_demo_current_ts = None
        if checked and self.connected and not self._foreground_pending:
            self.timer.start(self.poll_period.currentData())
            self.poll_once()
        else:
            self.timer.stop()
        if not checked:
            self.poll_rate.setText('電流實際：—')
            self.demo_sample_rate.setText('電流實際刷新：自動監控已關閉')
        else:
            self.demo_sample_rate.setText('電流實際刷新：等待資料…')

    def poll_period_changed(self):
        self._sync_demo_monitor()
        if self.auto_poll.isChecked() and self.timer.isActive():
            self.timer.setInterval(self.poll_period.currentData())
            self._last_monitor_ts = None
            self._last_demo_current_ts = None

    def _resume_poll(self):
        if self.connected and not self._link_stale and self.auto_poll.isChecked() and not self._foreground_pending:
            self.timer.start(self.poll_period.currentData())

    def _update_gauge(self, key, value):
        bar, maximum, unit = self.gauge_bars[key]
        number = float(value)
        bar.setValue(gauge_value(number, maximum))
        precision = 2 if key == 'current' else 1
        self.live[key].setText(f'{number:.{precision}f} {unit}')
        self.live[key].setStyleSheet('color:#B2F0E9;font-size:12pt;font-weight:700')

    def _gauge_unavailable(self, key, why='查詢失敗'):
        bar, maximum, unit = self.gauge_bars[key]
        bar.setValue(0)
        self.live[key].setText('— ' + unit)
        self.live[key].setToolTip(why)
        self.live[key].setStyleSheet('color:#E9A695;font-size:12pt;font-weight:700')

    @staticmethod
    def _flag_style(state):
        styles = {
            'unknown': 'background:#1B293C;color:#94A9BC;border:1px solid #2B3D55;',
            'clear': 'background:#141E2D;color:#2DCE9B;border:1px solid #2B3D55;',
            'power': 'background:#141E2D;color:#FF6375;border:1px solid #FF6375;',
            'control': 'background:#141E2D;color:#FFBD59;border:1px solid #FFBD59;',
        }
        return styles[state] + 'border-radius:4px;padding:2px;font-size:8pt;'

    def _reset_error_flags(self, reason='尚未查詢'):
        self.error_overview.setText(reason)
        self.error_overview.setStyleSheet('color:#D8AE84;font-weight:600;')
        self.last_error_bits = None
        self.hud_fault.setText('NOT READ')
        for definition in FLAGS:
            item = self.flag_labels[definition.key]
            item.setText('— ' + definition.label)
            item.setStyleSheet(self._flag_style('unknown'))

    def _render_error_flags(self, snapshot):
        active = set(snapshot['active'])
        unknown = snapshot['reserved_bits']
        for definition in FLAGS:
            item = self.flag_labels[definition.key]
            if definition.key in active:
                item.setText('● ' + definition.label)
                item.setStyleSheet(self._flag_style(definition.category))
            else:
                item.setText('✓ ' + definition.label)
                item.setStyleSheet(self._flag_style('clear'))
        if unknown:
            self.error_overview.setText(f'未知旗標 0x{unknown:02X}')
            self.error_overview.setStyleSheet('color:#F09A94;font-weight:700;')
        elif active:
            self.error_overview.setText(f'異常 {len(active)} 項')
            self.error_overview.setStyleSheet('color:#F09A94;font-weight:700;')
        else:
            self.error_overview.setText('目前無異常')
            self.error_overview.setStyleSheet('color:#75C7AA;font-weight:700;')
        bits = (snapshot['byte0'], snapshot['byte1'])
        self.hud_fault.setText(f'0x{bits[0]:02X} / 0x{bits[1]:02X}' + ('  FAULT' if active or unknown else '  CLEAR'))
        if self.last_error_bits != bits:
            # Log changed flags. Also log an existing alarm on the very first poll.
            if self.last_error_bits is not None or active or unknown:
                name_map = {item.key: item.label for item in FLAGS}
                names = '、'.join(name_map[k] for k in snapshot['active']) if active else '已清除'
                if unknown:
                    names += f'、未知位元 0x{unknown:02X}'
                self.log(f'FAULT 旗標變化：{bits[0]:02X} {bits[1]:02X}（{names}）')
            self.last_error_bits = bits

    def _create_group(self, group):
        g = QGroupBox(group + '參數')
        layout = QVBoxLayout(g)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        fields = QFormLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setHorizontalSpacing(6)
        fields.setVerticalSpacing(2)
        for key in GROUPS[group][3]:
            label, unit, scale, _lo, _hi = FIELDS[key]
            edit = QSpinBox() if scale == 1 else QDoubleSpinBox()
            edit.setObjectName('compactEditor')
            lower, upper, decimals, step = field_editor_spec(key)
            if isinstance(edit, QDoubleSpinBox):
                edit.setDecimals(decimals)
            # Per-field display limits: especially the 0–100% software stroke.
            # Regenerative voltage preserves visibility of old 52/51V defaults,
            # but writing above protocol limits remains forbidden by build_write.
            edit.setRange(lower, upper)
            edit.setSingleStep(step)
            if key in ('pos_max', 'pos_min'):
                edit.setToolTip('軟體極限：0～100%，1% 單位。韌體對 0.1% 輸入會截成整數%。')
            edit.setSuffix(' ' + unit)
            edit.setEnabled(False)
            edit.setMinimumWidth(97)
            self.fields[key] = edit
            if group == '電流':
                edit.valueChanged.connect(self._mark_current_draft)
            fields.addRow(label, edit)
        layout.addLayout(fields)
        if group == '電流':
            slider_section = QVBoxLayout()
            slider_section.setSpacing(2)
            slider_head = QHBoxLayout()
            slider_head.addWidget(QLabel('本頁限流快捷滑桿（按寫入後才生效）'))
            self.limit_slider_info = QLabel('0.00–8.00 A')
            self.limit_slider_info.setStyleSheet('color:#91B8C5;font-size:8pt;')
            slider_head.addStretch()
            slider_head.addWidget(self.limit_slider_info)
            slider_section.addLayout(slider_head)
            self.limit_slider = QSlider(Qt.Orientation.Horizontal)
            self.limit_slider.setRange(amps_to_ticks(CURRENT_SLIDER_MIN_A), amps_to_ticks(CURRENT_SLIDER_MAX_A))
            self.limit_slider.setSingleStep(5)
            self.limit_slider.setPageStep(25)
            self.limit_slider.setEnabled(False)
            self.limit_slider.valueChanged.connect(self._slider_to_current)
            self.fields['current_limit'].valueChanged.connect(self._current_to_slider)
            slider_section.addWidget(self.limit_slider)
            layout.addLayout(slider_section)
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        r = QPushButton('讀取')
        r.clicked.connect(lambda _checked=False, name=group: self.submit('readgroup', name))
        w = QPushButton('寫入（暫存）')
        w.clicked.connect(lambda _checked=False, name=group: self.write_group(name))
        self.write_buttons[group] = w
        w.setEnabled(False)
        buttons.addWidget(r)
        buttons.addWidget(w)
        layout.addLayout(buttons)
        return g

    def _slider_to_current(self, ticks):
        self.fields['current_limit'].setValue(ticks_to_amps(ticks))

    def _current_to_slider(self, amps):
        """Page 1 slider follows Page 1 numeric input only; no Demo write."""
        ticks = max(self.limit_slider.minimum(),
                    min(self.limit_slider.maximum(), amps_to_ticks(amps)))
        self.limit_slider.blockSignals(True)
        self.limit_slider.setValue(ticks)
        self.limit_slider.blockSignals(False)
        if amps > CURRENT_SLIDER_MAX_A:
            self.limit_slider_info.setText(f'目前 {amps:.2f} A（滑桿上限 {CURRENT_SLIDER_MAX_A:.2f} A）')
            self.limit_slider_info.setStyleSheet('color:#E4B476;font-size:8pt;')
        else:
            self.limit_slider_info.setText(f'本頁輸入：{amps:.2f} A（按下寫入才套用）')
            self.limit_slider_info.setStyleSheet('color:#91B8C5;font-size:8pt;')

    def _update_sensor_display(self, mode: int | None, *, set_choice=False):
        self.sensor_mode_current = mode if mode in SENSOR_MODE_LABELS else None
        self.sensor_mode_ready = self.sensor_mode_current is not None
        self.sensor_current_label.setText(SENSOR_MODE_LABELS.get(mode, '—（未知）'))
        self.hud_sensor.setText(SENSOR_MODE_LABELS.get(mode, 'UNKNOWN'))
        if set_choice and self.sensor_mode_ready:
            self.sensor_select.blockSignals(True)
            self.sensor_select.setCurrentIndex(self.sensor_select.findData(mode))
            self.sensor_select.blockSignals(False)
        self._update_sensor_button()

    def _update_sensor_button(self, *_):
        ready = (self.connected and self.identity_verified and self.sensor_mode_ready
                 and self.sensor_mode_current != self.sensor_select.currentData())
        self.sensor_select.setEnabled(self.connected and self.identity_verified and self.sensor_mode_ready)
        self.sensor_apply_btn.setEnabled(ready)

    def apply_sensor_mode(self):
        mode = self.sensor_select.currentData()
        if not (self.connected and self.identity_verified and self.sensor_mode_ready
                and mode in SENSOR_MODE_LABELS and mode != self.sensor_mode_current):
            return
        choice = QMessageBox.warning(
            self, '感測器模式變更（風險提醒）',
            f'目前：{SENSOR_MODE_LABELS[self.sensor_mode_current]}\n'
            f'要切換成：{SENSOR_MODE_LABELS[mode]}？\n\n'
            '切換將清除原行程學習資訊，韌體會設定位置回授異常，需重新學習行程。\n'
            '請確認馬達、推桿完全停止，並在安全測試台上操作。\n'
            '此工具會再次讀取停止狀態，非停止狀態將拒絕寫入。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if choice == QMessageBox.StandardButton.Yes:
            self.submit('sensor_write', mode)

    def refresh_ports(self):
        prev = self.ports.currentData() if hasattr(self, 'ports') else None
        self.ports.clear()
        self._port_inventory = [PortIdentity.from_port(p) for p in list_ports.comports()]
        for p in self._port_inventory:
            label = f'{p.device} · {p.description}'
            if p.serial_number:
                label += f' · USB {p.serial_number}'
            self.ports.addItem(label, p.device)
        if not self.ports.count():
            self.ports.addItem('沒有 USB-to-UART 裝置', '')
        pos = self.ports.findData(prev)
        if pos >= 0:
            self.ports.setCurrentIndex(pos)

    def _connection_state(self, state, detail=''):
        self.connection_label.setText(state)
        self.connection_label.setToolTip(detail or state)
        self.hud_link.setText(state)
        color = '#2DCE9B' if state == 'CI76 VERIFIED' else '#FFBD59'
        self.connection_label.setStyleSheet(f'color:{color};font-weight:700')
        if detail:
            self.statusBar().showMessage(detail)

    def _startup_connection(self):
        if self._startup_attempted:
            return
        self._startup_attempted = True
        match, reason = match_port(self.preferences.last_port(), self._port_inventory)
        if match is None:
            self._connection_state('DISCONNECTED', reason)
            return
        self.ports.setCurrentIndex(self.ports.findData(match.device))
        if self.preferences.auto_connect and not self._user_disconnected:
            self._begin_connection()

    def _begin_connection(self):
        if self.connected or self._connection_pending:
            return
        port = self.ports.currentData()
        if not port:
            self._connection_state('DISCONNECTED', '沒有可連線的 COM Port；請掃描或手動選取')
            return
        self._connecting_port = next((p for p in self._port_inventory if p.device == port), None)
        self._connection_failure = None
        self._connection_pending = True
        self.ports.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self._connection_state('CONNECTING', f'正在開啟 {port}；尚未驗證設備')
        self.worker.submit('connect', port)

    def _reject_connection(self, state, reason):
        # No motion/mode/parameter action is admitted before identity succeeds.
        # Closing this newly opened, unverified connection is read-only.
        self._connection_failure = (state, reason)
        self.identity_verified = False
        self.set_connected(False)
        self._connection_pending = True
        self.connect_btn.setEnabled(False)
        self.ports.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self._connection_state(state, reason)
        self.worker.submit('disconnect')

    def set_connected(self, state):
        self.connected = state
        if not state:
            self.identity_verified = False
        self._connection_state('CONNECTED—VERIFYING' if state else 'DISCONNECTED')
        if not state:
            self.hud_motor_state.setText('NO DATA')
        self.connect_btn.setText('斷線' if state else '連線')
        self.connect_btn.setEnabled(True)
        self.ports.setEnabled(not state)
        self.refresh_btn.setEnabled(not state)
        for button in (self.identity_btn, self.readall_btn, self.monitor_btn):
            button.setEnabled(state and self.identity_verified)
        self.auto_poll.setEnabled(state and self.identity_verified)
        self.poll_period.setEnabled(state and self.identity_verified)
        self.motion_active = self.motion_active if state else None
        self.motion_supported = self.motion_supported if state else False
        if not state:
            self.timer.stop()
            self._background_paused = False
            self._current_only_failures = 0
            self.latest_monitor.clear()
            self.hud_sensor.setText('UNKNOWN')
            self.demo_actual.setText('— A')
            self.demo_current_bar.setValue(0)
            self.demo_current_dial.setReading(None)
            self.hud_limit_dial.setReading(None)
            self.fw_label.setText('—')
            self.device_label.setText('—')
            self.header_firmware.setText('FW —')
            self._last_demo_current_ts = None
            self.demo_sample_rate.setText('電流實際刷新：—')
            self.demo_update_timer.stop()
            self._demo_pending_value = None
            self._demo_last_sent = None
            self._demo_write_inflight = False
            self.demo_applied.setText('MCU 已確認：— A')
            self.demo_dirty = False
            self.demo_verified_limit = None
            self.learning_requested = False
            self.learning_seen = False
            self.interlock_fault = False
            self.stop_pending = False
            self.legacy_fw = False
            self.bench_uart_enabled = False
            self.motion_approved = False
        self._render_motion_state()
        self._update_sensor_button()
        self.limit_slider.setEnabled(state and '電流' in self.group_read_ok)
        for group, keys in GROUPS.items():
            editable = state and group in self.group_read_ok
            for key in keys[3]:
                self.fields[key].setEnabled(editable)
            self.write_buttons[group].setEnabled(editable and self.identity_verified)
        if not state:
            self.identity_verified = False
            self.group_read_ok.clear()
            self.sensor_mode_current = None
            self.sensor_mode_ready = False
            self.sensor_current_label.setText('—（未連線）')
            self.motor_time_label.setText('—（未連線）')
            self.auto_poll.setChecked(False)
            self._last_monitor_ts = None
            self._foreground_pending = False
            self.pending = 0
            self._reset_error_flags('尚未查詢')
            for group in GROUPS:
                self.write_buttons[group].setEnabled(False)
                for key in GROUPS[group][3]:
                    self.fields[key].setEnabled(False)
            for k in self.live:
                if k in self.gauge_bars:
                    self._gauge_unavailable(k, '尚未查詢')
                else:
                    self.live[k].setText('—（尚未查詢）')

    def toggle_connection(self):
        if self._connection_pending:
            return
        if self.connected:
            if self.learning_requested:
                self.request_learning_abort()
                QMessageBox.warning(self, '正在學習', '已要求取消，請確認推桿完全停止再斷線。')
                return
            if self.demo_dirty:
                self.request_demo_restore()
                QMessageBox.information(self, '先還原展示限流', '已要求還原限流，請讀回確認後再斷線。')
                return
            if self.motion_active:
                QMessageBox.information(self, '請先停止推桿', '請先按「停止」並確認完全停止，才能正常中斷連線。')
                self.request_stop()
                return
            if self.bench_uart_enabled:
                QMessageBox.warning(self, '請先關閉 UART MODE',
                    '先按「UART MODE：ON」關閉控制模式，確認讀回 OFF 後再斷線。')
                return
            self._user_disconnected = True
            self.submit('disconnect')
        else:
            self._begin_connection()

    def submit(self, action, payload=None):
        if not self.connected:
            self.statusBar().showMessage('尚未連線')
            return
        if not self.identity_verified and action not in ('identity', 'disconnect'):
            self.statusBar().showMessage('設備驗證尚未成功；禁止設定與控制')
            return
        if self._link_stale and action not in ('identity','disconnect','monitor','motor_stop','learning_abort'):
            self.statusBar().showMessage('連線資料已失效；請先讀取設備資訊重新驗證。若有動作請先用獨立硬體停止。')
            return
        if self.interlock_fault and action not in ('monitor','disconnect'):
            self.statusBar().showMessage('上一次學習／停止未確認；請實體確認停止並重新連線')
            return
        if self.learning_requested and action not in ('monitor','learning_abort'):
            self.statusBar().showMessage('正在行程學習，請先取消並確認停妥')
            return
        if self.motion_active and action not in ('monitor','motor_start','bench_start','motor_stop','demo_limit'):
            self.statusBar().showMessage('推桿控制中，請先停止再執行設定或診斷操作')
            return
        if self.bench_uart_enabled and action in ('writegroup', 'sensor_write', 'motor_time_reset', 'diagnostics', 'learning_start'):
            self.statusBar().showMessage('請先關閉 UART MODE，再修改參數或擷取診斷')
            return
        if action == 'monitor':
            if self.pending:
                return
        elif self._foreground_pending:
            self.statusBar().showMessage('設定操作尚未完成，請稍後')
            return
        else:
            # Pause automatic polling for user-triggered parameter actions;
            # if one monitor transaction is running, put this behind it.
            self._foreground_pending = True
            self.timer.stop()
        self.pending += 1
        self.worker.submit(action, payload)

    def write_group(self, group):
        if group == '電流' and self._demo_write_inflight:
            QMessageBox.information(self, '請稍候', 'Demo 限流寫入正在等待 MCU 讀回，完成後再用第一頁覆蓋。')
            return
        if not (self.connected and self.identity_verified and group in self.group_read_ok):
            QMessageBox.warning(self, '尚未準備', '須先確認 CI76 設備碼並成功讀取該組參數')
            return
        vals = {k: self.fields[k].value() for k in GROUPS[group][3]}
        try:
            build_write(group, vals)
        except (ProtocolError, ValueError) as exc:
            QMessageBox.warning(self, '參數檢查', str(exc))
            return
        details = '\n'.join(f'{FIELDS[k][0]}：{vals[k]} {FIELDS[k][1]}' for k in vals)
        choice = QMessageBox.question(self, '確認寫入 CI76',
            f'確定寫入「{group}」的暫存設定嗎？\n\n{details}\n\n'
            '會影響馬達與保護限制；需讀回確認，斷電不保證保存。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if choice == QMessageBox.StandardButton.Yes:
            # Page 1 is now the chosen writer; discard only UNSENT Demo target.
            # Worker will clear the old Demo current snapshot after successful readback.
            if group == '電流':
                self.demo_update_timer.stop()
                self._demo_pending_value = None
                self._demo_last_sent = None
                self.demo_write_status.setText('由第一頁寫入電流參數中；請等待 MCU 讀回確認')
            self.submit('writegroup', (group, vals))

    def _mark_current_draft(self, *_):
        if not self._applying_group:
            self._current_draft_dirty = True

    def _apply_group(self, group, items, *, preserve_draft=False):
        keep_draft = group == '電流' and preserve_draft and self._current_draft_dirty
        self._applying_group = True
        for key, val in items.items():
            if not keep_draft:
                self.fields[key].setValue(val)
            self.last_values[key] = val
        self._applying_group = False
        if group == '電流' and not keep_draft:
            self._current_draft_dirty = False
        self.group_read_ok.add(group)
        if group == '電流':
            self.limit_slider_info.setText(
                f'MCU {items["current_limit"]:.2f} A / 本頁草稿保留' if keep_draft
                else f'MCU 讀回：{items["current_limit"]:.2f} A')
            self.limit_slider_info.setStyleSheet('color:#76D4C9;font-size:8pt;')
            self.limit_slider.setEnabled(self.connected)
            self.demo_slider.setEnabled(self.connected and self.identity_verified and not self.learning_requested)
            self.demo_target_spin.setEnabled(self.demo_slider.isEnabled())
            self.demo_apply_btn.setEnabled(self.demo_slider.isEnabled())
            self.demo_applied.setText(f'MCU 已確認：{items["current_limit"]:.2f} A')
            if self._demo_pending_value is None and not self._demo_write_inflight:
                self._set_demo_limit_display(items['current_limit'])
                self.demo_verified_limit = (items['current_limit'] if within_slider_range(items['current_limit']) else None)
                self.demo_write_status.setText(
                    f'MCU 限流 {items["current_limit"]:.2f} A；Demo 滑桿僅於操作時自動寫入')
        for key in GROUPS[group][3]:
            self.fields[key].setEnabled(self.connected)
        self.write_buttons[group].setEnabled(self.connected and self.identity_verified)

    def on_success(self, action, data):
        # Ignore delayed telemetry signals after a disconnect, never revive stale values.
        if not self.connected and action in ('monitor_item', 'monitor_problem', 'monitor', 'monitor_inline'):
            return
        if action not in ('connect','disconnect','readgroup_part','group_problem',
                          'monitor_item','monitor_problem', 'monitor_inline', 'motor_lost', 'motor_autostop',
                          'learning_stage', 'learning_result', 'learning_abort'):
            self.pending = max(0, self.pending - 1)
        if action == 'connect':
            self.identity_verified = False
            self.group_read_ok.clear()
            self.set_connected(True)
            self._connection_state('CONNECTED—VERIFYING', 'COM 已開啟，正在唯讀查詢 CI76 Device Code')
            self.connect_btn.setEnabled(False)
            self.statusBar().showMessage('已連接 COM，讀取設備資訊中…')
            self.submit('identity')
        elif action == 'disconnect':
            self._connection_pending = False
            self.pending = 0
            self.set_connected(False)
            self.statusBar().showMessage('已斷線')
            if self._connection_failure:
                self._connection_state(*self._connection_failure)
        elif action == 'identity':
            if not self.connected:
                return
            if data['device'] != '0x0B01':
                self._reject_connection('IDENTITY MISMATCH',
                    f'設備代碼 {data["device"]} 不符 CI76 0x0B01；已要求關閉 COM，未寫入任何參數')
                return
            self._connection_pending = False
            self._link_stale = False
            self.fw_label.setText(data['version'])
            self.header_firmware.setText('FW ' + data['version'])
            self.device_label.setText(data['device'])
            self.identity_verified = (data['device'] == '0x0B01')
            self.preferences.remember_verified(self._connecting_port, data['device'])
            self._connection_state('CI76 VERIFIED', '已確認 CI76 Device Code 0x0B01；尚未寫入任何參數')
            self.connect_btn.setEnabled(True)
            for button in (self.identity_btn, self.readall_btn, self.monitor_btn,
                           self.auto_poll, self.poll_period):
                button.setEnabled(True)
            self.motion_supported = firmware_motion_supported(data['version'], data['device'])
            self.legacy_fw = data['version'] == '0x0B01' and data['device'] == '0x0B01'
            self.bench_uart_enabled = False
            self.motion_approved = False
            self._render_motion_state()
            try:
                self.event_store.append('device_identity', **data)
            except OSError as exc:
                self.statusBar().showMessage('Log 寫入失敗：' + str(exc))
            self._update_sensor_display(data.get('sensor_mode'), set_choice=not self.local_profile_loaded)
            if data.get('motor_seconds') is not None:
                secs = data['motor_seconds']
                self.motor_time_label.setText(format_motor_seconds(secs))
                self.motor_time_label.setToolTip(f'原始秒數：{secs}')
            for group in GROUPS:
                self.write_buttons[group].setEnabled(self.identity_verified and group in self.group_read_ok)
            if self.identity_verified:
                self.statusBar().showMessage('已確認 CI76 (0x0B01)，可讀取全部參數')
            else:
                self.statusBar().showMessage('設備代碼不符：禁止寫入參數')
                QMessageBox.warning(self, '設備代碼不符',
                    '只允許對 Device Code 0x0B01 的 CI76 寫入；其餘裝置僅可讀取')
        elif action in ('readgroup','readgroup_part'):
            group, values = data
            self._apply_group(group, values)
            self.log(f'INFO  已讀取「{group}」參數')
        elif action == 'group_problem':
            group, why = data
            self.log(f'WARN  讀取「{group}」失敗：{why}')
        elif action == 'readall':
            text = f"全部參數：成功 {len(data['ok'])} 組；失敗 {len(data['failed'])} 組"
            self.statusBar().showMessage(text)
            self.log('INFO  ' + text)
            if data['failed']:
                QMessageBox.warning(self, '部分參數讀取失敗', text + '\n' +
                                    '\n'.join(f'{g}: {err}' for g,err in data['failed']))
        elif action == 'sensor_read':
            self._update_sensor_display(data, set_choice=True)
            self.statusBar().showMessage('已讀取目前感測器模式')
        elif action == 'sensor_write':
            self._update_sensor_display(data, set_choice=True)
            self._gauge_unavailable('position', '感測器切換後行程學習資料已失效')
            self.log(f'INFO  感測器已切換為 {SENSOR_MODE_LABELS[data]}，狀態讀回一致；需重新學習行程')
            QMessageBox.warning(self, '切換完成，請重新學習',
                                '已確認 CI76 回報新感測器模式。原行程學習資料已失效，'
                                '完成學習及回授檢查前請勿進行正常行程控制。')
        elif action == 'motor_time_read':
            pass
        elif action == 'motor_time_reset':
            self.motor_time_label.setText('0 天 00 時 00 分 00 秒')
            try:
                self.event_store.append('motor_time_reset', **data)
            except OSError as exc:
                self.statusBar().showMessage('Log 寫入失敗：' + str(exc))
            self.log('ACTION  運轉時間歸零：0x0F/0x03，0x14 讀回為零；斷電保存尚未驗證')
            QMessageBox.information(self, '歸零完成', '控制器已回報 0 秒；斷電後保留仍需實板確認。')
        elif action == 'diagnostics':
            self.latest_diagnostics = data
            report_file = self.event_store.folder / f'CI76_Diagnostic_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.json'
            try:
                self.event_store.export_snapshot(data, report_file)
            except OSError as exc:
                QMessageBox.warning(self, '診斷已讀取，但保存失敗', str(exc))
                return
            counts = data['counters']
            self.log(f'DIAG  電壓={counts["voltage"]} 電流={counts["current"]} 位置={counts["position"]} 總計={counts["total"]}；已儲存報告')
            QMessageBox.information(self, '診斷報告已保存',
                f'電壓異常：{counts["voltage"]} 次\n電流異常：{counts["current"]} 次\n'
                f'位置異常：{counts["position"]} 次\n總故障：{counts["total"]} 次\n\n'
                f'報告：{report_file}\n\n'
                '注意：既有韌體只有累計次數，不能復原離線故障發生時間。')
        elif action == 'learning_start':
            self.learning_requested = True
            self.learning_seen = False
            self.learn_feedback.setText('學習要求已 ACK；等待進入學習（可能需數秒）')
            self.log('ACTION 學習要求 ACK 0x02/01；不代表成功')
            self._render_motion_state()
        elif action == 'learning_stage':
            if data == 'learning':
                self.learning_seen = True
                self.learn_feedback.setText('● 學習中（MCU 0x12=05）')
            elif data == 'failed':
                self.learn_feedback.setText('學習失敗旗標已出現')
        elif action == 'learning_result':
            self.learning_requested = False
            if data.get('stage') == 'completed_candidate':
                self.learn_feedback.setText('MCU 回報學習結束，但回授／有效行程尚未驗證')
                self.log('LEARN MCU 回報完成候選；舊韌體可能無 Hall/POT 仍假成功，須驗證有效行程')
            else:
                self.learn_feedback.setText('學習可能失敗：請檢查 ERR_LEARN_FAIL／回授')
                self.log('LEARN 錯誤旗標提示學習失敗')
            self._render_motion_state()
        elif action == 'learning_abort':
            self.learning_requested = False
            self.learn_feedback.setText('取消要求已送達；請現場確認停止／0x17')
            self.log('ACTION 學習取消指令 ACK；尚未確認實際停止')
            self._render_motion_state()
        elif action == 'demo_speed':
            self.demo_dirty = True  # after timeout MCU may have applied the speed
            self.demo_write_status.setText('Demo 速度寫入不確定，請讀回並還原原設定')
        if action == 'demo_limit':
            self._demo_write_inflight = False
            self.demo_dirty = True
            actual_a = float(data['actual_A'])
            self.demo_verified_limit = actual_a
            # Update Page 1 ONLY from MCU readback, not a speculative Demo target.
            self._apply_group('電流', data['current_group'], preserve_draft=True)
            if self._demo_pending_value is not None and abs(self._demo_pending_value - actual_a) > 0.011:
                self.demo_write_status.setText(
                    f'MCU 已確認 {actual_a:.2f} A；Demo 新目標 {self._demo_pending_value:.2f} A 等待寫入')
                if not self.demo_update_timer.isActive():
                    self.demo_update_timer.start()
            else:
                self._demo_pending_value = None
                self._demo_last_sent = actual_a
                self.demo_update_timer.stop()
                self._set_demo_limit_display(actual_a)
                self.demo_write_status.setText(f'✓ Demo 寫入／MCU 讀回一致：{actual_a:.2f} A')
            self._render_motion_state()
            self.log(f'DEMO 限流目標 {data["requested_A"]:.2f} A，ACK/讀回 {actual_a:.2f} A')
            if 'transactions' in data:
                detail = ', '.join(f'{t["command"]} {t["elapsed_ms"]:.1f}ms' for t in data['transactions'])
                self.log(f'DEMO TIMING 總計 {data["elapsed_ms"]:.1f}ms；{detail}')
        elif action == 'demo_speed':
            self.demo_speed_modified = True
            self.demo_dirty = True
            self.motor_speed.setValue(data['speed'])
            self.log(f'DEMO 速度讀回一致：{data["speed"]}%（0x07）')
            self._render_motion_state()
        elif action == 'error_clear':
            self.log(f'FAULT 清除要求 0x0F/02：原值 {data["before"]}，讀回 {data["after"]}')
            self.submit('monitor', {'auto':False, 'trace':False})
            QMessageBox.information(self,'故障清除讀回',
                f'清除前：{data["before"]}\n清除後：{data["after"]}\n\n'
                + ('目前無故障旗標；請確認實際故障原因已排除。' if data['cleared']
                   else '仍有故障旗標；可能是原因尚未排除、待學習或硬體保護正在生效。'))
        elif action == 'demo_restore':
            self._demo_write_inflight = False
            self._demo_pending_value = None
            self._demo_last_sent = None
            self.demo_update_timer.stop()
            if data.get('restored'):
                self.demo_dirty = False
                self.demo_verified_limit = None
                if data['current_group'] is not None:
                    self._apply_group('電流', data['current_group'], preserve_draft=True)
                self.demo_speed_modified = False
                self.demo_write_status.setText('已恢復本次連線開始展示前的限流與速度（讀回一致）')
                self.log('DEMO 電流原始參數已還原（僅 MCU RAM，未驗證斷電）')
            else:
                self.demo_write_status.setText(data.get('reason','尚未更動'))
            self._render_motion_state()
        elif action == 'bench_uart_mode':
            self.bench_uart_enabled = bool(data['enabled'])
            self.motion_approved = False
            self._demo_last_sent = None
            self._render_motion_state()
            self.log('ACTION  UART MODE ' + ('ON（舊版短時內測）' if self.bench_uart_enabled else 'OFF'))
        elif action == 'motor_start':
            self.motion_active = data['direction']
            self._render_motion_state()
            extra = '；2秒 PC 端自動停止' if data.get('legacy_fw') else ''
            self.log(f'ACTION  推桿{ "伸出" if self.motion_active == "extend" else "縮回"} 速度 {data["speed"]}%{extra}')
        elif action in ('motor_stop','motor_autostop'):
            if action == 'motor_stop':
                self.stop_pending = False
            self.motion_active = None
            self._render_motion_state()
            self.log(f'ACTION  已送出停止命令；回覆狀態={data.get("status")}（需確認實際停止）')
            if data.get('reason') == 'host_2s_timeout':
                self.statusBar().showMessage('已到 2 秒軟體限時，STOP 已送出；請確認推桿實際停止')
            if data.get('status') not in (1, 4, 6, 7):
                self.motion_supported = False
                self.bench_uart_enabled = False
                self._render_motion_state()
                self.motor_feedback.setText('停止未確認，請檢查實體')
                QMessageBox.critical(self, '停止狀態未確認',
                    '控制器已回覆停止指令，但未確認馬達完全停止。\n'
                    '請立即用硬體停止手段處理，確認停止後重新連線。')
        elif action == 'writegroup':
            group, actual, requested = data
            self._apply_group(group, actual)
            diffs = [k for k in requested if abs(actual[k] - requested[k]) > 0.011]
            if diffs:
                QMessageBox.warning(self, '讀回不一致', group + ': ' + '、'.join(diffs))
            else:
                if group == '電流':
                    # Page 1 has explicitly taken ownership of the current setting.
                    # A later Demo restore must not overwrite this confirmed choice.
                    self.demo_dirty = self.demo_speed_modified
                    self.demo_verified_limit = (actual['current_limit'] if within_slider_range(actual['current_limit']) else None)
                    self._set_demo_limit_display(actual['current_limit'])
                    self.demo_write_status.setText(
                        f'✓ 第一頁電流設定已確認：{actual["current_limit"]:.2f} A；Demo 可接續調整')
                    self._render_motion_state()
                self.log(f'INFO  「{group}」寫入 ACK 和讀回一致；未驗證 Flash')
                self.statusBar().showMessage(f'「{group}」寫入成功（暫存），未驗證 Flash')
        elif action == 'monitor_item':
            self.latest_monitor.update({k: v for k,v in data.items() if k not in ('error_flags',)})
            if 'motor' in data:
                self.hud_motor_state.setText(str(data['motor']))
            for key, value in data.items():
                if key == 'error_flags':
                    self._render_error_flags(value)
                elif key == 'motor_time':
                    self.motor_time_label.setText(value)
                elif key == 'motor_seconds':
                    self.motor_time_label.setToolTip(f'原始秒數：{value}')
                elif key == 'sensor_mode':
                    self._update_sensor_display(value, set_choice=not self.sensor_mode_ready and not self.local_profile_loaded)
                elif key in self.gauge_bars:
                    self._update_gauge(key, value)
                    if key == 'current':
                        self.demo_actual.setText(f'{float(value):.2f} A')
                        self.demo_current_bar.setValue(gauge_value(float(value), 8.0))
                        self.demo_current_dial.setReading(float(value))
                        sample_time = time.perf_counter()
                        if self._last_demo_current_ts is not None:
                            delta_ms = (sample_time - self._last_demo_current_ts) * 1000.0
                            self.demo_sample_rate.setText(f'電流實際刷新：約 {delta_ms:.0f} ms')
                        else:
                            self.demo_sample_rate.setText('電流實際刷新：已收到資料')
                        if self.auto_poll.isChecked():
                            self.poll_rate.setText(
                                f'電流實際：約 {delta_ms:.0f} ms' if self._last_demo_current_ts is not None
                                else '電流實際：收到資料')
                        self._last_demo_current_ts = sample_time
                else:
                    self.live[key].setText(str(value))
                    self.live[key].setStyleSheet('color:#B5ECE8;')
        elif action == 'monitor_problem':
            cmd, why = data
            keys = {0x10: ('current',), 0x11: ('position',),
                    0x12: ('motor',), 0x13: ('uart','sensor'),
                    0x17: ('errors',), 0x14: ('motor_time',)}.get(cmd, ())
            if cmd == 0x17:
                self._reset_error_flags('通訊異常／未知')
                self.hud_fault.setText('UART TIMEOUT')
            if cmd == 0x10:
                self.latest_monitor.pop('current', None)
                self._connection_state('TIMEOUT / REMOVED', '電流資料已失效；請檢查 USB / UART 連線')
            if cmd == 0x12:
                self.hud_motor_state.setText('UNKNOWN / STALE')
                self.latest_monitor.pop('motor', None)
            if cmd == 0x13:
                self.hud_sensor.setText('UNKNOWN / STALE')
            for key in keys:
                if key == 'motor_time':
                    self.motor_time_label.setText('—（查詢失敗）')
                    continue
                if key in self.gauge_bars:
                    self._gauge_unavailable(key, why)
                    if key == 'current':
                        self.demo_current_dial.setReading(None)
                        self.demo_actual.setText('— A')
                        self.demo_current_bar.setValue(0)
                        self._last_demo_current_ts = None
                        self.demo_sample_rate.setText('電流實際刷新：通訊逾時')
                        self.poll_rate.setText('電流實際：逾時')
                else:
                    self.live[key].setText('—（查詢失敗）')
                    self.live[key].setStyleSheet('color:#F09A94;')
            # At 100ms, repeated timeouts must not flood the log.
            now = time.monotonic()
            if now - self._last_issue_at.get(cmd, 0) >= 5.0:
                self._last_issue_at[cmd] = now
                self.log(f'WARN  監控 0x{cmd:02X}：{why}')
        elif action == 'monitor_inline':
            # The enclosing write still owns its one pending transaction.
            # Don't decrement it, restart polling, or disconnect mid-write.
            if 'current_only' in data:
                self._set_poll_scope(data['current_only'])
            if data['auto'] and data['ok']:
                self._record_telemetry_sample()
        elif action == 'monitor':
            if 'current_only' in data:
                self._set_poll_scope(data['current_only'])
            if data.get('current_only') and data['failed'] and not data['ok']:
                # A single lost current packet is not proof of USB removal.
                # Mark the value unavailable immediately, but close/lock only
                # after three consecutive failed current-only polls.
                self._current_only_failures += 1
                if self._current_only_failures < 3:
                    return
            else:
                if self._current_only_failures and data['ok'] and self.identity_verified:
                    self._connection_state('CI76 VERIFIED')
                self._current_only_failures = 0
            if data['failed'] and not data['ok']:
                # Reuse the existing safe disconnect path. Never auto-restore,
                # STOP, or toggle UART MODE on an idle monitoring timeout.
                if not (self.motion_active or self.learning_requested or
                        self.bench_uart_enabled or self.demo_dirty):
                    self._reject_connection('TIMEOUT / REMOVED',
                        '本輪監控全部失敗；資料已失效，請檢查連線後手動重連')
                    return
                self._link_stale = True
                self.timer.stop()
                self.demo_update_timer.stop()
                self._demo_pending_value = None
                self.demo_verified_limit = None
                self.latest_monitor.clear()
                self._render_motion_state()
                for button in self.write_buttons.values():
                    button.setEnabled(False)
                self._reset_error_flags('連線失效 / UNKNOWN')
                self._connection_state('TIMEOUT / REMOVED',
                    '連線失效；未自動還原或重播設定。若有動作請用獨立硬體停止，再手動讀取設備資訊。')
            if data['auto']:
                self._record_telemetry_sample()
            failed = len(data['failed'])
            if failed:
                self.statusBar().showMessage(
                    f'監控更新：{len(data["ok"])} 欄成功、{failed} 條查詢失敗；'
                    f'本輪耗時 {data["elapsed_ms"]}ms')
            elif not data['auto']:
                self.statusBar().showMessage('手動狀態讀取完成')
        if action in ('identity', 'readgroup', 'readall', 'writegroup', 'sensor_read', 'sensor_write', 'motor_time_read', 'motor_time_reset', 'diagnostics', 'motor_start', 'bench_start', 'bench_uart_mode', 'motor_stop', 'learning_start', 'learning_abort', 'demo_limit', 'demo_restore', 'demo_speed', 'error_clear'):
            self._foreground_pending = False
            self._resume_poll()

    def _record_telemetry_sample(self):
        if time.monotonic() - self._last_telemetry_log <= 1.0:
            return
        self._last_telemetry_log = time.monotonic()
        sample = dict(current_A=self.latest_monitor.get('current'),
                      position_pct=self.latest_monitor.get('position'),
                      motor_status=self.latest_monitor.get('motor'),
                      flags=self.last_error_bits,
                      motor_seconds=self.latest_monitor.get('motor_seconds'))
        try:
            self.event_store.sample(**sample)
        except OSError as exc:
            self.statusBar().showMessage(f'CSV 記錄失敗：{exc}')

    def on_error(self, action, message):
        if action == 'identity' and not self.identity_verified:
            self._reject_connection('TIMEOUT / REMOVED', 'CI76 設備驗證失敗：' + message)
            return
        if action == 'connect':
            self._connection_pending = False
            self.set_connected(False)
            state = 'PORT BUSY' if any(s in message.lower() for s in
                    ('permission', 'denied', 'busy', 'access', '拒絕')) else 'TIMEOUT / REMOVED'
            self._connection_state(state, 'COM 開啟失敗：' + message)
            return
        if action == 'writegroup' and self._demo_pending_value is None:
            self.demo_write_status.setText('參數寫入尚未確認：請重新讀取 MCU 電流參數')
        if action == 'demo_limit':
            self._demo_write_inflight = False
            self.demo_verified_limit = None
            self.demo_dirty = True  # Unknown after UART timeout: MCU may already have applied it.
            self.demo_update_timer.stop()
            self._demo_last_sent = None
            self.demo_write_status.setText('限流寫入未確認；請停止動作、讀回或按「立即套用／重試」：' + message)
            self._render_motion_state()
        if action in ('learning_start','learning_abort'):
            self.learning_requested = False
            self.interlock_fault = True
            self.learn_feedback.setText('學習操作未確認！請使用硬體停止並重新連線：' + message)
            self._render_motion_state()
        if action == 'motor_lost':
            self._foreground_pending = False
            self.timer.stop()
            self.motion_active = None
            self.motion_supported = False
            self.bench_uart_enabled = False
            self._render_motion_state()
            self.motor_feedback.setText('通訊失聯：必須使用獨立硬體停止')
            self.log('CRITICAL  ' + message)
            QMessageBox.critical(self, '推桿通訊失聯',
                message + '\n請使用實體停止／斷電，確認推桿已實際停止。')
            return
        self.pending = max(0, self.pending - 1)
        if action == 'motor_stop':
            self.stop_pending = False
        if action in ('motor_start','bench_start','motor_stop','bench_uart_mode'):
            self.motion_active = None
            if action in ('bench_start', 'motor_stop', 'bench_uart_mode'):
                self.bench_uart_enabled = False  # Unknown MCU state; require deliberate mode re-enable.
            if action in ('motor_start','motor_stop'):
                self.motion_supported = False
            self._render_motion_state()
        # Some USB-UART errors recur every 100 ms after cable removal.
        now = time.monotonic()
        if action != 'monitor' or now - self._last_issue_at.get('monitor_error', 0) >= 5.0:
            self._last_issue_at['monitor_error'] = now
            self.log(f'ERROR  {action}：{message}')
        self.statusBar().showMessage('UART 通訊錯誤：' + message)
        if action == 'connect':
            self.set_connected(False)
        elif action == 'bench_uart_mode':
            # A precondition failure (e.g. 0x20 feedback/learning flag) happens
            # BEFORE any STOP or UART MODE command is sent. Never report a
            # fictitious STOP ACK failure for this situation.
            QMessageBox.warning(self, 'UART MODE 尚未啟用',
                'CI76 未進入 UART MODE。\n\n原因：' + message +
                '\n\n請先確認行程學習、感測器回授與錯誤旗標，再重新嘗試。'
                '\n若通訊逾時或曾有運動，請先用獨立硬體方式確認馬達已停止。')
        elif action == 'motor_stop':
            QMessageBox.critical(self, '停止命令未確認',
                'STOP 命令無法確認成功；請立即使用獨立硬體停止裝置並確認馬達已停止。\n' + message)
        elif action == 'bench_start':
            QMessageBox.warning(self, '推桿啟動遭拒絕',
                'CI76 沒有確認成功啟動：' + message +
                '\n請檢查故障旗標、學習狀態及停止條件，勿強制跳過保護。')
        elif action not in ('monitor','disconnect'):
            QMessageBox.warning(self, 'CI76 通訊錯誤', f'{action}: {message}')
        if action != 'monitor':
            self._foreground_pending = False
            self._resume_poll()

    def log(self, message):
        stamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.console.appendPlainText(f'{stamp}  {message}')
        try:
            self.event_store.append('console', message=message)
        except OSError:
            # Disk logging must not block a safety-critical motor stop.
            pass
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def save_config(self):
        if set(GROUPS) != self.group_read_ok and not self.local_profile_loaded:
            QMessageBox.warning(self, '設定檔未準備好',
                                '請先連接 CI76 並「讀取全部參數」，或先載入完整設定檔。')
            return
        path, _ = QFileDialog.getSaveFileName(self, '匯出 CI76 設定檔',
            'CI76_parameters.config', 'CI76 設定檔 (*.config);;JSON (*.json)')
        if not path:
            return
        try:
            save_profile(path, {k: e.value() for k, e in self.fields.items()},
                         self.sensor_select.currentData() if (self.sensor_mode_ready or self.local_profile_loaded) else None)
            self.log('INFO  已匯出設定檔（僅本機檔案，未寫入控制器）')
            self.statusBar().showMessage('已儲存本機 .config；不是 Flash 儲存')
        except Exception as exc:
            QMessageBox.warning(self, '匯出失敗', str(exc))

    def load_config(self):
        if self.connected and self.identity_verified and set(GROUPS) != self.group_read_ok:
            QMessageBox.warning(self, '請先讀取全部參數',
                '要將 .config 套用到這台 CI76，請先按「讀取全部參數」取得全部五組資料，'
                '再載入 .config。如此才不會把未讀取的預設值寫入設備。')
            return
        path, _ = QFileDialog.getOpenFileName(self, '載入 CI76 設定檔', '',
            'CI76 設定檔 (*.config);;舊版 JSON (*.json);;全部檔案 (*.*)')
        if not path:
            return
        try:
            profile = load_profile(path)
            for k, v in profile['parameters'].items():
                self.fields[k].setValue(v)
            mode = profile['sensor_mode']
            if mode in SENSOR_MODE_LABELS:
                self.sensor_select.blockSignals(True)
                self.sensor_select.setCurrentIndex(self.sensor_select.findData(mode))
                self.sensor_select.blockSignals(False)
                self._update_sensor_button()
            self.local_profile_loaded = True
            self.log('INFO  .config/JSON 已載入本機畫面；不會自動寫入控制器或切換感測器')
            self.statusBar().showMessage('設定檔已載入畫面；按各組「寫入（暫存）」才能套用')
            QMessageBox.information(self, '設定檔載入成功',
                '設定值已載入畫面，未寫入 CI76。\n'
                '請確認設備碼及各組已讀取完成，再由你逐組確認寫入；'
                '若再次讀取設備參數，載入值會被覆蓋。')
        except Exception as exc:
            QMessageBox.warning(self, '載入失敗', str(exc))

    # Backwards-compatible script entrypoints
    def save_json(self):
        self.save_config()

    def load_json(self):
        self.load_config()

    def closeEvent(self, event):
        if self.learning_requested:
            self.request_learning_abort()
            QMessageBox.warning(self, '學習程序尚未結束', '請先確認學習已停止，再退出程式。')
            event.ignore()
            return
        if self.demo_dirty:
            QMessageBox.warning(self, '展示限流尚未還原', '請先按「還原原限流」，確認讀回成功後再離開。')
            event.ignore()
            return
        if self.motion_active:
            self.request_stop()
            QMessageBox.warning(self, '推桿控制尚未停止',
                '已要求停止。請先確認推桿完全停止後再關閉程式；若通訊失聯請使用實體停止手段。')
            event.ignore()
            return
        if self.bench_uart_enabled:
            QMessageBox.warning(self, '請先關閉 UART MODE',
                '舊韌體 UART MODE 仍為 ON，請先點擊關閉並確認回覆。')
            event.ignore()
            return
        self.event_store.append('session_end')
        self.timer.stop()
        self.worker.halt()
        if not self.worker.wait(2500):
            self.log('WARN  Serial worker 尚未完全停止')
        event.accept()


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    window = CI76Window()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
