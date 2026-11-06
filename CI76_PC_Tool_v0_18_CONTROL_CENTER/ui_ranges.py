"""Qt-free display constraints for CI76 parameter editors.

Do not confuse a UI-readable historical default with a firmware-writable
range. Validation of writes remains the responsibility of protocol.build_write.
"""
from protocol import FIELDS

# Factory/old regenerative thresholds can read as 52/51 V. Keep readable.
LEGACY_DISPLAY_MAX = {'brake_on': 60.0, 'brake_off': 60.0}


def field_editor_spec(key: str) -> tuple[float, float, int, float]:
    """Return (min, max, decimals, single_step) for a QSpinBox/DoubleSpinBox.

    Position soft limits have 1% effective resolution in 2026-11-04 firmware:
    ctl.c divides incoming deci-percent by 10 using integer arithmetic.
    """
    _, _, scale, _, maximum = FIELDS[key]
    high = max(float(maximum), LEGACY_DISPLAY_MAX.get(key, float(maximum)))
    if scale == 1:
        return (0, int(high), 0, 1)
    if key in ('pos_max', 'pos_min'):
        return (0.0, 100.0, 0, 1.0)
    decimals = 2 if scale == 100 else 1
    step = 0.01 if scale == 100 else 0.1
    return (0.0, high, decimals, step)
