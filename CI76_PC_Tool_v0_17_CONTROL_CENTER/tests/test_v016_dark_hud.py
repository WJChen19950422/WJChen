from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]

def test_dark_hud_stylesheet_starts_without_stray_quote():
    s = (ROOT/'main.py').read_text(encoding='utf-8')
    assert "HUD_STYLESHEET = r\'\'\'\n" in s
    assert "HUD_STYLESHEET = r\'\'\'\'" not in s
    assert 'background-color:#05090D' in s
    assert 'WA_StyledBackground' in s

def test_motor_art_removed_preserving_status():
    s = (ROOT/'main.py').read_text(encoding='utf-8')
    assert 'HudMotorVisual' not in s
    assert 'self.hud_motor_art' not in s
    assert "('MOTOR STATUS', 'hud_motor_state', 'NO DATA')" in s
    for needle in ('self.demo_current_dial = HudRingDial',
                   'self.hud_limit_dial = HudRingDial',
                   'self.demo_slider.valueChanged.connect',
                   'self.demo_current_bar', 'self.demo_target_spin'):
        assert needle in s
    ast.parse(s)
    ast.parse((ROOT/'hud_widgets.py').read_text(encoding='utf-8'))
