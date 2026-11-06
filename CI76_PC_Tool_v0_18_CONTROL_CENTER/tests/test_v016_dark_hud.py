from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]

def test_dark_hud_stylesheet_starts_without_stray_quote():
    s = (ROOT/'main.py').read_text(encoding='utf-8')
    # v0.18 moved both palettes into one theme; validate its actual QSS.
    theme = (ROOT/'theme.py').read_text(encoding='utf-8')
    ast.parse(theme)
    assert 'from theme import STYLESHEET, apply_theme' in s
    assert "page.setStyleSheet(" not in s
    assert 'QWidget#hudPage' in theme
    assert 'background:#0B1220' in theme
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
