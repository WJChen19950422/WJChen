"""Current-only tuning telemetry; safety and explicit readback remain intact."""
import time
import pytest
from monitoring import scheduled_monitor_commands
from worker import SerialWorker
from test_v09_learning_demo import FakeClient
from test_v018_ui import app, make_window, verify


class ReadRecorder(FakeClient):
    def __init__(self):
        super().__init__()
        self.reads = []
        self.faults = b'\x00\x00'
    def read_cmd(self, cmd, **kwargs):
        self.reads.append(cmd)
        return super().read_cmd(cmd, **kwargs)


def test_idle_tuning_queries_only_current_indefinitely():
    timestamps = {}
    for tick in range(200):
        assert scheduled_monitor_commands(auto=True, now=tick*.05, last=timestamps,
                   fast_demo=True, current_only=True) == [0x10]
    assert timestamps == {}  # Background timestamps aren't falsely refreshed.


@pytest.mark.parametrize('auto,fast_demo', [(False,True),(False,False),(True,False)])
def test_other_read_modes_ignore_current_only(auto, fast_demo):
    assert scheduled_monitor_commands(auto=auto, now=10, last={}, fast_demo=fast_demo,
            current_only=True) == [0x10,0x11,0x12,0x13,0x17,0x14]


def test_worker_idle_sends_only_current_and_no_writes(app):
    w=SerialWorker(); w.client=ReadRecorder()
    results=[]
    w.success.connect(lambda action,data: results.append((action,data)))
    for _ in range(5):
        w._monitor(dict(auto=True, fast_demo=True, current_only=True))
    assert w.client.reads == [0x10]*5
    assert w.client.writes == []
    assert all(data['current_only'] for action,data in results if action=='monitor')


@pytest.mark.parametrize('safety_state', ['motor_direction','bench_uart_enabled','bench_limited_motion','learning_active'])
def test_worker_safety_state_overrides_stale_ui_request(app, safety_state):
    w=SerialWorker(); w.client=ReadRecorder()
    setattr(w,safety_state,'extend' if safety_state=='motor_direction' else True)
    w.client.uart_mode=1  # Valid motion mode; OFF must trigger the existing auto-STOP.
    w.motor_last_tick=time.monotonic()
    w.bench_deadline=time.monotonic()+100
    results=[]
    w.success.connect(lambda action,data: results.append((action,data)))
    for _ in range(5):
        w._monitor(dict(auto=True, fast_demo=True, current_only=True))
        w._slow_time.pop(0xFE,None)  # Advance the background scheduling opportunity.
    assert {0x10,0x11,0x12,0x13,0x14,0x17}.issubset(w.client.reads)
    assert results[-1][0]=='monitor' and results[-1][1]['current_only'] is False


def test_current_only_cannot_skip_explicit_limit_readback(app):
    w=SerialWorker(); w.client=ReadRecorder()
    w._monitor(dict(auto=True, fast_demo=True, current_only=True))
    w.client.reads.clear()
    result=w._demo_limit(1.5)
    assert result['actual_A']==1.5
    assert 0x71 in w.client.reads
    assert 0x70 not in w.client.reads  # Unused firmware-version query removed.
    assert 0x12 in w.client.reads and 0x17 in w.client.reads
    assert w.client.reads.count(0x19)>=2
    assert w.client.writes[-1][0]==0x06


def test_ui_requests_current_only_and_background_becomes_unknown(make_window):
    w=make_window(); verify(w)
    w.latest_monitor.update(current=1.2,position=23,motor='停止',motor_seconds=30)
    w.tabs.setCurrentIndex(1)
    w.auto_poll.setChecked(True)
    action,payload=w.worker.commands[-1]
    assert action=='monitor' and payload['current_only'] and payload['fast_demo']
    assert w.latest_monitor=={'current':1.2}
    assert w.hud_motor_state.text()=='PAUSED / UNKNOWN'
    assert w.hud_fault.text()=='PAUSED / UNKNOWN'
    assert all('✓' not in flag.text() for flag in w.flag_labels.values())
    assert w.last_error_bits is None
    assert '暫停更新' in w.demo_poll_scope.text()


@pytest.mark.parametrize('attr', ['motion_active','learning_requested','bench_uart_enabled','stop_pending','interlock_fault'])
def test_ui_safety_states_keep_other_queries(make_window,attr):
    w=make_window(); verify(w)
    w.tabs.setCurrentIndex(1)
    w.auto_poll.setChecked(True)
    w.pending=0; w.worker.commands.clear()
    # interlock_fault blocks monitor? monitor remains explicitly permitted.
    setattr(w,attr,'extend' if attr=='motion_active' else True)
    w.poll_once()
    assert w.worker.commands[-1][0]=='monitor'
    assert not w.worker.commands[-1][1]['current_only']


def test_return_to_page1_resumes_full_schedule_without_writes(make_window):
    w=make_window(); verify(w)
    w.tabs.setCurrentIndex(1); w.auto_poll.setChecked(True)
    w.worker.commands.clear(); w.pending=0
    w.tabs.setCurrentIndex(0); w.poll_once()
    assert len(w.worker.commands)==1
    action,payload=w.worker.commands[0]
    assert action=='monitor'
    assert not payload['current_only'] and not payload['fast_demo']
    assert not w._background_paused
    # Previously paused flags stay unknown until an actual reply arrives.
    assert w.last_error_bits is None


def test_current_timeout_marks_unavailable_but_requires_three_failures(make_window):
    w=make_window(); verify(w)
    w.worker.success.emit('monitor_item',{'current':1.23})
    failure=dict(auto=True,current_only=True,ok=[],failed=['timeout'],elapsed_ms=120)
    for i in range(2):
        w.worker.success.emit('monitor_problem',(0x10,'timeout'))
        w.worker.success.emit('monitor',failure)
        assert w.connected and w.demo_current_dial._value is None
        assert not w.worker.commands
    w.worker.success.emit('monitor',failure)
    assert not w.connected
    assert w.worker.commands==[('disconnect',None)]


def test_success_resets_consecutive_current_failures(make_window):
    w=make_window(); verify(w)
    failure=dict(auto=True,current_only=True,ok=[],failed=['timeout'],elapsed_ms=120)
    w.worker.success.emit('monitor_problem',(0x10,'timeout'))
    w.worker.success.emit('monitor',failure)
    w.worker.success.emit('monitor_item',{'current':1.23})
    w.worker.success.emit('monitor',dict(auto=True,current_only=True,ok=['current'],failed=[],elapsed_ms=10))
    assert w._current_only_failures==0
    assert w.connection_label.text()=='CI76 VERIFIED'
    assert w.demo_current_dial._value==1.23
