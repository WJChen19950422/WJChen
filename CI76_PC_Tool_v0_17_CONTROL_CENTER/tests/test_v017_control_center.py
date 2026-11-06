"""v0.17 visual integration and direct current-limit behavior (no real UART)."""
from pathlib import Path
import ast
from test_v09_learning_demo import FakeClient
from worker import SerialWorker
from lab_features import demo_current_write
from protocol import ProtocolError
import pytest

ROOT=Path(__file__).resolve().parents[1]

def test_brand_and_dark_theme_source():
    text=(ROOT/'main.py').read_text(encoding='utf-8')
    ast.parse(text)
    for token in ('MOTECK', 'CI76 CONTROL CENTER', 'QLabel#brandWord',
                  'QTabWidget::pane', 'QTabBar::tab:selected', 'QToolTip',
                  'QGroupBox', "self.demo_current_dial = HudRingDial",
                  'self.hud_limit_dial = HudRingDial'):
        assert token in text

def test_no_extra_high_current_checkbox_or_guard():
    text=(ROOT/'main.py').read_text(encoding='utf-8')
    assert 'demo_high_current' not in text
    assert '_high_current_approved' not in text
    assert "self.submit('demo_limit', value)" in text
    worker=(ROOT/'worker.py').read_text(encoding='utf-8')
    assert 'limit > DEMO_HIGH_CONFIRM_A' not in worker

def test_hover_gauge_has_no_popup_and_readout_is_on_right():
    src=(ROOT/'hud_widgets.py').read_text(encoding='utf-8')
    ast.parse(src)
    assert "self.setToolTip('')" in src
    assert "x = w * 0.58" in src
    assert 'value_text' in src

def test_8a_direct_write_preserves_other_current_parameters():
    w=SerialWorker(); w.client=FakeClient()
    before=w.client.current[2:]
    result=w._demo_limit(8)
    assert result['actual_A']==8
    assert w.client.current[2:]==before

def test_cannot_raise_above_overload_threshold():
    payload=(100).to_bytes(2,'little')+(200).to_bytes(2,'little')+(500).to_bytes(2,'little')
    with pytest.raises(ProtocolError, match='過載門檻'):
        demo_current_write(payload,3.0)

def test_motor_timing_protection_still_present():
    text=(ROOT/'main.py').read_text(encoding='utf-8')
    assert '每次最多 2 秒' in text
    assert 'I1 不是緊急停止' in text
