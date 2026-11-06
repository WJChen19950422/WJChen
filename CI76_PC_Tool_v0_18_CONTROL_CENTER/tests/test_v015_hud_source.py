"""Static HUD integration checks; runnable without PySide6 on CI."""
import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_both_gui_sources_parse():
    for name in ('main.py', 'hud_widgets.py'):
        ast.parse((ROOT / name).read_text(encoding='utf-8'))


def test_demo_preserves_existing_input_and_status_signals():
    s = (ROOT / 'main.py').read_text(encoding='utf-8')
    a = s[s.index('    def _build_demo_tab'):s.index('    def _update_demo_view', s.index('    def _build_demo_tab'))]
    for field in ('self.demo_slider', 'self.demo_target_spin', 'self.demo_restore_btn', 'self.demo_apply_btn', 'self.demo_current_dial',
                  'self.demo_current_bar', 'self.demo_sample_rate', 'self.demo_applied'):
        assert field in a
    assert 'self.demo_slider.valueChanged.connect(self._on_demo_slider_changed)' in a
    assert 'self.demo_target_spin.valueChanged.connect(self._demo_spin_to_slider)' in a
    assert 'self.demo_current_dial = HudRingDial' in a
    assert "self.hud_limit_dial = HudRingDial" in a


def test_hud_does_not_invent_motor_measurements():
    s = (ROOT / 'main.py').read_text(encoding='utf-8')
    assert '無 RPM 或推力實測' in s
    assert "self.hud_fault.setText(f'0x{bits[0]:02X} / 0x{bits[1]:02X}'" in s
    assert '回授／有效行程尚未驗證' in s
