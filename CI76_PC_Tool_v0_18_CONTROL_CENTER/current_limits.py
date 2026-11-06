"""Single source of truth for CI76 PC Tool current-limit sliders.

These are LAB user-interface settings, not proof of an MCU or motor rating.
The 0 A minimum is based on the user's report of a firmware revision;
readback verification is always required to confirm device support.
"""
from decimal import Decimal

CURRENT_SLIDER_MIN_A = 0.00
CURRENT_SLIDER_MAX_A = 8.00
CURRENT_HIGH_CONFIRM_A = 2.00
CURRENT_TICKS_PER_AMP = 100


def amps_to_ticks(amps):
    return int(Decimal(str(amps)) * CURRENT_TICKS_PER_AMP)


def ticks_to_amps(ticks):
    return ticks / CURRENT_TICKS_PER_AMP


def within_slider_range(amps):
    return CURRENT_SLIDER_MIN_A <= amps <= CURRENT_SLIDER_MAX_A
