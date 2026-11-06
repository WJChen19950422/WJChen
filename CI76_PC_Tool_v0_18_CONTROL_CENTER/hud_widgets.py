"""Midnight Tech Blue presentation widgets for the CI76 live Demo.

All displayed amperes are supplied by the existing CI76 UART protocol.
The display contains measured current and a user-configured limit only.
"""
from __future__ import annotations
import math
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QBrush
from PySide6.QtWidgets import QWidget
from theme import COLORS

CYAN = QColor(COLORS['telemetry'])
MINT = QColor(COLORS['ok'])
MUTED = QColor(COLORS['secondary'])
DARK = QColor(COLORS['app'])
AMBER = QColor(COLORS['warn'])


class HudRingDial(QWidget):
    """Instrument-style gauge, NOT an RPM or force sensor."""
    def __init__(self, caption='ACTUAL CURRENT', parent=None):
        super().__init__(parent)
        self.caption = caption
        self._value: float | None = None
        self._maximum = 8.0
        self.setMinimumSize(190, 196)
        self.setToolTip('')  # Avoid dark Windows tooltip stripe over the live gauge.

    def sizeHint(self):
        return QSize(245, 226)

    def setReading(self, value):
        self._value = None if value is None else float(value)
        self.update()

    def setMaximumAmps(self, value):
        self._maximum = max(0.1, float(value))
        self.update()

    def paintEvent(self, _event):
        # Compact GPU-monitor style: dial on the left, high-contrast value on right.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        cx, cy = w * 0.30, h * 0.52
        r = min(w * 0.24, h * 0.38, 106.0)
        rect = QRectF(cx-r, cy-r, 2*r, 2*r)
        p.setPen(QPen(QColor(COLORS['border']), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 220*16, -260*16)
        for n in range(27):
            angle = math.radians(220 - n*10)
            major = n % 5 == 0
            inside = r - (16 if major else 10)
            outside = r - 4
            p.setPen(QPen(QColor(COLORS['secondary'] if major else COLORS['border']), 1.7 if major else 1))
            p.drawLine(QPointF(cx + inside*math.cos(angle), cy - inside*math.sin(angle)),
                       QPointF(cx + outside*math.cos(angle), cy - outside*math.sin(angle)))
        if self._value is not None:
            fraction = max(0., min(1., abs(self._value)/self._maximum))
            accent = AMBER if fraction > .9 else CYAN
            p.setPen(QPen(accent, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 220*16, round(-260*16*fraction))
            angle = math.radians(220-260*fraction)
            endpoint = QPointF(cx+(r-24)*math.cos(angle), cy-(r-24)*math.sin(angle))
            p.setPen(QPen(QColor(COLORS['text']), 2.7))
            p.drawLine(QPointF(cx, cy), endpoint)
            p.setBrush(CYAN)
            p.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
        p.setPen(MUTED)
        p.setFont(QFont('Segoe UI', 8))
        p.drawText(QRectF(cx-r, cy+r*.61, r, 22), Qt.AlignmentFlag.AlignLeft, '0 A')
        p.drawText(QRectF(cx, cy+r*.61, r, 22), Qt.AlignmentFlag.AlignRight, f'{self._maximum:g} A')
        x = w * 0.58
        right = max(60., w-x-5)
        p.setPen(MUTED)
        p.setFont(QFont('Segoe UI', 9, QFont.Weight.DemiBold))
        # Wrap captions instead of clipping them on smaller displays.
        p.drawText(QRectF(x, h*.18, right, h*.18),
                   Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self.caption)
        p.setPen(CYAN if self._value is not None else MUTED)
        p.setFont(QFont('Segoe UI', 29 if w>410 else 23, QFont.Weight.Bold))
        value_text = '—' if self._value is None else f'{self._value:.2f}'
        p.drawText(QRectF(x, h*.36, right, 60),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f'{value_text} A')
        p.setPen(MUTED)
        p.setFont(QFont('Segoe UI', 9))
        p.drawText(QRectF(x, h*.67, right, 26),
                   Qt.AlignmentFlag.AlignLeft, f'RANGE   0.00 – {self._maximum:.2f} A')
        p.end()
