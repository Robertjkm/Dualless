"""Tema oscuro neón de Dualless v0.6.7 — paleta extraída del logo oficial
(Cyan eléctrico #38BDF8, Púrpura/Magenta #C026D3 y Naranja/Ámbar #F97316)."""

DARK_QSS = """
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    color: #F1EEF9;
}
QMainWindow, QWidget#centralWidget {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0.0 #0D111E,
        stop: 0.5 #151226,
        stop: 1.0 #1F1322
    );
}
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }

QWidget#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #101424, stop:1 #161124);
    border-right: 1px solid #2A2542;
}

QPushButton#navButton {
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: #AEB3CC;
    font-weight: 500;
}
QPushButton#navButton:hover {
    background-color: #1E1C33;
    color: #FFFFFF;
}
QPushButton#navButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1D2542, stop:0.6 #2D1B44, stop:1 #331B36);
    border-left: 3px solid #38BDF8;
    color: #FFFFFF;
    font-weight: 700;
}

QWidget#subNavBar {
    background-color: #131426;
    border-bottom: 1px solid #2C2645;
}
QPushButton#subNavButton {
    padding: 7px 12px;
    border: 1px solid #312B4D;
    border-radius: 8px;
    background-color: #1A182E;
    color: #B6B2CC;
    font-size: 12px;
    font-weight: 500;
}
QPushButton#subNavButton:hover {
    background-color: #252040;
    border-color: #38BDF8;
    color: #FFFFFF;
}
QPushButton#subNavButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7C3AED, stop:0.6 #C026D3, stop:1 #F97316);
    border-color: #F472B6;
    color: #FFFFFF;
    font-weight: 700;
}

QLabel#pageTitle { font-size: 20px; font-weight: 700; color: #FFFFFF; }
QLabel#pageSubtitle { color: #9CA0BA; }

QFrame#card {
    background-color: #181629;
    border: 1px solid #2D2847;
    border-radius: 12px;
}
QLabel#cardTitle { font-size: 14px; font-weight: 600; color: #FFFFFF; }

QSlider::groove:horizontal {
    height: 6px;
    background: #27233F;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #F97316;
    border: 2px solid #FFEDD5;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 9px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:0.55 #C026D3, stop:1 #F97316);
    border-radius: 3px;
}

QComboBox, QLineEdit, QSpinBox {
    background-color: #121222;
    border: 1px solid #302B4D;
    border-radius: 6px;
    padding: 5px 8px;
    color: #F1EEF9;
}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border-color: #38BDF8; }
QComboBox QAbstractItemView {
    background-color: #171529;
    border: 1px solid #3A325C;
    selection-background-color: #A855F7;
    color: #FFFFFF;
}

QListWidget {
    background-color: #121222;
    border: 1px solid #2E294A;
    border-radius: 8px;
    padding: 4px;
}
QListWidget::item { padding: 7px 9px; border-radius: 5px; }
QListWidget::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7C3AED, stop:1 #C026D3);
    color: #FFFFFF;
}
QListWidget::item:hover:!selected { background-color: #221E38; }

QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0EA5E9, stop:0.55 #A855F7, stop:1 #F97316);
    color: #FFFFFF;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 700;
    border: none;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:0.55 #C084FC, stop:1 #FB923C);
}
QPushButton#primary:disabled { background: #2D2942; color: #75728F; }

QPushButton#secondary {
    background-color: #1F1C33;
    color: #DCD8EC;
    border: 1px solid #352F54;
    border-radius: 8px;
    padding: 7px 14px;
}
QPushButton#secondary:hover {
    border-color: #38BDF8;
    color: #FFFFFF;
    background-color: #292442;
}

QPlainTextEdit#hexDump {
    background-color: #0B0D17;
    color: #38BDF8;
    font-family: "Consolas", "Courier New", monospace;
    border: 1px solid #2A2542;
    border-radius: 8px;
}

QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #373056; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #5B4C8A; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""

CONNECTION_COLORS = {
    "no_detectado": ("#FF5C7A", "Sin detectar"),
    "detectado": ("#F97316", "Detectado"),
    "abierto": ("#F97316", "Abierto"),
    "entrada_funcional": ("#38BDF8", "Entrada OK"),
    "salida_funcional": ("#22C55E", "Entrada y salida OK"),
    "error": ("#FF5C7A", "Error"),
}
