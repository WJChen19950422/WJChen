"""Real Qt widgets with recorded worker commands; never open physical UART."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from functools import partial
from pathlib import Path
import time
import pytest
from PySide6.QtCore import QObject, Signal, QSettings, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
import main
from eventlog import EventLog
from settings_store import PortIdentity, SettingsStore, match_port
from diagnostics import decode_error_flags

P = PortIdentity('COM3', 'USB CI76', 'USB VID:PID=1234:5678', 'ABC', 0x1234, 0x5678)
CURRENT = dict(current_limit=1.0, current_overload=9.0, current_time=500)
INFO = dict(version='0x0B02', device='0x0B01', sensor_mode=1, motor_seconds=42)


class RecordedWorker(QObject):
    success = Signal(str, object)
    error = Signal(str, str)
    trace = Signal(str)
    def __init__(self):
        super().__init__()
        self.commands = []
    def start(self): pass
    def submit(self, action, data=None): self.commands.append((action, data))
    def configure_demo_monitor(self, config): self.demo_monitor_config=dict(config)
    def halt(self): pass
    def wait(self, ms): return True


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_window(app, tmp_path, monkeypatch):
    windows = []
    monkeypatch.setattr(main, 'SerialWorker', RecordedWorker)
    monkeypatch.setattr(main, 'EventLog', partial(EventLog, tmp_path/'logs'))
    monkeypatch.setattr(main.list_ports, 'comports', lambda: [P])
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: QMessageBox.StandardButton.Ok)
    def create(*, auto=False, saved=None, ports=None):
        if ports is not None:
            monkeypatch.setattr(main.list_ports, 'comports', lambda: ports)
        store = SettingsStore(QSettings(str(tmp_path/f'{len(windows)}.ini'), QSettings.Format.IniFormat))
        store.set_auto_connect(auto)
        if saved:
            store.remember_verified(saved, '0x0B01')
        w = main.CI76Window(settings_store=store)
        windows.append(w)
        app.processEvents()
        return w
    yield create
    for w in windows:
        w.demo_dirty = False
        w.learning_requested = False
        w.motion_active = None
        w.bench_uart_enabled = False
        w.close()
        w.deleteLater()
    app.processEvents()


def verify(w):
    w.toggle_connection()
    w.worker.success.emit('connect', 'COM3')
    w.worker.success.emit('identity', INFO)
    w._apply_group('電流', CURRENT)
    w.worker.commands.clear()


def test_preferences_default_off_and_verified_only(tmp_path):
    path = str(tmp_path/'settings.ini')
    store = SettingsStore(QSettings(path, QSettings.Format.IniFormat))
    assert not store.auto_connect
    assert not store.remember_verified(P, '0xFFFF')
    assert store.last_port() is None
    assert store.remember_verified(P, '0x0B01')
    store.set_auto_connect(True)
    reopened = SettingsStore(QSettings(path, QSettings.Format.IniFormat))
    assert reopened.auto_connect and reopened.last_port() == P
    assert set(reopened.settings.allKeys()) == {'connection/auto_connect', 'connection/last_verified_port'}


@pytest.mark.parametrize('ports,expected', [
    ([P], 'COM3'),
    ([PortIdentity('COM9', P.description, P.hwid, P.serial_number, P.vid, P.pid)], 'COM9'),
    ([], None), ([P, P], None),
    ([PortIdentity('COM3', P.description, P.hwid, 'OTHER', P.vid, P.pid)], None),
])
def test_unique_usb_matching(ports, expected):
    p, _ = match_port(P, ports)
    assert (p.device if p else None) == expected


@pytest.mark.parametrize('saved,ports,expected', [
    (PortIdentity('COM3','USB','HW'), [PortIdentity('COM3','USB','HW')], 'COM3'),
    (PortIdentity('COM3','USB','HW'), [PortIdentity('COM3','OTHER','HW')], None),
    (PortIdentity('COM3'), [PortIdentity('COM3')], None),
    (PortIdentity('COM3','USB','HW'), [PortIdentity('COM8','USB','HW')], None),
])
def test_fallback_requires_com_and_consistent_metadata(saved, ports, expected):
    p, _ = match_port(saved, ports)
    assert (p.device if p else None) == expected


def test_startup_default_and_preselect_no_writes(make_window):
    renamed = PortIdentity('COM9', P.description, P.hwid, P.serial_number, P.vid, P.pid)
    w = make_window(saved=P, ports=[P.__class__('COM1','other'), renamed])
    assert w.ports.currentData() == 'COM9'
    assert not w.auto_connect_check.isChecked()
    assert w.worker.commands == []
    assert not w.identity_verified
    assert not any(b.isEnabled() for b in w.write_buttons.values())


def test_auto_connect_once_read_only_then_remember(make_window):
    w = make_window(auto=True, saved=P)
    assert w.worker.commands == [('connect', 'COM3')]
    w._startup_connection(); w.toggle_connection(); w._begin_connection()
    assert len(w.worker.commands) == 1
    w.worker.success.emit('connect', 'COM3')
    assert w.worker.commands[-1] == ('identity', None)
    assert not w.identity_verified
    w.submit('writegroup', ('電流', CURRENT))
    assert len(w.worker.commands) == 2
    w.worker.success.emit('identity', INFO)  # New firmware accepted by Device Code.
    assert w.identity_verified
    assert w.connection_label.text() == 'CI76 VERIFIED'
    assert w.preferences.last_port() == P
    assert [a for a, _ in w.worker.commands] == ['connect','identity']
    w.toggle_connection()
    assert w.worker.commands[-1] == ('disconnect',None)
    w.worker.success.emit('disconnect',None)
    w.refresh_ports(); w._startup_connection()
    assert [a for a,_ in w.worker.commands].count('connect') == 1


@pytest.mark.parametrize('ports', [[], [P,P]])
def test_missing_ambiguous_does_not_attempt(make_window, ports):
    w = make_window(auto=True, saved=P, ports=ports)
    assert w.worker.commands == []
    assert w.connection_label.text() == 'DISCONNECTED'


@pytest.mark.parametrize('message,state', [('Access denied: port busy','PORT BUSY'),
                                        ('device removed','TIMEOUT / REMOVED')])
def test_open_error_no_retry(make_window, message, state):
    w = make_window(auto=True, saved=P)
    w.worker.error.emit('connect', message)
    assert not w.connected and not w.identity_verified
    assert w.connection_label.text() == state
    assert w.connect_btn.isEnabled()
    w._startup_connection()
    assert len(w.worker.commands) == 1


@pytest.mark.parametrize('failure', ['mismatch', 'timeout'])
def test_identity_failure_closes_without_writes_or_saving(make_window, failure):
    w = make_window()
    w.toggle_connection(); w.worker.success.emit('connect', 'COM3')
    if failure == 'mismatch':
        w.worker.success.emit('identity', dict(INFO, device='0xFFFF'))
    else:
        w.worker.error.emit('identity','read timed out')
    assert w.worker.commands == [('connect','COM3'),('identity',None),('disconnect',None)]
    assert not w.connected and not w.identity_verified
    assert w.preferences.last_port() is None
    assert not any(b.isEnabled() for b in w.write_buttons.values())
    w.worker.success.emit('disconnect',None)
    assert w.connect_btn.isEnabled()
    assert w.connection_label.text() == ('IDENTITY MISMATCH' if failure == 'mismatch' else 'TIMEOUT / REMOVED')


def test_page1_draft_survives_demo_readback_and_restore(make_window):
    w = make_window(); verify(w)
    w.fields['current_limit'].setValue(2.25)
    w.fields['current_overload'].setValue(7)
    w.fields['current_time'].setValue(750)
    assert w.worker.commands == []
    w.tabs.setCurrentIndex(1)
    w.demo_slider.setValue(150)
    w._flush_demo_limit()
    assert w.worker.commands == [('demo_limit', 1.5)]
    result=dict(requested_A=1.5, actual_A=1.5, current_group=dict(CURRENT,current_limit=1.5))
    w.worker.success.emit('demo_limit',result)
    assert w.last_values['current_limit'] == 1.5
    assert w.fields['current_limit'].value() == 2.25
    assert w.fields['current_overload'].value() == 7
    assert w.fields['current_time'].value() == 750
    assert '1.50' in w.demo_applied.text()
    w.worker.success.emit('demo_restore',dict(restored=True,current_group=CURRENT))
    assert w.fields['current_limit'].value() == 2.25
    assert w.last_values['current_limit'] == 1


def test_clean_page1_tracks_confirmed_readback(make_window):
    w = make_window(); verify(w)
    w.worker.success.emit('demo_limit',dict(requested_A=1.5,actual_A=1.5,
        current_group=dict(CURRENT,current_limit=1.5)))
    assert w.fields['current_limit'].value() == 1.5
    assert not w._current_draft_dirty


def test_tab_change_cancels_unsent_does_not_replay(make_window):
    w = make_window(); verify(w)
    w.tabs.setCurrentIndex(1)
    w.demo_slider.setValue(175)
    w.tabs.setCurrentIndex(0)
    w.tabs.setCurrentIndex(1)
    w._flush_demo_limit()
    assert w._demo_pending_value is None
    assert w.worker.commands == []


def test_demo_coalesces_and_inflight_does_not_duplicate(make_window):
    w = make_window(); verify(w)
    w.tabs.setCurrentIndex(1)
    for value in (100,125,150,180): w.demo_slider.setValue(value)
    assert not w.worker.commands
    w._flush_demo_limit(); w._flush_demo_limit()
    assert w.worker.commands == [('demo_limit',1.8)]
    w.demo_slider.setValue(200)
    w.worker.success.emit('demo_limit',dict(requested_A=1.8,actual_A=1.8,
        current_group=dict(CURRENT,current_limit=1.8)))
    w._flush_demo_limit()
    assert w.worker.commands[-1] == ('demo_limit',2)


@pytest.mark.parametrize('ticks', [0,800])
def test_demo_ui_edges(make_window, ticks):
    w = make_window(); verify(w)
    w.tabs.setCurrentIndex(1); w.demo_slider.setValue(ticks)
    w._flush_demo_limit()
    assert w.worker.commands == [('demo_limit',ticks/100)]


def test_disconnect_clears_telemetry_and_ignores_late_sample(make_window):
    w = make_window(); verify(w)
    w.worker.success.emit('monitor_item',dict(current=1.23))
    w._render_error_flags(decode_error_flags(b'\x00\x00'))
    assert len(w.flag_labels) == 9
    assert all('✓' in l.text() for l in w.flag_labels.values())
    w.set_connected(False)
    w.worker.success.emit('monitor_item',dict(current=4.56))
    assert w.demo_current_dial._value is None
    assert w.demo_actual.text() == '— A'
    assert w.latest_monitor == {}
    assert all('✓' not in l.text() for l in w.flag_labels.values())
    assert w.hud_fault.text() == 'NOT READ'


def test_monitor_loss_closes_idle_port_and_stales_values(make_window):
    w = make_window(); verify(w)
    w.worker.success.emit('monitor_problem',(0x10,'removed'))
    w.worker.success.emit('monitor',dict(ok=[],failed=['removed'],auto=True,elapsed_ms=1))
    assert not w.connected
    assert w.worker.commands == [('disconnect',None)]
    assert w.demo_current_dial._value is None
    assert w.connection_label.text() == 'TIMEOUT / REMOVED'


def test_stop_shortcut_learning_order_and_theme(make_window, app):
    w = make_window(); verify(w)
    w.show(); app.processEvents()
    assert w.stop_btn.parent() == w.learn_btn.parent() == w.learn_abort_btn.parent()
    layout=w.stop_btn.parent().layout().itemAt(0).layout()
    assert layout.indexOf(w.learn_btn) == layout.indexOf(w.stop_btn)+1
    assert layout.indexOf(w.learn_abort_btn) == layout.indexOf(w.learn_btn)+1
    QTest.keyClick(w, Qt.Key.Key_Escape); app.processEvents()
    assert w.worker.commands == [('motor_stop',None)]
    assert w.demo_current_dial.toolTip() == ''
    assert not w.console.isVisible()
    assert app.palette().highlight().color().name() == '#3ba7ff'
    assert w.ports.view().hasMouseTracking()
    assert w.findChild(main.QLabel,'brandWord').text() == 'MOTECK'


def test_lost_link_with_modified_demo_stops_pending_writes(make_window):
    w = make_window(); verify(w)
    w.demo_dirty=True
    w.tabs.setCurrentIndex(1); w.demo_slider.setValue(175)
    w.worker.success.emit('monitor',dict(ok=[],failed=['USB removed'],auto=True,elapsed_ms=1))
    assert w.connected  # No unsafe implicit restore / mode write on cable removal.
    assert not w.demo_slider.isEnabled()
    assert w._demo_pending_value is None
    assert not w.timer.isActive()
    w.submit('demo_limit',2)
    assert w.worker.commands == []
    w.request_stop()
    assert w.worker.commands == [('motor_stop',None)]


def test_real_worker_connect_identity_disconnect_are_read_only(monkeypatch, app):
    from worker import SerialWorker
    from test_v09_learning_demo import FakeClient
    from transport import DeviceClient
    w=SerialWorker()
    class Client(FakeClient):
        def __init__(self):
            super().__init__(); self.reads=[]; self.closed=False
        def read_cmd(self,cmd,**kw):
            self.reads.append(cmd)
            return super().read_cmd(cmd,**kw)
        def close(self):
            self.closed=True
            w.running=False
    client=Client()
    monkeypatch.setattr(DeviceClient,'open',lambda *a,**k: client)
    results=[]; errors=[]
    w.success.connect(lambda action,data: results.append((action,data)))
    w.error.connect(lambda action,message: errors.append((action,message)))
    w.submit('connect','COM3'); w.submit('identity'); w.submit('disconnect')
    w.run()
    assert not errors
    assert [action for action,_ in results] == ['connect','identity','disconnect']
    assert client.reads == [0x70,0x71,0x13,0x14]
    assert client.writes == []
    assert client.closed and w.client is None


@pytest.mark.parametrize('raw',['[]','not-json','{"device":3}','{"device":"COM3","vid":"bad"}'])
def test_malformed_preferences_fail_closed(tmp_path, raw):
    q=QSettings(str(tmp_path/'broken.ini'),QSettings.Format.IniFormat)
    q.setValue('connection/last_verified_port',raw)
    assert SettingsStore(q).last_port() is None


def test_manual_readall_and_page1_write_require_explicit_confirmation(make_window, monkeypatch):
    w = make_window(); verify(w)
    w.readall_btn.click()
    assert w.worker.commands == [('readall',None)]
    w.worker.success.emit('readgroup_part',('電流',CURRENT))
    w.worker.success.emit('readall',dict(ok=['電流'],failed=[]))
    w.worker.commands.clear()
    w.fields['current_limit'].setValue(2.25)
    assert not w.worker.commands
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k: QMessageBox.StandardButton.No)
    w.write_buttons['電流'].click()
    assert not w.worker.commands
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k: QMessageBox.StandardButton.Yes)
    w.write_buttons['電流'].click()
    requested=dict(CURRENT,current_limit=2.25)
    assert w.worker.commands == [('writegroup',('電流',requested))]
    w.worker.success.emit('writegroup',('電流',requested,requested))
    assert not w._current_draft_dirty
    assert w.demo_target_spin.value() == 2.25
    assert w.demo_verified_limit == 2.25


def test_demo_debounce_timer_sends_latest_target(make_window):
    w = make_window(); verify(w)
    w.tabs.setCurrentIndex(1)
    w.demo_slider.setValue(150)
    QTest.qWait(10)
    w.demo_slider.setValue(200)
    assert not w.worker.commands
    QTest.qWait(80)
    assert w.worker.commands == [('demo_limit',2)]


def test_all_demo_view_modes_and_log_toggle(make_window, app):
    w = make_window(); w.show(); w.tabs.setCurrentIndex(1); app.processEvents()
    for index, dial, bar, number in [(0,True,True,False),(1,False,True,True),(2,True,False,False)]:
        w.demo_view_combo.setCurrentIndex(index)
        assert w.demo_current_dial.isVisible() == dial
        assert w.demo_current_bar.isVisible() == bar
        assert w.demo_actual.isVisible() == number
    w.log_toggle.click()
    assert w.console.isVisible()
    w.log_toggle.click()
    assert not w.console.isVisible()
