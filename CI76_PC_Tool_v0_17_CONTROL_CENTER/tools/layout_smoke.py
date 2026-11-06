r"""GUI layout screenshots for both CI76 tabs, without connecting UART.

From a Windows PowerShell opened at the project folder:
  .\.venv\Scripts\python.exe tools\layout_smoke.py
Optional CI offscreen mode:
  .\.venv\Scripts\python.exe tools\layout_smoke.py --offscreen
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

if '--offscreen' in sys.argv:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from main import CI76Window

app = QApplication(sys.argv)
win = CI76Window()
win.resize(1260, 840)
win.show()
app.processEvents()

def save_tabs():
    for idx, file_name in enumerate(('CI76_v0_17_page1.png','CI76_v0_17_page2.png')):
        win.tabs.setCurrentIndex(idx)
        app.processEvents()
        path = PROJECT_DIR / file_name
        if win.grab().save(str(path)):
            print('Saved', path)
        else:
            print('Screenshot failed:', path)
        print('Tab', idx, 'Window', win.width(), 'x', win.height())
        if idx == 0:
            print('Page1 vertical-scroll range:', win.main_scroll.verticalScrollBar().maximum())
        else:
            print('Demo vertical-scroll range:', win.demo_tab.verticalScrollBar().maximum())
    win.close()
    app.quit()

QTimer.singleShot(400, save_tabs)
raise SystemExit(app.exec())
