"""One Midnight Tech Blue theme for application, popups and painted meters."""
from pathlib import Path
from PySide6.QtGui import QColor, QFont, QPalette, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QListView

COLORS = dict(app='#0B1220', card='#141E2D', control='#1B293C', hover='#253750',
              border='#2B3D55', primary='#3BA7FF', telemetry='#40D3BF',
              text='#ECF3FA', secondary='#94A9BC', ok='#2DCE9B',
              warn='#FFBD59', error='#FF6375')

STYLESHEET = '''
QWidget { color:#ECF3FA; font-family:"Segoe UI","Microsoft JhengHei",sans-serif; font-size:9pt; }
QMainWindow, QWidget#centralRoot, QWidget#settingsPage, QWidget#settingsContent,
QWidget#hudPage, QScrollArea, QScrollArea > QWidget > QWidget { background:#0B1220; }
QFrame#brandBar, QFrame#hudPanel, QFrame#hudStatusPanel {
 background:#141E2D; border:1px solid #2B3D55; border-radius:8px; }
QLabel { background:transparent; }
QLabel#brandWord { color:#ECF3FA; font:800 18pt "Segoe UI"; }
QLabel#heroTitle, QLabel#hudHeading { color:#ECF3FA; font:700 12pt "Segoe UI"; }
QLabel#brandDetail, QLabel#hudCaption { color:#94A9BC; }
QLabel#buildTag { color:#3BA7FF; font-weight:600; }
QLabel#hudNum { color:#40D3BF; font:700 24pt "Segoe UI"; }
QLabel#hudStatus { color:#ECF3FA; font-weight:600; }
QGroupBox { background:#141E2D; border:1px solid #2B3D55; border-radius:8px;
 margin-top:13px; padding:5px 4px 4px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; color:#94A9BC; }
QPushButton { background:#1B293C; border:1px solid #2B3D55; border-radius:6px;
 padding:3px 8px; min-height:24px; }
QPushButton:hover { background:#253750; border-color:#3BA7FF; }
QPushButton:pressed { background:#2B3D55; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
 border:1px solid #3BA7FF; }
QPushButton#primary { background:#3BA7FF; color:#0B1220; font-weight:700; }
QPushButton#primary:hover { background:#83C8FF; }
QPushButton#stopButton { background:#722D40; color:#ECF3FA; border-color:#FF6375; font-weight:700; }
QPushButton#stopButton:hover { background:#98374C; }
QPushButton#primary:disabled, QPushButton#stopButton:disabled {
 background:#141E2D; color:#73879B; border-color:#2B3D55; }
QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
 background:#141E2D; color:#73879B; border-color:#2B3D55; }
QComboBox, QSpinBox, QDoubleSpinBox { background:#1B293C; border:1px solid #2B3D55;
 border-radius:5px; padding:2px 5px; min-height:24px;
 selection-background-color:#3BA7FF; selection-color:#0B1220; }
QComboBox::drop-down { border:0; width:20px; }
QSpinBox#compactEditor, QDoubleSpinBox#compactEditor { min-height:20px; padding:1px 5px; }
QComboBox QAbstractItemView { background:#1B293C; color:#ECF3FA; border:1px solid #3BA7FF;
 selection-background-color:#3BA7FF; selection-color:#0B1220; outline:0; }
QAbstractItemView::item { padding:6px; }
QAbstractItemView::item:selected, QAbstractItemView::item:hover {
 background:#3BA7FF; color:#0B1220; }
QCheckBox { spacing:5px; }
QCheckBox::indicator { width:14px; height:14px; border-radius:3px; }
QCheckBox::indicator:unchecked { background:#1B293C; border:1px solid #94A9BC; }
QCheckBox::indicator:checked { background:#3BA7FF; border:1px solid #3BA7FF; }
QCheckBox:disabled { color:#73879B; }
QTabWidget::pane { border:1px solid #2B3D55; background:#0B1220; }
QTabBar::tab { background:#141E2D; color:#94A9BC; padding:6px 16px; }
QTabBar::tab:selected { color:#ECF3FA; background:#1B293C; border-top:2px solid #3BA7FF; }
QTabBar::tab:hover { background:#253750; }
QProgressBar { background:#1B293C; border:1px solid #2B3D55; border-radius:4px;
 min-height:10px; max-height:12px; }
QProgressBar::chunk { background:#40D3BF; border-radius:3px; }
QProgressBar#positionBar::chunk { background:#3BA7FF; }
QSlider::groove:horizontal { background:#2B3D55; height:6px; border-radius:3px; }
QSlider::sub-page:horizontal { background:#3BA7FF; border-radius:3px; }
QSlider::handle:horizontal { background:#ECF3FA; border:2px solid #3BA7FF;
 width:14px; margin:-6px 0; border-radius:8px; }
QSlider { background:transparent; }
QSlider::sub-page:horizontal:disabled { background:#2B3D55; }
QSlider::add-page:horizontal { background:#2B3D55; border-radius:3px; }
QPlainTextEdit { background:#0B1220; color:#94A9BC; border:1px solid #2B3D55; font:9pt Consolas; }
QScrollArea { border:0; }
QScrollBar:vertical { background:#141E2D; width:10px; }
QScrollBar::handle:vertical { background:#2B3D55; min-height:24px; border-radius:4px; }
QScrollBar:horizontal { background:#141E2D; height:10px; }
QScrollBar::handle:horizontal { background:#2B3D55; min-width:24px; border-radius:4px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QStatusBar { background:#141E2D; color:#94A9BC; }
QMessageBox, QDialog { background:#141E2D; }
QToolTip { background:#1B293C; color:#ECF3FA; border:1px solid #3BA7FF; padding:5px; }
'''


def apply_theme(app=None):
    app = app or QApplication.instance()
    app.setStyle('Fusion')  # Deterministic Qt popup; avoid native light-theme leakage.
    palette = QPalette()
    for role, color in [('Window', 'app'), ('WindowText', 'text'), ('Base', 'control'),
                        ('AlternateBase', 'card'), ('Text', 'text'), ('Button', 'control'),
                        ('ButtonText', 'text'), ('Highlight', 'primary'),
                        ('HighlightedText', 'app'), ('ToolTipBase', 'control'),
                        ('ToolTipText', 'text'), ('PlaceholderText', 'secondary')]:
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(COLORS[color]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#73879B'))
    app.setPalette(palette)
    app.setFont(QFont('Segoe UI', 9))
    app.setStyleSheet(STYLESHEET)


def configure_port_popup(combo):
    view = QListView(combo)
    view.setMouseTracking(True)
    combo.setView(view)
    combo.setMinimumContentsLength(18)
    combo.setSizeAdjustPolicy(combo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)


def brand_label():
    label = QLabel('MOTECK')
    label.setObjectName('brandWord')
    for name in ('moteck_logo.svg', 'moteck_logo.png'):
        path = Path(__file__).resolve().parent / 'assets' / name
        if path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                dpr = label.devicePixelRatioF()
                scaled = pixmap.scaledToHeight(round(32 * dpr), Qt.TransformationMode.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                label.setPixmap(scaled)
                break
    return label
