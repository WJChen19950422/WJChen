"""Readable horizontal current gauge. UART amps, NOT motor speed or force."""
from __future__ import annotations
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QColor, QFont


class CurrentDial(QWidget):
    """Left: analogue needle. Right: large 0.00 A current reading."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = None
        self._max = 8.0
        self.setMinimumSize(395, 178)
        self.setToolTip('UART 0x10 回報的估算馬達電流，單位 A；不是 RPM 或量測推力')

    def sizeHint(self):
        return QSize(530, 195)

    def setReading(self, value):
        self._value = None if value is None else float(value)
        self.update()

    def setMaximumAmps(self, value):
        self._max = max(0.1, float(value))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        # The arc occupies the left 40% and leaves a fixed digital-readout
        # area at the right. Use the widget dimensions, not hardcoded pixels.
        r = min(87.0, h * 0.415, w * 0.19)
        cx, cy = r + 20.0, h * 0.55
        arc = QRectF(cx-r, cy-r, r*2, r*2)
        bg = QPen(QColor('#DDE7EF'), 10)
        bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bg)
        p.drawArc(arc, 210*16, -240*16)
        if self._value is not None:
            fraction = max(0.0, min(1.0, abs(self._value) / self._max))
            fg_color = '#0E8CC5' if fraction < 0.8 else '#D67C25'
            fg = QPen(QColor(fg_color), 10)
            fg.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(fg)
            p.drawArc(arc, 210*16, round(-240*16*fraction))
            angle = math.radians(210 - 240*fraction)
            end = QPointF(cx + (r-18)*math.cos(angle),
                          cy - (r-18)*math.sin(angle))
            p.setPen(QPen(QColor('#203F58'), 3))
            p.drawLine(QPointF(cx, cy), end)
            p.setBrush(QColor('#203F58'))
            p.drawEllipse(QPointF(cx, cy), 4, 4)
        # Arc labels stay beneath the left dial; never overlap the big number.
        p.setPen(QColor('#506F86'))
        p.setFont(QFont('Segoe UI', 9))
        base_y = min(h-22.0, cy+r-8.0)
        p.drawText(QRectF(cx-r-4, base_y, r+2, 20),
                   Qt.AlignmentFlag.AlignLeft, '0 A')
        p.drawText(QRectF(cx, base_y, r+5, 20),
                   Qt.AlignmentFlag.AlignRight, f'{self._max:g} A')

        # Independent large digital readout, on the RIGHT of the analogue dial.
        right_x = cx + r + 36.0
        right_width = max(100.0, w-right_x-12.0)
        p.setPen(QColor('#5C7489'))
        p.setFont(QFont('Microsoft JhengHei', 10, QFont.Weight.Medium))
        p.drawText(QRectF(right_x, h*.17, right_width, 25),
                   Qt.AlignmentFlag.AlignLeft, '即時馬達電流')
        p.setPen(QColor('#11699D'))
        digit_size = 31 if right_width >= 210 else 25
        p.setFont(QFont('Segoe UI', digit_size, QFont.Weight.Bold))
        number = '—' if self._value is None else f'{self._value:.2f}'
        p.drawText(QRectF(right_x, h*.33, right_width, 69),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f'{number} A')
        p.setPen(QColor('#697F90'))
        p.setFont(QFont('Microsoft JhengHei', 9))
        p.drawText(QRectF(right_x, h*.72, right_width, 24),
                   Qt.AlignmentFlag.AlignLeft, 'MCU 回報值（A）')
        p.end()
