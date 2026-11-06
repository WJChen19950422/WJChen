"""Deterministic UART latency simulation, no hardware or concurrent UART calls."""
from types import SimpleNamespace
import pytest
import worker as worker_module
from worker import SerialWorker
from protocol import ProtocolError
from test_v09_learning_demo import FakeClient
from test_v018_ui import app, make_window, verify


class Clock:
    def __init__(self): self.value=100.0
    def now(self): return self.value
    def advance(self, seconds): self.value+=seconds


class TimedClient(FakeClient):
    def __init__(self,clock,latency=.020):
        super().__init__()
        self.clock=clock; self.latency=latency
        self.calls=[]; self.active=0; self.max_active=0
    def transact(self,kind,cmd,callback):
        self.active+=1; self.max_active=max(self.max_active,self.active)
        self.calls.append((kind,cmd,self.clock.now()))
        try:
            self.clock.advance(self.latency)
            return callback()
        finally: self.active-=1
    def read_cmd(self,cmd,**kw):
        return self.transact('read',cmd,lambda: super(TimedClient,self).read_cmd(cmd,**kw))
    def write_cmd(self,cmd,payload,**kw):
        return self.transact('write',cmd,lambda: super(TimedClient,self).write_cmd(cmd,payload,**kw))


@pytest.fixture
def simulated_worker(app,monkeypatch):
    clock=Clock()
    monkeypatch.setattr(worker_module,'time',SimpleNamespace(monotonic=clock.now,sleep=clock.advance))
    w=SerialWorker();w.client=TimedClient(clock)
    return w,clock


def enable(w,**extra):
    w.configure_demo_monitor(dict(auto=True,fast_demo=True,current_only=True,period_ms=50,**extra))


def test_current_samples_arrive_during_write_not_only_after(simulated_worker):
    w,clock=simulated_worker
    enable(w)
    samples=[]; summaries=[]
    w.success.connect(lambda action,data: samples.append(clock.now()) if action=='monitor_item' and 'current' in data else None)
    w.success.connect(lambda action,data: summaries.append(action) if action.startswith('monitor') else None)
    start=clock.now(); result=w._demo_limit(1.5)
    assert result['actual_A']==1.5
    assert len(samples)>=3
    assert max(b-a for a,b in zip([start]+samples,samples+[clock.now()]))<=.090001
    assert 'monitor' not in summaries and 'monitor_inline' in summaries
    assert w.client.max_active==1
    assert [c['command'] for c in result['transactions']]==['0x71','0x17','0x12','0x19','0x06','0x19']
    assert all(abs(c['elapsed_ms']-20)<.001 for c in result['transactions'])
    assert len(result['transactions'])==6


@pytest.mark.parametrize('auto,page',[(False,True),(True,False),(False,False)])
def test_respects_monitor_off_or_leaving_tuning(simulated_worker,auto,page):
    w,clock=simulated_worker
    w.configure_demo_monitor(dict(auto=auto,fast_demo=page,current_only=True,period_ms=50))
    assert w._demo_limit(1.5)['actual_A']==1.5
    assert all(cmd!=0x10 for _,cmd,_ in w.client.calls)


def test_checkbox_change_during_write_stops_further_inline_reads(simulated_worker):
    w,clock=simulated_worker;enable(w)
    samples=[]
    def on_sample(action,data):
        if action=='monitor_item' and 'current' in data:
            samples.append(clock.now())
            w.configure_demo_monitor(dict(auto=False,fast_demo=True))
    w.success.connect(on_sample)
    assert w._demo_limit(1.5)['actual_A']==1.5
    assert len(samples)==1


def test_configured_slower_period_is_honored(simulated_worker):
    w,clock=simulated_worker
    w.configure_demo_monitor(dict(auto=True,fast_demo=True,current_only=True,period_ms=500))
    result=w._demo_limit(1.5)
    assert sum(cmd==0x10 for _,cmd,_ in w.client.calls)==1
    assert result['elapsed_ms']<500


def test_overload_guard_remains_with_interleaving(simulated_worker):
    w,clock=simulated_worker;enable(w)
    w.client.current=(100).to_bytes(2,'little')+(150).to_bytes(2,'little')+(500).to_bytes(2,'little')
    with pytest.raises(ProtocolError,match='過載門檻'): w._demo_limit(2)
    assert w.client.writes==[]


def test_wrong_readback_is_not_reported_success_with_interleaving(simulated_worker):
    w,clock=simulated_worker;enable(w)
    original=w.client.current
    write=w.client.write_cmd
    def ignore_limit(cmd,payload,**kw):
        result=write(cmd,payload,**kw)
        if cmd==0x06: w.client.current=original
        return result
    w.client.write_cmd=ignore_limit
    with pytest.raises(ProtocolError,match='不一致'): w._demo_limit(1.5)
    assert w.demo_original_current==original
    assert sum(cmd==0x10 for _,cmd,_ in w.client.calls)>1


def test_stop_is_serviced_between_requests_before_parameter_write(simulated_worker):
    w,clock=simulated_worker;enable(w)
    read=w.client.read_cmd
    def request_stop(cmd,**kw):
        data=read(cmd,**kw)
        if cmd==0x71: w.submit('motor_stop')
        return data
    w.client.read_cmd=request_stop
    assert w._demo_limit(1.5)['actual_A']==1.5
    cmds=[cmd for cmd,_ in w.client.writes]
    assert cmds.index(0x09)<cmds.index(0x06)
    assert w.client.max_active==1


def test_inline_samples_do_not_finish_foreground_operation(make_window):
    w=make_window();verify(w)
    w.pending=1;w._foreground_pending=True;w._demo_write_inflight=True
    w.worker.success.emit('monitor_item',{'current':1.23})
    w.worker.success.emit('monitor_inline',dict(auto=True,ok=['current'],failed=[],current_only=True))
    assert w.pending==1 and w._foreground_pending and w._demo_write_inflight
    assert w.demo_current_dial._value==1.23
    assert not w.worker.commands


def test_slider_release_flushes_latest_without_waiting_for_timer(make_window):
    w=make_window();verify(w);w.tabs.setCurrentIndex(1)
    assert w.demo_update_timer.interval()==50
    for ticks in (120,140,175): w.demo_slider.setValue(ticks)
    assert w.demo_target_spin.value()==1.75
    assert not w.worker.commands
    w.demo_slider.sliderReleased.emit()
    assert w.worker.commands==[('demo_limit',1.75)]
    w._flush_demo_limit()
    assert len(w.worker.commands)==1


def test_gui_updates_worker_monitor_preferences_during_write(make_window):
    w=make_window();verify(w);w.tabs.setCurrentIndex(1)
    w.auto_poll.setChecked(True)
    assert w.worker.demo_monitor_config['auto']
    w.auto_poll.setChecked(False)
    assert not w.worker.demo_monitor_config['auto']
    w.tabs.setCurrentIndex(0)
    assert not w.worker.demo_monitor_config['fast_demo']
