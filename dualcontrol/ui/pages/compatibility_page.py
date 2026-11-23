from __future__ import annotations

from collections import deque
from pathlib import Path
import sys
from typing import Dict

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.services.conflict_scanner import format_conflicts_report, scan_live_conflicts
from dualcontrol.services.hidhide_service import HIDHIDE_DOWNLOAD_URL
from dualcontrol.ui.widgets import Card, LabeledSlider
from dualcontrol.virtualcontroller.base import VirtualControllerMode
from dualcontrol.virtualcontroller.mapper import XInputSnapshot
from dualcontrol.virtualcontroller.xinput_vigem import VIGEMBUS_DOWNLOAD_URL


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "dualcontrol" / "ui" / "assets"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent / "assets"


class _BrandIconWidget(QWidget):
    """Iconos oficiales de marca (PNG con transparencia) para Xbox, DualShock 4 y DualSense,
    más icono vectorial para Native Mode."""

    _ICON_FILES = {
        "xbox": "xbox.png",
        "ps_circle": "ds4.png",
        "ps": "dualsense.png",
    }

    def __init__(self, kind: str, size: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind  # "native" | "xbox" | "ps_circle" | "ps"
        self.setFixedSize(size, size)
        self._pixmap: QPixmap | None = None
        fname = self._ICON_FILES.get(kind)
        if fname:
            path = _assets_dir() / fname
            if path.exists():
                pm = QPixmap(str(path))
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

        # Fallback / Native Mode (mando tachado)
        w, h = float(self.width()), float(self.height())
        p.scale(w / 24.0, h / 24.0)
        pen = QPen(QColor("#FFFFFF"), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(4, 8, 16, 9), 4, 4)
        p.drawLine(QPointF(4, 4), QPointF(20, 20))


class _DeviceModeButton(QFrame):
    """Tarjeta seleccionable de modo en la columna izquierda (Native, Xbox 360, DS4, DualSense)."""

    clicked = Signal(object)

    def __init__(self, mode: VirtualControllerMode, icon_text: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self._active = False
        self.setCursor(Qt.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        icon_w = _BrandIconWidget(icon_text, size=24)
        row.addWidget(icon_w)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-weight: 700; font-size: 13px; background: transparent; border: none; color: #FFFFFF;")
        row.addWidget(title_lbl, 1)

        chev = QLabel("›")
        chev.setStyleSheet("font-size: 16px; color: #C6C1D6; background: transparent; border: none;")
        row.addWidget(chev)

        self._apply_style()

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self.clicked.emit(self.mode)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._apply_style()

    def _apply_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                "QFrame { background-color: #0057D9; border: 1.5px solid #3B82F6; border-radius: 10px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background-color: #211D2C; border: 1px solid #332C46; border-radius: 10px; }"
            )


class _ToggleRowCard(QFrame):
    """Tarjeta horizontal con título, descripción y casilla de activación a la derecha."""

    toggled = Signal(bool)

    def __init__(self, title: str, description: str, *, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background-color: #211D2C; border: 1px solid #332C46; border-radius: 10px; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(2)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        d_lbl = QLabel(description)
        d_lbl.setWordWrap(True)
        d_lbl.setStyleSheet("font-size: 12px; color: #A6A0B8; background: transparent; border: none;")
        col.addWidget(t_lbl)
        col.addWidget(d_lbl)
        row.addLayout(col, 1)

        self.checkbox = QCheckBox("")
        self.checkbox.setChecked(checked)
        self.checkbox.toggled.connect(self.toggled.emit)
        row.addWidget(self.checkbox)


class CompatibilityPage(QWidget):
    """Sección Game Compatibility / Virtual Device (v0.4.8):
    Native Mode, Xbox 360 Emulation, DualShock 4 Emulation, DualSense Emulation,
    Fix Double Input, Key Repeat Rate y Live Incoming Virtual Device Data Feed."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._mode_buttons: Dict[VirtualControllerMode, _DeviceModeButton] = {}
        self._feed_buffer: deque[str] = deque(maxlen=100)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(14)

        # Cabecera superior
        title = QLabel("Virtual Device")
        title.setObjectName("pageTitle")
        subtitle = QLabel("The Virtual Device is what the computer will think you're using instead of your physical controller.")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        # Dos columnas principales
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # ==================== COLUMNA IZQUIERDA ====================
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        modes_defs = [
            (VirtualControllerMode.NATIVE, "native", "Native Mode"),
            (VirtualControllerMode.XINPUT, "xbox", "Xbox 360 Emulation"),
            (VirtualControllerMode.DUALSHOCK4, "ps_circle", "DualShock 4 Emulation"),
            (VirtualControllerMode.DUALSENSE, "ps", "DualSense Emulation"),
        ]
        for mode_enum, icon_txt, label_txt in modes_defs:
            btn = _DeviceModeButton(mode_enum, icon_txt, label_txt)
            btn.clicked.connect(self._on_mode_clicked)
            self._mode_buttons[mode_enum] = btn
            left_col.addWidget(btn)

        # Fix Double Input
        fix_card = QFrame()
        fix_card.setStyleSheet(
            "QFrame { background-color: #211D2C; border: 1px solid #332C46; border-radius: 10px; }"
        )
        fix_row = QHBoxLayout(fix_card)
        fix_row.setContentsMargins(14, 12, 14, 12)
        fix_row.setSpacing(10)
        fix_col = QVBoxLayout()
        fix_t = QLabel("Fix Double Input")
        fix_t.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        fix_d = QLabel(
            "Attempts to restart the controller connection cleanly to avoid double input. "
            "Controller may briefly disconnect/reconnect."
        )
        fix_d.setWordWrap(True)
        fix_d.setStyleSheet("font-size: 12px; color: #A6A0B8; background: transparent; border: none;")
        fix_col.addWidget(fix_t)
        fix_col.addWidget(fix_d)
        fix_row.addLayout(fix_col, 1)

        self.fix_btn = QPushButton("↻ Reiniciar")
        self.fix_btn.setObjectName("secondary")
        self.fix_btn.clicked.connect(self._fix_double_input)
        fix_row.addWidget(self.fix_btn)
        left_col.addWidget(fix_card)

        # Key Repeat Rate
        krr_card = QFrame()
        krr_card.setStyleSheet(
            "QFrame { background-color: #211D2C; border: 1px solid #332C46; border-radius: 10px; }"
        )
        krr_lay = QVBoxLayout(krr_card)
        krr_lay.setContentsMargins(14, 12, 14, 12)
        krr_lay.setSpacing(8)
        krr_t = QLabel("Key Repeat Rate")
        krr_t.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        krr_d = QLabel(
            "Set the repeat speed for keyboard mapping actions when a button is held."
        )
        krr_d.setWordWrap(True)
        krr_d.setStyleSheet("font-size: 12px; color: #A6A0B8; background: transparent; border: none;")
        self.krr_combo = QComboBox()
        self.krr_combo.addItems(["Do Not Repeat", "Slow Repetition", "Fast Repetition", "Native Keyboard"])
        self.krr_combo.currentTextChanged.connect(self.ctx.virtual_controller_service.set_key_repeat_rate)
        krr_lay.addWidget(krr_t)
        krr_lay.addWidget(krr_d)
        krr_lay.addWidget(self.krr_combo)
        left_col.addWidget(krr_card)

        # Live Incoming Virtual Device Data Feed
        feed_card = QFrame()
        feed_card.setStyleSheet(
            "QFrame { background-color: #211D2C; border: 1px solid #332C46; border-radius: 10px; }"
        )
        feed_lay = QVBoxLayout(feed_card)
        feed_lay.setContentsMargins(14, 12, 14, 12)
        feed_lay.setSpacing(8)
        feed_top = QHBoxLayout()
        feed_col = QVBoxLayout()
        feed_t = QLabel("Live Incoming Virtual Device Data Feed")
        feed_t.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        feed_d = QLabel("Shows most recent 100 entries of incoming/outgoing Virtual Device data for debugging.")
        feed_d.setWordWrap(True)
        feed_d.setStyleSheet("font-size: 12px; color: #A6A0B8; background: transparent; border: none;")
        feed_note = QLabel("NOTE: Entries only show up if you are on this page for performance reasons.")
        feed_note.setWordWrap(True)
        feed_note.setStyleSheet("font-size: 11px; color: #F59E0B; background: transparent; border: none;")
        feed_col.addWidget(feed_t)
        feed_col.addWidget(feed_d)
        feed_col.addWidget(feed_note)
        feed_top.addLayout(feed_col, 1)

        self.feed_toggle = QCheckBox("")
        self.feed_toggle.toggled.connect(self._on_feed_toggled)
        feed_top.addWidget(self.feed_toggle)
        feed_lay.addLayout(feed_top)

        self.feed_view = QPlainTextEdit()
        self.feed_view.setObjectName("hexDump")
        self.feed_view.setReadOnly(True)
        self.feed_view.setMaximumHeight(120)
        self.feed_view.setVisible(False)
        feed_lay.addWidget(self.feed_view)
        left_col.addWidget(feed_card)

        left_col.addStretch(1)
        cols.addLayout(left_col, 5)

        # ==================== COLUMNA DERECHA (PANEL DINÁMICO) ====================
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        self.config_stack = QStackedWidget()
        self.config_stack.addWidget(self._build_native_panel())      # 0
        self.config_stack.addWidget(self._build_xbox_panel())        # 1
        self.config_stack.addWidget(self._build_ds4_panel())         # 2
        self.config_stack.addWidget(self._build_dualsense_panel())   # 3
        right_col.addWidget(self.config_stack)

        # Tarjeta compartida de requisitos ViGEmBus + Estado actual
        req_card = Card("Estado y requisitos de emulación (ViGEmBus)")
        self.status_label = QLabel("Native Mode activo — DualSense físico sin emulación")
        self.status_label.setStyleSheet("font-weight: 600; color: #35D07F;")
        self.status_label.setWordWrap(True)
        req_card.add(self.status_label)

        self.prereq_label = QLabel("Verificando...")
        self.prereq_label.setObjectName("pageSubtitle")
        self.prereq_label.setWordWrap(True)
        req_card.add(self.prereq_label)

        req_btns = QHBoxLayout()
        verify_btn = QPushButton("Verificar ViGEmBus")
        verify_btn.setObjectName("secondary")
        verify_btn.clicked.connect(self._refresh_prerequisites)
        dl_btn = QPushButton("Descargar ViGEmBus oficial")
        dl_btn.setObjectName("secondary")
        dl_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(VIGEMBUS_DOWNLOAD_URL)))
        req_btns.addWidget(verify_btn)
        req_btns.addWidget(dl_btn)
        req_btns.addStretch(1)
        req_card.add_layout(req_btns)
        right_col.addWidget(req_card)

        # Tarjeta HidHide (Solución definitiva contra Double Input en Xbox 360 / DS4)
        hh_card = Card("HidHide — Ocultar DualSense físico (Anti-Double Input)")
        self.hh_status_label = QLabel("Verificando HidHide...")
        self.hh_status_label.setObjectName("pageSubtitle")
        self.hh_status_label.setWordWrap(True)
        hh_card.add(self.hh_status_label)

        self.auto_hh_check = QCheckBox(
            "Ocultar automáticamente el DualSense físico al activar Xbox 360 o DualShock 4"
        )
        self.auto_hh_check.setChecked(self.ctx.auto_hidhide)
        self.auto_hh_check.toggled.connect(self.ctx.set_auto_hidhide)
        hh_card.add(self.auto_hh_check)

        hh_btns = QHBoxLayout()
        hh_hide_btn = QPushButton("Ocultar mando físico")
        hh_hide_btn.setObjectName("primary")
        hh_hide_btn.clicked.connect(self._on_hidhide_hide)

        hh_unhide_btn = QPushButton("Mostrar mando físico")
        hh_unhide_btn.setObjectName("secondary")
        hh_unhide_btn.clicked.connect(self._on_hidhide_unhide)

        hh_dl_btn = QPushButton("Descargar HidHide oficial")
        hh_dl_btn.setObjectName("secondary")
        hh_dl_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HIDHIDE_DOWNLOAD_URL)))

        hh_btns.addWidget(hh_hide_btn)
        hh_btns.addWidget(hh_unhide_btn)
        hh_btns.addWidget(hh_dl_btn)
        hh_btns.addStretch(1)
        hh_card.add_layout(hh_btns)
        right_col.addWidget(hh_card)

        # Tarjeta Detector de Conflictos HID en vivo (v1.3.0)
        conf_card = Card("Detector de conflictos HID en vivo (Steam Input / DSX / DS4Windows / reWASD)")
        self.conflict_label = QLabel("Pulsa 'Escanear conflictos' para revisar procesos activos en Windows.")
        self.conflict_label.setObjectName("pageSubtitle")
        self.conflict_label.setWordWrap(True)
        conf_card.add(self.conflict_label)

        conf_btns = QHBoxLayout()
        scan_btn = QPushButton("Escanear conflictos ahora")
        scan_btn.setObjectName("secondary")
        scan_btn.clicked.connect(self._scan_conflicts)
        conf_btns.addWidget(scan_btn)
        conf_btns.addStretch(1)
        conf_card.add_layout(conf_btns)
        right_col.addWidget(conf_card)

        right_col.addStretch(1)
        cols.addLayout(right_col, 6)
        root.addLayout(cols)

        # Conectar señales de todos los slots (P1..P4)
        for slot in self.ctx.slots:
            s_idx = slot.slot_index
            slot.virtual_controller_service.status_changed.connect(
                lambda act, msg, idx=s_idx: self._on_status_changed(act, msg) if idx == self.ctx.active_slot else None
            )
            slot.virtual_controller_service.preview_updated.connect(
                lambda snap, idx=s_idx: self._on_preview_updated(snap) if idx == self.ctx.active_slot else None
            )
            slot.virtual_controller_service.data_feed_logged.connect(
                lambda line, idx=s_idx: self._on_feed_entry(line) if idx == self.ctx.active_slot else None
            )
        self.ctx.slot_changed.connect(self._on_slot_changed)
        self.ctx.hidhide_service.status_changed.connect(lambda _st: self._refresh_prerequisites())

        self._select_mode_ui(self.ctx.virtual_controller_service.mode)
        self._refresh_prerequisites()
        self._scan_conflicts()

    # --- Constructores de paneles derechos -------------------------------------
    def _build_header_box(self, title: str, subtitle: str, icon_kind: str = "ps") -> QFrame:
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background-color: #241F32; border: 1px solid #352E47; border-radius: 12px; }"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(6)
        icon_row = QHBoxLayout()
        icon_row.addStretch(1)
        icon_row.addWidget(_BrandIconWidget(icon_kind, size=32))
        icon_row.addStretch(1)
        lay.addLayout(icon_row)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF; border: none; background: transparent;")
        s = QLabel(subtitle)
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        s.setStyleSheet("font-size: 12px; color: #A6A0B8; border: none; background: transparent;")
        lay.addWidget(t)
        lay.addWidget(s)
        return box

    def _build_native_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(
            self._build_header_box(
                "Native Mode Configuration",
                "Uses your physical Sony DualSense directly without virtual device emulation.",
                icon_kind="native",
            )
        )
        info = Card("Modo Nativo (Sin emulación)")
        lbl = QLabel(
            "Recomendado para juegos de PC con soporte nativo de PlayStation 5 (como mods HID directos "
            "o juegos recientes). Evita doble entrada y conserva todas las funciones USB del DualSense."
        )
        lbl.setWordWrap(True)
        lbl.setObjectName("pageSubtitle")
        info.add(lbl)
        lay.addWidget(info)
        return w

    def _build_xbox_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(
            self._build_header_box(
                "Xbox 360 Mode Configuration",
                "When Xbox 360 Emulation is active, games see a standard XInput Xbox 360 controller.",
                icon_kind="xbox",
            )
        )
        self.xbox_rumble_row = _ToggleRowCard(
            "Rumble Passthrough",
            "When enabled, vibration sent by Xbox/XInput games is passed to your DualSense motors.",
            checked=True,
        )
        self.xbox_rumble_row.toggled.connect(lambda c: self.ctx.virtual_controller_service.set_rumble_passthrough(c))
        lay.addWidget(self.xbox_rumble_row)

        self.xbox_r2t_row = _ToggleRowCard(
            "Rumble-to-Triggers (Vibración → Gatillos L2/R2)",
            "Convierte en tiempo real la vibración de juegos Xbox/XInput en pulsos y retroceso físico en los gatillos adaptativos.",
            checked=self.ctx.virtual_controller_service.rumble_to_triggers,
        )
        self.xbox_r2t_row.toggled.connect(self._on_r2t_toggled)
        lay.addWidget(self.xbox_r2t_row)

        self.xbox_r2t_strength = LabeledSlider(
            "Intensidad de Rumble-to-Triggers (%)",
            minimum=25,
            maximum=150,
            value=int(round(self.ctx.virtual_controller_service.rumble_to_triggers_strength * 100)),
        )
        self.xbox_r2t_strength.valueChanged.connect(self._on_r2t_strength_changed)
        lay.addWidget(self.xbox_r2t_strength)

        self.xbox_preview_card = Card("Salida en vivo — Xbox 360 (XInput)")
        self.xbox_preview_label = QLabel("Activa Xbox 360 Emulation para ver la salida en vivo.")
        self.xbox_preview_label.setObjectName("pageSubtitle")
        self.xbox_preview_label.setWordWrap(True)
        self.xbox_preview_card.add(self.xbox_preview_label)
        lay.addWidget(self.xbox_preview_card)
        return w

    def _build_ds4_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(
            self._build_header_box(
                "DualShock 4 Mode Configuration",
                "When DualShock 4 Emulation is active, games see a PlayStation 4 controller via ViGEmBus.",
                icon_kind="ps_circle",
            )
        )
        self.ds4_rumble_row = _ToggleRowCard(
            "Rumble Passthrough",
            "When enabled, vibration sent to the virtual DualShock 4 is passed to your DualSense.",
            checked=True,
        )
        self.ds4_rumble_row.toggled.connect(self.ctx.virtual_controller_service.set_rumble_passthrough)
        lay.addWidget(self.ds4_rumble_row)

        self.ds4_led_row = _ToggleRowCard(
            "LED Passthrough (Real vía ViGEmBus)",
            "Aplica en vivo a tu DualSense (USB o Bluetooth) los colores RGB que envíen los juegos al mando virtual DualShock 4 (ej. GTA V, Cyberpunk).",
            checked=self.ctx.virtual_controller_service.led_passthrough,
        )
        self.ds4_led_row.toggled.connect(self._on_ds4_led_toggled)
        lay.addWidget(self.ds4_led_row)

        self.ds4_r2t_row = _ToggleRowCard(
            "Rumble-to-Triggers (Vibración → Gatillos L2/R2)",
            "Convierte la vibración enviada al DualShock 4 virtual en retroceso físico en L2 y R2.",
            checked=self.ctx.virtual_controller_service.rumble_to_triggers,
        )
        self.ds4_r2t_row.toggled.connect(self._on_r2t_toggled)
        lay.addWidget(self.ds4_r2t_row)
        return w

    def _build_dualsense_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(
            self._build_header_box(
                "DualSense Mode Configuration",
                "When DualSense Emulation is active, you can adjust the passthrough options below.",
                icon_kind="ps",
            )
        )

        # Selector: sin audio vs con audio
        audio_row = QHBoxLayout()
        audio_row.setSpacing(10)
        self._ds_audio_group = QButtonGroup(self)
        self._ds_audio_group.setExclusive(True)

        self.btn_ds_no_audio = QPushButton("DualSense Emulation\n🔇 Audio Device")
        self.btn_ds_no_audio.setObjectName("subNavButton")
        self.btn_ds_no_audio.setCheckable(True)
        self.btn_ds_no_audio.setChecked(True)
        self.btn_ds_no_audio.clicked.connect(lambda: self.ctx.virtual_controller_service.set_dualsense_audio_device(False))

        self.btn_ds_audio = QPushButton("DualSense Emulation\n🔊 Audio Device")
        self.btn_ds_audio.setObjectName("subNavButton")
        self.btn_ds_audio.setCheckable(True)
        self.btn_ds_audio.clicked.connect(lambda: self.ctx.virtual_controller_service.set_dualsense_audio_device(True))

        self._ds_audio_group.addButton(self.btn_ds_no_audio, 0)
        self._ds_audio_group.addButton(self.btn_ds_audio, 1)
        audio_row.addWidget(self.btn_ds_no_audio, 1)
        audio_row.addWidget(self.btn_ds_audio, 1)
        lay.addLayout(audio_row)

        self.ds_rumble_row = _ToggleRowCard(
            "Rumble Passthrough",
            "When enabled, the vibration sent to the virtual DualSense controller will get passed to this device.",
            checked=True,
        )
        self.ds_rumble_row.toggled.connect(self.ctx.virtual_controller_service.set_rumble_passthrough)
        lay.addWidget(self.ds_rumble_row)

        self.ds_triggers_row = _ToggleRowCard(
            "Adaptive Triggers Passthrough",
            "When enabled, the adaptive triggers sent to the virtual DualSense controller will get passed to this device.",
            checked=True,
        )
        self.ds_triggers_row.toggled.connect(self.ctx.virtual_controller_service.set_triggers_passthrough)
        lay.addWidget(self.ds_triggers_row)

        self.ds_led_row = _ToggleRowCard(
            "LED Passthrough",
            "When enabled, the Light Bar colors sent to the virtual DualSense controller will get passed to this device.",
            checked=False,
        )
        self.ds_led_row.toggled.connect(self.ctx.virtual_controller_service.set_led_passthrough)
        lay.addWidget(self.ds_led_row)

        note = QLabel(
            "Nota técnica (honesta): ViGEmBus solo emula Xbox 360 y DualShock 4. DualSense Emulation opera en "
            "Modo Passthrough Nativo. Para desarrollo avanzado con WDK (Test Signing Mode), consulta la plantilla "
            "C++ KMDF/VHF incluida en driver_vhf_template/README_WDK.md."
        )
        note.setWordWrap(True)
        note.setObjectName("pageSubtitle")
        lay.addWidget(note)
        return w

    # --- Lógica e interacción --------------------------------------------------
    def _select_mode_ui(self, mode: VirtualControllerMode) -> None:
        for m, btn in self._mode_buttons.items():
            btn.set_active(m == mode)
        idx_map = {
            VirtualControllerMode.NATIVE: 0,
            VirtualControllerMode.XINPUT: 1,
            VirtualControllerMode.DUALSHOCK4: 2,
            VirtualControllerMode.DUALSENSE: 3,
        }
        self.config_stack.setCurrentIndex(idx_map.get(mode, 0))

    def _on_mode_clicked(self, mode: VirtualControllerMode) -> None:
        ok = self.ctx.virtual_controller_service.set_mode(mode)
        self._refresh_prerequisites()
        if ok:
            self._select_mode_ui(mode)
        else:
            self._select_mode_ui(VirtualControllerMode.NATIVE)
            QMessageBox.warning(
                self,
                "No se pudo activar la emulación",
                self.ctx.virtual_controller_service.last_error
                + "\n\nPuedes pulsar 'Descargar ViGEmBus oficial' para instalar el driver manualmente.",
            )

    def _on_slot_changed(self, _slot_idx: int, _total: int) -> None:
        self._select_mode_ui(self.ctx.virtual_controller_service.mode)

    def _on_hidhide_hide(self) -> None:
        ok, msg = self.ctx.apply_hidhide_now()
        self._refresh_prerequisites()
        if ok:
            QMessageBox.information(self, "HidHide activado", msg)
        else:
            QMessageBox.warning(self, "HidHide", msg)

    def _on_hidhide_unhide(self) -> None:
        self.ctx.hidhide_service.unhide_all()
        self._refresh_prerequisites()
        QMessageBox.information(self, "HidHide desactivado", "El DualSense físico vuelve a ser visible en Windows.")

    def _fix_double_input(self) -> None:
        msg = self.ctx.fix_double_input_smart()
        self._refresh_prerequisites()
        QMessageBox.information(self, "Fix Double Input", msg)

    def _on_feed_toggled(self, enabled: bool) -> None:
        self.ctx.virtual_controller_service.set_feed_enabled(enabled)
        self.feed_view.setVisible(enabled)

    def _on_feed_entry(self, line: str) -> None:
        if not self.isVisible() or not self.feed_toggle.isChecked():
            return
        self._feed_buffer.append(line)
        self.feed_view.setPlainText("\n".join(self._feed_buffer))
        sb = self.feed_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_prerequisites(self) -> None:
        info = self.ctx.virtual_controller_service.check_prerequisites()
        vg_mark = "✅" if info.vgamepad_installed else "❌"
        drv_mark = "✅" if info.vigembus_driver_detected else "❌"
        vhf_mark = "✅" if info.dualless_vhf_detected else "⬜"
        self.prereq_label.setText(
            f"{vg_mark} Biblioteca vgamepad  ·  {drv_mark} Driver ViGEmBus  ·  {vhf_mark} Driver VHF experimental\n{info.summary}"
        )
        hh = self.ctx.hidhide_service.check_status()
        hh_mark = "✅" if hh.installed else "⬜"
        cloak_txt = " · Ocultamiento ACTIVO" if hh.cloak_active else ""
        self.hh_status_label.setText(f"{hh_mark} HidHide{cloak_txt}\n{hh.summary}")

    def _on_status_changed(self, active: bool, message: str) -> None:
        color = "#35D07F" if active else "#AEB4C2"
        self.status_label.setStyleSheet(f"font-weight: 600; color: {color};")
        self.status_label.setText(message)

    def _on_preview_updated(self, snap: XInputSnapshot) -> None:
        pressed = ", ".join(snap.pressed_labels()) or "(ninguno)"
        self.xbox_preview_label.setText(
            f"Botones: {pressed}\n"
            f"Gatillos: LT={snap.left_trigger} · RT={snap.right_trigger}\n"
            f"Stick Izq: ({snap.left_x}, {snap.left_y}) · Stick Der: ({snap.right_x}, {snap.right_y})"
        )

    def _on_r2t_toggled(self, enabled: bool) -> None:
        self.ctx.virtual_controller_service.set_rumble_to_triggers(enabled)
        self.xbox_r2t_row.checkbox.blockSignals(True)
        self.xbox_r2t_row.checkbox.setChecked(enabled)
        self.xbox_r2t_row.checkbox.blockSignals(False)
        self.ds4_r2t_row.checkbox.blockSignals(True)
        self.ds4_r2t_row.checkbox.setChecked(enabled)
        self.ds4_r2t_row.checkbox.blockSignals(False)
        self.ctx.save_settings()

    def _on_r2t_strength_changed(self, value: int) -> None:
        self.ctx.virtual_controller_service.set_rumble_to_triggers_strength(value / 100.0)
        self.ctx.save_settings()

    def _on_ds4_led_toggled(self, enabled: bool) -> None:
        self.ctx.virtual_controller_service.set_led_passthrough(enabled)
        self.ctx.save_settings()

    def _scan_conflicts(self) -> None:
        conflicts = scan_live_conflicts()
        self.conflict_label.setText(format_conflicts_report(conflicts))
