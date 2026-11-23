from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.models import ConnectionState
from dualcontrol.ui.pages.compatibility_page import _BrandIconWidget
from dualcontrol.virtualcontroller.base import VirtualControllerMode


def _home_assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "dualcontrol" / "ui" / "assets"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent / "assets"


class _HomeIconWidget(QWidget):
    """Iconos limpios para Home: usa los PNG del menú lateral y trazos vectoriales
    nítidos para Adaptive Triggers, Diagnostics y Changelog (sin emojis)."""

    _ASSET_MAP = {
        "controller": "nav_controller.png",
        "profiles": "nav_profiles.png",
        "mods": "nav_mods.png",
        "settings": "nav_settings.png",
    }

    def __init__(self, kind: str, size: int = 22, color: str = "#EAE8F2", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._color = QColor(color)
        self.setFixedSize(size, size)
        self._pixmap: QPixmap | None = None
        fname = self._ASSET_MAP.get(kind)
        if fname:
            p = _home_assets_dir() / fname
            if p.exists():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    self._pixmap = pm

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._pixmap is not None:
            scaled = self._pixmap.scaled(
                self.width(),
                self.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            ox = (self.width() - scaled.width()) // 2
            oy = (self.height() - scaled.height()) // 2
            p.drawPixmap(ox, oy, scaled)
            return

        w, h = float(self.width()), float(self.height())
        p.scale(w / 24.0, h / 24.0)
        pen = QPen(self._color, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        if self._kind == "triggers":
            # Silueta de gatillo adaptativo (L2/R2) con onda de resistencia
            trig = QPainterPath()
            trig.moveTo(6.0, 5.0)
            trig.lineTo(15.5, 5.0)
            trig.cubicTo(18.5, 5.0, 19.5, 8.0, 18.0, 13.0)
            trig.cubicTo(16.8, 17.2, 14.0, 19.5, 11.0, 19.5)
            trig.lineTo(7.5, 19.5)
            trig.cubicTo(6.0, 19.5, 5.5, 18.0, 6.0, 16.0)
            trig.closeSubpath()
            p.drawPath(trig)
            # Pequeñas líneas de tensión dentro
            p.drawLine(QPointF(9.0, 9.5), QPointF(14.5, 9.5))
            p.drawLine(QPointF(9.0, 13.0), QPointF(13.5, 13.0))
            return

        if self._kind == "diagnostics":
            # Onda de pulso / diagnóstico de señal HID
            wave = QPainterPath()
            wave.moveTo(2.5, 12.5)
            wave.lineTo(6.5, 12.5)
            wave.lineTo(9.2, 5.5)
            wave.lineTo(13.0, 18.5)
            wave.lineTo(16.0, 10.5)
            wave.lineTo(18.0, 12.5)
            wave.lineTo(21.5, 12.5)
            p.drawPath(wave)
            return

        if self._kind == "changelog":
            # Documento con líneas de lista
            p.drawRoundedRect(QRectF(5.0, 3.0, 14.0, 18.0), 2.5, 2.5)
            p.drawLine(QPointF(8.5, 8.0), QPointF(15.5, 8.0))
            p.drawLine(QPointF(8.5, 12.0), QPointF(15.5, 12.0))
            p.drawLine(QPointF(8.5, 16.0), QPointF(13.0, 16.0))
            return


class _BatteryIcon(QWidget):
    """Icono vectorial compacto de batería con nivel de carga dinámico."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 12)
        self._level = 0
        self._charging = False

    def set_battery(self, level: int, charging: bool = False) -> None:
        self._level = max(0, min(100, int(level)))
        self._charging = bool(charging)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor("#22C55E") if self._level > 20 or self._charging else QColor("#FF5C7A")
        p.setPen(QPen(col, 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(1.0, 1.5, 15.0, 9.0), 2.0, 2.0)
        # Terminal positivo
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(16.8, 3.8, 2.2, 4.4), 0.8, 0.8)
        # Relleno proporcional
        fill_w = (self._level / 100.0) * 11.4
        if fill_w > 0.5:
            p.drawRoundedRect(QRectF(2.8, 3.2, fill_w, 5.6), 1.0, 1.0)


def _make_changelog_qicon() -> QIcon:
    pm = QPixmap(20, 20)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#C4B5FD"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawRoundedRect(QRectF(3.5, 2.0, 13.0, 16.0), 2.2, 2.2)
    p.drawLine(QPointF(6.5, 6.5), QPointF(13.5, 6.5))
    p.drawLine(QPointF(6.5, 10.0), QPointF(13.5, 10.0))
    p.drawLine(QPointF(6.5, 13.5), QPointF(11.0, 13.5))
    p.end()
    return QIcon(pm)


class _DualSensePreviewArt(QWidget):
    """Render limpio del DualSense (PNG transparente) alineado al borde derecho en Home."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(155, 175)
        self._led_color = QColor(46, 107, 255)
        self._pixmap: QPixmap | None = None
        img_path = _home_assets_dir() / "home_dualsense.png"
        if img_path.exists():
            pm = QPixmap(str(img_path))
            if not pm.isNull():
                self._pixmap = pm

    def set_led_color(self, r: int, g: int, b: int) -> None:
        self._led_color = QColor(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._pixmap is not None:
            scaled = self._pixmap.scaled(
                self.width(),
                self.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            ox = self.width() - scaled.width()
            oy = (self.height() - scaled.height()) // 2
            p.drawPixmap(ox, oy, scaled)


class _HeroBanner(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(185)
        self._logo: QPixmap | None = None
        lp = _home_assets_dir() / "app_logo.png"
        if lp.exists():
            pm = QPixmap(str(lp))
            if not pm.isNull():
                self._logo = pm

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        bg = QLinearGradient(r.left(), r.top(), r.right(), r.bottom())
        bg.setColorAt(0.0, QColor("#0A1628"))
        bg.setColorAt(0.48, QColor("#1F1338"))
        bg.setColorAt(0.82, QColor("#2D1533"))
        bg.setColorAt(1.0, QColor("#291716"))
        p.setPen(QPen(QColor("#A855F7"), 1.4))
        p.setBrush(bg)
        p.drawRoundedRect(r, 14, 14)

        cx, cy = r.width() * 0.56, r.height() * 0.48
        glow = QRadialGradient(cx, cy, r.height() * 0.85)
        glow.setColorAt(0.0, QColor(59, 130, 246, 95))
        glow.setColorAt(0.55, QColor(99, 102, 241, 45))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawRoundedRect(r, 14, 14)

        for rad, alpha, width in ((76, 130, 2.2), (52, 165, 1.8), (28, 120, 1.4)):
            p.setPen(QPen(QColor(96, 165, 250, alpha), width))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), rad, rad)

        bx, by = 24.0, r.height() - 68.0
        p.setPen(QPen(QColor("#8B5CF6"), 1.6))
        p.setBrush(QColor("#201D33"))
        p.drawRoundedRect(QRectF(bx, by, 44, 44), 10, 10)

        if self._logo is not None:
            scaled = self._logo.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(int(bx + (44 - scaled.width()) / 2), int(by + (44 - scaled.height()) / 2), scaled)

        p.setPen(QColor("#FFFFFF"))
        f_title = p.font()
        f_title.setPointSize(16)
        f_title.setBold(True)
        p.setFont(f_title)
        p.drawText(QRectF(82, by - 4, r.width() - 100, 26), Qt.AlignLeft | Qt.AlignVCenter, "Dualless")

        p.setPen(QColor("#CBD5E1"))
        f_sub = p.font()
        f_sub.setPointSize(10)
        f_sub.setBold(False)
        p.setFont(f_sub)
        p.drawText(QRectF(82, by + 20, r.width() - 100, 18), Qt.AlignLeft | Qt.AlignVCenter, "USB & Bluetooth Native Support")

        p.setPen(QColor("#FFFFFF"))
        f_bold = p.font()
        f_bold.setPointSize(10)
        f_bold.setBold(True)
        p.setFont(f_bold)
        p.drawText(QRectF(82, by + 37, r.width() - 100, 18), Qt.AlignLeft | Qt.AlignVCenter, "Adaptive Triggers • Haptic Feedback!")


class _QuickModePill(QFrame):
    clicked = Signal(object)

    def __init__(self, mode: VirtualControllerMode, icon_kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(_BrandIconWidget(icon_kind, size=20))
        self._apply_style()

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self.clicked.emit(self.mode)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._apply_style()

    def _apply_style(self) -> None:
        if self._active:
            color = "#16A34A" if self.mode == VirtualControllerMode.XINPUT else "#0057D9"
            border = "#22C55E" if self.mode == VirtualControllerMode.XINPUT else "#3B82F6"
            self.setStyleSheet(f"QFrame {{ background-color: {color}; border: 1.5px solid {border}; border-radius: 7px; }}")
        else:
            self.setStyleSheet("QFrame { background-color: #2A2538; border: 1px solid #3A334F; border-radius: 7px; }")


class _QuickNavTile(QFrame):
    clicked = Signal()

    def __init__(self, icon_kind: str, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { background-color: #231F2F; border: 1px solid #342D47; border-radius: 10px; }"
            "QFrame:hover { background-color: #2C263D; border-color: #8B5CF6; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        row.addWidget(_HomeIconWidget(icon_kind, size=22, color="#C4B5FD"))

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet("font-size: 11px; color: #9A93B0; background: transparent; border: none;")
        col.addWidget(t)
        col.addWidget(s)
        row.addLayout(col, 1)

        ch = QLabel("›")
        ch.setStyleSheet("font-size: 16px; color: #9A93B0; background: transparent; border: none;")
        row.addWidget(ch)

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self.clicked.emit()


class HomePage(QWidget):
    navigate_requested = Signal(str, str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._mode_pills: Dict[VirtualControllerMode, _QuickModePill] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        left_card = QFrame()
        left_card.setObjectName("card")
        left_card.setMinimumWidth(320)
        left_card.setMaximumWidth(370)
        l_lay = QVBoxLayout(left_card)
        l_lay.setContentsMargins(14, 12, 14, 14)
        l_lay.setSpacing(10)

        hdr = QHBoxLayout()
        self.conn_badge = QLabel("SIM")
        self.conn_badge.setStyleSheet(
            "background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; "
            "border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 700;"
        )

        # Insignia de batería con icono vectorial (sin emoji)
        bat_pill = QFrame()
        bat_pill.setStyleSheet(
            "QFrame { background-color: #14291F; border: 1px solid #1E4631; border-radius: 6px; }"
        )
        bat_lay = QHBoxLayout(bat_pill)
        bat_lay.setContentsMargins(6, 2, 7, 2)
        bat_lay.setSpacing(5)
        self.bat_icon = _BatteryIcon()
        self.bat_badge = QLabel("0%")
        self.bat_badge.setStyleSheet("color: #22C55E; font-size: 11px; font-weight: 700; border: none; background: transparent;")
        bat_lay.addWidget(self.bat_icon)
        bat_lay.addWidget(self.bat_badge)

        self.profile_title_lbl = QLabel("Default Profile")
        self.profile_title_lbl.setAlignment(Qt.AlignCenter)
        self.profile_title_lbl.setStyleSheet("font-weight: 700; color: #FFFFFF;")

        self.power_btn = QPushButton("⏻")
        self.power_btn.setFixedSize(28, 28)
        self.power_btn.setStyleSheet(
            "QPushButton { background-color: #2B1F2A; color: #FF5C7A; border: 1px solid #4A2B3E; border-radius: 6px; font-weight: 700; }"
            "QPushButton:hover { background-color: #3E273B; }"
        )
        self.power_btn.clicked.connect(self._toggle_connection)

        edit_quick_btn = QPushButton("↗")
        edit_quick_btn.setFixedSize(28, 28)
        edit_quick_btn.setObjectName("secondary")
        edit_quick_btn.setStyleSheet("padding: 0px;")
        edit_quick_btn.clicked.connect(lambda: self.navigate_requested.emit("Edit Controller", ""))

        hdr.addWidget(self.conn_badge)
        hdr.addWidget(bat_pill)
        hdr.addWidget(self.profile_title_lbl, 1)
        hdr.addWidget(self.power_btn)
        hdr.addWidget(edit_quick_btn)
        l_lay.addLayout(hdr)

        mid = QHBoxLayout()
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        self.ctrl_name_lbl = QLabel("DualSense™ Wireless\nController")
        self.ctrl_name_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #FFFFFF;")
        self.ctrl_id_lbl = QLabel("VID:054C · PID:0CE6")
        self.ctrl_id_lbl.setStyleSheet("font-size: 11px; color: #9A93B0;")
        self.backend_sub_lbl = QLabel("Backend: Simulado")
        self.backend_sub_lbl.setStyleSheet("font-size: 11px; color: #A78BFA;")
        info_col.addSpacing(10)
        info_col.addWidget(self.ctrl_name_lbl)
        info_col.addWidget(self.ctrl_id_lbl)
        info_col.addWidget(self.backend_sub_lbl)
        info_col.addStretch(1)
        mid.addLayout(info_col, 1)

        self.ds_art = _DualSensePreviewArt()
        mid.addWidget(self.ds_art)
        l_lay.addLayout(mid)

        vd_lbl = QLabel("Virtual Device")
        vd_lbl.setStyleSheet("font-weight: 700; font-size: 12px; color: #DCD7EA;")
        l_lay.addWidget(vd_lbl)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(6)
        for m_enum, icon_k in (
            (VirtualControllerMode.NATIVE, "native"),
            (VirtualControllerMode.XINPUT, "xbox"),
            (VirtualControllerMode.DUALSHOCK4, "ps_circle"),
            (VirtualControllerMode.DUALSENSE, "ps"),
        ):
            pill = _QuickModePill(m_enum, icon_k)
            pill.clicked.connect(self._on_quick_mode_clicked)
            self._mode_pills[m_enum] = pill
            pills_row.addWidget(pill, 1)
        l_lay.addLayout(pills_row)

        opts_box = QFrame()
        opts_box.setStyleSheet("QFrame { background-color: #191524; border: 1px solid #2F2940; border-radius: 10px; }")
        o_lay = QVBoxLayout(opts_box)
        o_lay.setContentsMargins(10, 10, 10, 10)
        o_lay.setSpacing(8)

        o_hdr = QLabel("Virtual Device Options")
        o_hdr.setAlignment(Qt.AlignCenter)
        o_hdr.setStyleSheet("font-weight: 700; color: #FFFFFF; border: none; background: transparent;")
        o_lay.addWidget(o_hdr)

        vd_open_btn = QPushButton("Virtual Device                                   ›")
        vd_open_btn.setObjectName("secondary")
        vd_open_btn.setStyleSheet("text-align: left; padding: 7px 10px;")
        vd_open_btn.clicked.connect(lambda: self.navigate_requested.emit("Edit Controller", "Game Compatibility"))
        o_lay.addWidget(vd_open_btn)

        krr_row = QHBoxLayout()
        krr_lbl = QLabel("Key Repeat Rate")
        krr_lbl.setStyleSheet("border: none; background: transparent; color: #D2CEE0; font-size: 12px;")
        self.home_krr_combo = QComboBox()
        self.home_krr_combo.addItems(["Do Not Repeat", "Slow Repetition", "Fast Repetition", "Native Keyboard"])
        self.home_krr_combo.currentTextChanged.connect(self.ctx.virtual_controller_service.set_key_repeat_rate)
        krr_row.addWidget(krr_lbl)
        krr_row.addWidget(self.home_krr_combo, 1)
        o_lay.addLayout(krr_row)

        fix_row = QHBoxLayout()
        fix_lbl = QLabel("Fix Double Input")
        fix_lbl.setStyleSheet("border: none; background: transparent; color: #D2CEE0; font-size: 12px;")
        fix_btn = QPushButton("↻ Reiniciar")
        fix_btn.setObjectName("secondary")
        fix_btn.setStyleSheet("padding: 4px 10px; font-size: 12px;")
        fix_btn.clicked.connect(self._fix_double_input)
        fix_row.addWidget(fix_lbl)
        fix_row.addStretch(1)
        fix_row.addWidget(fix_btn)
        o_lay.addLayout(fix_row)

        r_row = QHBoxLayout()
        r_lbl = QLabel("Rumble Passthrough")
        r_lbl.setStyleSheet("border: none; background: transparent; color: #D2CEE0; font-size: 12px;")
        self.home_rumble_check = QCheckBox("")
        self.home_rumble_check.setChecked(True)
        self.home_rumble_check.toggled.connect(self.ctx.virtual_controller_service.set_rumble_passthrough)
        r_row.addWidget(r_lbl)
        r_row.addStretch(1)
        r_row.addWidget(self.home_rumble_check)
        o_lay.addLayout(r_row)

        l_lay.addWidget(opts_box)
        top_row.addWidget(left_card)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        pill_row = QHBoxLayout()
        status_pill = QFrame()
        status_pill.setStyleSheet("QFrame { background-color: #1A1625; border: 1px solid #352E47; border-radius: 12px; }")
        sp_lay = QHBoxLayout(status_pill)
        sp_lay.setContentsMargins(12, 8, 12, 8)
        sp_lay.setSpacing(10)

        # Aro de estado con icono real del DualSense (sin emoji)
        self.pill_ring = QFrame()
        self.pill_ring.setFixedSize(38, 38)
        self.pill_ring.setStyleSheet(
            "QFrame { background-color: #13251D; border: 2px solid #22C55E; border-radius: 19px; }"
        )
        ring_lay = QHBoxLayout(self.pill_ring)
        ring_lay.setContentsMargins(0, 0, 0, 0)
        ring_lay.setAlignment(Qt.AlignCenter)
        ring_lay.addWidget(_HomeIconWidget("controller", size=22))
        sp_lay.addWidget(self.pill_ring)

        sp_text = QVBoxLayout()
        sp_text.setSpacing(1)
        self.pill_name = QLabel("DualSense™ Wireless Controller")
        self.pill_name.setStyleSheet("font-weight: 700; color: #FFFFFF; border: none; background: transparent;")
        self.pill_profile = QLabel("Default Profile")
        self.pill_profile.setStyleSheet("font-size: 11px; color: #C084FC; border: none; background: transparent;")
        self.pill_meta = QLabel("Conectando...")
        self.pill_meta.setStyleSheet("font-size: 11px; color: #9A93B0; border: none; background: transparent;")
        sp_text.addWidget(self.pill_name)
        sp_text.addWidget(self.pill_profile)
        sp_text.addWidget(self.pill_meta)
        sp_lay.addLayout(sp_text)

        self.pill_power_btn = QPushButton("⏻")
        self.pill_power_btn.setFixedSize(28, 28)
        self.pill_power_btn.setStyleSheet(
            "QPushButton { background-color: #2B1F2A; color: #FF5C7A; border: 1px solid #4A2B3E; border-radius: 6px; }"
            "QPushButton:hover { background-color: #3E273B; }"
        )
        self.pill_power_btn.clicked.connect(self._toggle_connection)
        sp_lay.addWidget(self.pill_power_btn)

        pill_row.addWidget(status_pill)

        # Selector Multi-Mando (P1..P4)
        multi_box = QFrame()
        multi_box.setStyleSheet("QFrame { background-color: #1A1625; border: 1px solid #352E47; border-radius: 12px; }")
        mb_lay = QHBoxLayout(multi_box)
        mb_lay.setContentsMargins(10, 8, 10, 8)
        mb_lay.setSpacing(6)
        mb_lbl = QLabel("Multi-Mando:")
        mb_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #9CA0BA; border: none; background: transparent;")
        mb_lay.addWidget(mb_lbl)
        self._slot_btns = []
        for slot_i in range(4):
            sb = QPushButton(f"P{slot_i + 1}")
            sb.setObjectName("subNavButton")
            sb.setCheckable(True)
            sb.setFixedSize(36, 28)
            sb.setChecked(slot_i == self.ctx.active_slot)
            sb.clicked.connect(lambda _c=False, idx=slot_i: self._on_slot_clicked(idx))
            self._slot_btns.append(sb)
            mb_lay.addWidget(sb)
        self.multi_count_lbl = QLabel("1 activo")
        self.multi_count_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #38BDF8; border: none; background: transparent;")
        mb_lay.addWidget(self.multi_count_lbl)
        pill_row.addWidget(multi_box)
        pill_row.addStretch(1)
        right_col.addLayout(pill_row)

        self.hero_banner = _HeroBanner()
        right_col.addWidget(self.hero_banner)

        quick_grid = QGridLayout()
        quick_grid.setSpacing(10)
        quick_items = [
            ("controller", "Edit Controller", "Mappings, triggers, haptics & LEDs.", "Edit Controller", "Controller Mappings"),
            ("profiles", "Profiles", "Manage and view your saved profiles.", "Profiles", ""),
            ("settings", "Settings", "Manage USB/BT backend & settings.", "Settings", ""),
            ("triggers", "Adaptive Triggers", "Customize L2/R2 weapon & vibration.", "Edit Controller", "Adaptive Triggers"),
            ("mods", "Mods (UDP)", "DSX UDP server & game mod portal.", "Mods", ""),
            ("diagnostics", "Diagnostics", "Inspect HID output reports & status.", "Edit Controller", "Diagnostics"),
        ]
        for idx, (ic_kind, t, s, sec, sub) in enumerate(quick_items):
            tile = _QuickNavTile(ic_kind, t, s)
            tile.clicked.connect(lambda _s=sec, _sub=sub: self.navigate_requested.emit(_s, _sub))
            quick_grid.addWidget(tile, idx // 3, idx % 3)
        right_col.addLayout(quick_grid)

        top_row.addLayout(right_col, 1)
        root.addLayout(top_row)

        self.update_card = QFrame()
        self.update_card.setObjectName("card")
        u_lay = QVBoxLayout(self.update_card)
        u_lay.setContentsMargins(16, 12, 16, 12)
        u_lay.setSpacing(10)

        u_top = QHBoxLayout()
        u_titles = QVBoxLayout()
        u_t = QLabel("Dualless Updated")
        u_t.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        u_s = QLabel("Check out what's new below!")
        u_s.setObjectName("pageSubtitle")
        u_titles.addWidget(u_t)
        u_titles.addWidget(u_s)
        u_top.addLayout(u_titles, 1)

        ver_lbl = QLabel("v1.4.0")
        ver_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #C084FC;")
        u_top.addWidget(ver_lbl)
        u_top.addStretch(1)

        dismiss_btn = QPushButton("✕  Dismiss")
        dismiss_btn.setObjectName("secondary")
        dismiss_btn.clicked.connect(lambda: self.update_card.setVisible(False))
        u_top.addWidget(dismiss_btn)
        u_lay.addLayout(u_top)

        self.changelog_btn = QPushButton("  Dualless Changelog")
        self.changelog_btn.setIcon(_make_changelog_qicon())
        self.changelog_btn.setIconSize(QSize(18, 18))
        self.changelog_btn.setObjectName("secondary")
        self.changelog_btn.setCheckable(True)
        self.changelog_btn.setStyleSheet("text-align: left; padding: 9px 14px;")
        self.changelog_btn.toggled.connect(self._toggle_changelog)
        u_lay.addWidget(self.changelog_btn)

        self.changelog_body = QLabel(
            "• v1.4.0: Gyro Pro (suavizado EMA, zona muerta, Yaw/Roll y botón de activación), Rapid Trigger + umbral ajustable de Hair Trigger / Dual Stage con tope táctil físico, enrutamiento Multi-Mando mejorado y scripts 1-clic compilar_onefile.bat / crear_iexpress.bat.\n"
            "• v1.3.0: Nivel 3 — LED Passthrough real en DualShock 4, Motor Rumble-to-Triggers (vibración → L2/R2), Escáner en vivo de conflictos HID (Steam/DSX/DS4Windows/reWASD) y plantilla WDK KMDF/VHF opcional.\n"
            "• v1.2.0: Nivel 2 completo — Gyro-to-Stick, Hair Trigger / Deadzone / Dual Stage en L2 y R2, Mapeo libre a Teclado/Ratón, Modo Turbo (2–25 Hz), Altavoz + Mute LED sincronizado y soporte DualSense Edge (Paddles y FN).\n"
            "• v1.1.0: Integración real con HidHide (solución definitiva al Double Input), Multi-Mando simultáneo P1–P4 en paralelo y Hápticos HD USB de 4 canales (canales 3–4 VCM).\n"
            "• v1.0.2: Reconectada la pestaña Input Monitor en Edit Controller y documentación actualizada (README, STATUS y THIRD_PARTY_NOTICES).\n"
            "• v1.0.1: Persistencia automática (settings.json), Macros y Atajos de Windows, Curvas de respuesta + Calibración Anti-Drift, Multi-Mando (P1–P4) e Instalador profesional de Windows (Dualless-Setup.exe).\n"
            "• v0.8.0: Bandeja del sistema (System Tray) e inicio con Windows, cambio automático de perfil por juego (.exe), alerta de batería baja, Touchpad como ratón, Gyro Aim y Audio To Rumble (WASAPI).\n"
            "• v0.7.0: Nuevo nombre oficial Dualless, recuperación automática tras desconexiones (restaura gatillos, hápticos y LEDs), pruebas directas en Diagnostics y compilador en 1 clic (compilar_exe.bat).\n"
            "• v0.6.8: Detección automática de DualSense (USB y Bluetooth) al abrir la app y al conectar/reconectar en caliente sin ir a Settings.\n"
            "• v0.6.7: Nuevo logo oficial de Dualless (ventana, barra lateral, banner Home e icono .ico) y paleta neón Cyan / Magenta / Naranja en toda la interfaz.\n"
            "• v0.6.6: Eliminados los emojis de Home y reemplazados por iconos limpios (PNG personalizados + iconos vectoriales para Batería, Adaptive Triggers, Diagnostics y Changelog).\n"
            "• v0.6.5: Imagen HD limpia del DualSense con transparencia en la tarjeta principal de Home.\n"
            "• v0.6.0–0.6.3: Soporte nativo de Bluetooth, nuevo Input Feedback DualSense, logos oficiales y menú lateral con iconos."
        )
        self.changelog_body.setWordWrap(True)
        self.changelog_body.setObjectName("pageSubtitle")
        self.changelog_body.setVisible(False)
        u_lay.addWidget(self.changelog_body)

        root.addWidget(self.update_card)
        root.addStretch(1)

        self.ctx.active_connection_changed.connect(self._on_connection_changed)
        self.ctx.active_state_changed.connect(self._on_state_changed)
        for slot in self.ctx.slots:
            s_idx = slot.slot_index
            slot.virtual_controller_service.mode_changed.connect(
                lambda m_val, idx=s_idx: self._on_virtual_mode_changed(m_val) if idx == self.ctx.active_slot else None
            )
        self.ctx.slot_changed.connect(self._on_slots_updated)
        self.ctx.profile_applied.connect(self._on_profile_applied)
        if self.ctx.lighting_engine is not None:
            self.ctx.lighting_engine.live_color_changed.connect(self.ds_art.set_led_color)

        self._on_virtual_mode_changed(self.ctx.virtual_controller_service.mode.value)
        self._on_connection_changed(self.ctx.controller_service.backend.connection_state)

    def _toggle_connection(self) -> None:
        state = self.ctx.controller_service.backend.connection_state
        if state in (ConnectionState.NOT_DETECTED, ConnectionState.ERROR):
            self.ctx.controller_service.connect_controller()
        else:
            self.ctx.controller_service.disconnect_controller()

    def _on_quick_mode_clicked(self, mode: VirtualControllerMode) -> None:
        ok = self.ctx.virtual_controller_service.set_mode(mode)
        if not ok:
            QMessageBox.warning(
                self,
                "Virtual Device",
                self.ctx.virtual_controller_service.last_error
                + "\n\nPuedes verificar o descargar ViGEmBus en Edit Controller → Game Compatibility.",
            )

    def _on_virtual_mode_changed(self, mode_value: str) -> None:
        for m, pill in self._mode_pills.items():
            pill.set_active(m.value == mode_value)

    def _fix_double_input(self) -> None:
        msg = self.ctx.fix_double_input_smart()
        QMessageBox.information(self, "Fix Double Input", msg)

    def _toggle_changelog(self, checked: bool) -> None:
        self.changelog_body.setVisible(checked)

    def _on_profile_applied(self, profile) -> None:
        name = profile.name or "Default Profile"
        self.profile_title_lbl.setText(name)
        self.pill_profile.setText(name)

    def _on_connection_changed(self, state: ConnectionState) -> None:
        connected = state in (ConnectionState.OPENED, ConnectionState.INPUT_OK, ConnectionState.OUTPUT_OK)
        ctype = getattr(self.ctx.controller_service.backend, "connection_type", "SIM")
        if not self.ctx.using_real_backend:
            ctype = "SIM"
        backend_txt = {"BT": "Bluetooth nativo", "USB": "USB nativo"}.get(ctype, "Simulado")
        self.conn_badge.setText(ctype if ctype in ("BT", "USB") else "SIM")
        self.backend_sub_lbl.setText(f"Backend: {backend_txt}")

        ring_col = "#22C55E" if connected else "#FF5C7A"
        ring_bg = "#13251D" if connected else "#2A151D"
        self.pill_ring.setStyleSheet(
            f"QFrame {{ background-color: {ring_bg}; border: 2px solid {ring_col}; border-radius: 19px; }}"
        )
        status_word = "Conectado" if connected else "Desconectado"
        self.pill_meta.setText(f"{backend_txt} · {status_word}")

    def _on_state_changed(self, state) -> None:
        lvl = int(state.battery_level)
        charging = bool(state.battery_charging)
        self.bat_icon.set_battery(lvl, charging)
        self.bat_badge.setText(f"{lvl}%{' (Cargando)' if charging else ''}")
        ctype = getattr(self.ctx.controller_service.backend, "connection_type", "SIM")
        backend_txt = ctype if (self.ctx.using_real_backend and ctype in ("BT", "USB")) else "SIM"
        self.pill_meta.setText(f"VID:054C:0CE6 · {backend_txt} · Bat {lvl}%")

    def _on_slot_clicked(self, slot_idx: int) -> None:
        self.ctx.select_controller_slot(slot_idx)
        self._on_virtual_mode_changed(self.ctx.virtual_controller_service.mode.value)

    def _on_slots_updated(self, active_idx: int, total_real: int) -> None:
        for i, btn in enumerate(self._slot_btns):
            btn.setChecked(i == active_idx)
            connected = self.ctx.slot_is_connected(i)
            btn.setToolTip(f"Jugador {i + 1}: {'Conectado' if connected else 'Libre'}")
        shown = max(1, total_real)
        self.multi_count_lbl.setText(f"{shown} activo" if shown == 1 else f"{shown} activos")
