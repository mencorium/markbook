# /markbook/frontend/theme.py
"""Colours, palette and the Qt stylesheet. Same palette as the exported sheets and PDFs.

Call apply(app) at startup: Markbook always draws itself light, so a dark (or any other)
desktop theme can't leave dark text on a dark background in dialogs and popups.
"""
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

PAPER, SURFACE, INK, MUTED, RULE, GRID = "#F6F8FA", "#FFFFFF", "#16263D", "#56657A", "#DCE3EB", "#EDF1F5"
PEN, GREEN, AMBER, BLUE = "#C8322B", "#2E7D4F", "#A8691A", "#2458A6"
HEAT_LOW, HEAT_MID, HEAT_HIGH = "#F4D3D1", "#F3E3C8", "#D3EBDD"

QSS = f"""
QWidget {{ font-family: 'Segoe UI', 'Noto Sans', 'Helvetica Neue', Arial; font-size: 10.5pt; color: {INK}; }}
QMainWindow, #page {{ background: {PAPER}; }}
#sidebar {{ background: {SURFACE}; border: none; border-right: 1px solid {RULE}; padding: 14px 8px; outline: 0; }}
#sidebar::item {{ padding: 9px 12px; border-radius: 6px; color: {MUTED}; margin: 1px 0; }}
#sidebar::item:hover {{ background: {GRID}; color: {INK}; }}
#sidebar::item:selected {{ background: {GRID}; color: {INK}; font-weight: 600; border-left: 3px solid {PEN}; }}
#brand {{ font-size: 15pt; font-weight: 700; padding: 6px 12px 14px 12px; background: {SURFACE}; }}
#storeNote {{ color: {MUTED}; font-size: 9pt; padding: 8px 12px; background: {SURFACE}; }}
#title {{ font-size: 19pt; font-weight: 700; }}
#subtitle {{ color: {MUTED}; }}
#h2 {{ font-size: 12pt; font-weight: 700; }}
#muted {{ color: {MUTED}; }}
#note {{ background: {GRID}; border-left: 3px solid {AMBER}; padding: 8px 10px; border-radius: 4px; }}
#panel {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 10px; }}
#stat {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 10px; }}
#statValue {{ font-size: 16pt; font-weight: 700; }}
#statLabel {{ color: {MUTED}; font-size: 9pt; }}
#bigMark {{ font-size: 30pt; font-weight: 800; color: {PEN}; border: 3px solid {PEN}; border-radius: 42px; min-width: 84px; min-height: 84px; max-width: 84px; max-height: 84px; qproperty-alignment: AlignCenter; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 7px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {MUTED}; }}
QPushButton:disabled {{ color: #9aa5b3; }}
QPushButton#primary {{ background: {INK}; color: white; border-color: {INK}; font-weight: 600; }}
QPushButton#danger {{ color: {PEN}; }}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background: {PAPER}; border: 1px solid {RULE}; border-radius: 7px; padding: 6px 8px; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus {{ border-color: {BLUE}; }}
QTableWidget {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 8px; gridline-color: {GRID}; alternate-background-color: #F9FBFC; }}
QTableWidget::item:selected {{ background: #DCE7F5; color: {INK}; }}
QHeaderView::section {{ background: {INK}; color: white; font-weight: 600; padding: 6px; border: none; border-right: 1px solid #2c3d56; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: {SURFACE}; border: 1px solid {RULE}; padding: 7px 16px; margin-right: 4px; border-radius: 7px; }}
QTabBar::tab:selected {{ background: {INK}; color: white; }}
QScrollArea {{ border: none; background: transparent; }}
QDialog, QMessageBox, QInputDialog, QFileDialog, QColorDialog {{ background: {SURFACE}; }}
QDialog QLabel, QMessageBox QLabel, QGroupBox {{ background: transparent; color: {INK}; }}
QDialogButtonBox QPushButton {{ min-width: 92px; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; color: {INK}; border: 1px solid {RULE};
    selection-background-color: #DCE7F5; selection-color: {INK}; outline: 0; padding: 2px; }}
QMenu {{ background: {SURFACE}; color: {INK}; border: 1px solid {RULE}; }}
QMenu::item:selected {{ background: {GRID}; }}
QToolTip {{ background: {INK}; color: white; border: none; padding: 5px 7px; }}
QCalendarWidget QWidget {{ background: {SURFACE}; color: {INK}; alternate-background-color: {GRID}; }}
QCalendarWidget QAbstractItemView:enabled {{ background: {SURFACE}; color: {INK}; selection-background-color: {INK}; selection-color: white; }}
QCalendarWidget QToolButton {{ background: {SURFACE}; color: {INK}; }}
QCalendarWidget QSpinBox {{ background: {PAPER}; color: {INK}; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {PAPER}; border: none; width: 12px; height: 12px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: #C2CBD6; border-radius: 6px; min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; height: 0; width: 0; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
"""


def palette() -> QPalette:
    """Light palette, so widgets the stylesheet doesn't reach still read correctly."""
    p = QPalette()
    C = QPalette.ColorRole
    for role, colour in [(C.Window, PAPER), (C.WindowText, INK), (C.Base, SURFACE), (C.AlternateBase, GRID),
                         (C.Text, INK), (C.Button, SURFACE), (C.ButtonText, INK), (C.ToolTipBase, INK),
                         (C.ToolTipText, "#FFFFFF"), (C.PlaceholderText, MUTED), (C.Link, BLUE),
                         (C.Highlight, "#DCE7F5"), (C.HighlightedText, INK)]:
        p.setColor(role, QColor(colour))
    for group in (QPalette.ColorGroup.Disabled,):
        for role in (C.Text, C.ButtonText, C.WindowText):
            p.setColor(group, role, QColor("#9AA5B3"))
    return p


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")          # one consistent look on Windows, macOS and Linux
    app.setPalette(palette())
    app.setStyleSheet(QSS)