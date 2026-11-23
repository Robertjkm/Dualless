from __future__ import annotations

from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.models import TriggerMode, TriggerSettings
from dualcontrol.services.diagnostics import hex_dump
from dualcontrol.ui.widgets import Card


def _scale_0_8_to_byte(val: int) -> int:
    v = max(0, min(8, int(val)))
    return int(round((v / 8.0) * 255))


class _ParamSliderRow(QFrame):
    """Fila estilizada con etiqueta, valor numérico a la derecha y slider horizontal."""

    valueChanged = Signal(int)

    def __init__(
        self,
        label: str,
        *,
        minimum: int,
        maximum: int,
        value: int,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._suffix = suffix
        self.setStyleSheet(
            "QFrame { background-color: #231F2E; border: 1px solid #352E47; border-radius: 8px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("border: none; background: transparent; font-weight: 600; color: #EAE8F2;")
        self._val_lbl = QLabel(f"{value}{suffix}")
        self._val_lbl.setStyleSheet("border: none; background: transparent; font-weight: 700; color: #FFFFFF;")
        top.addWidget(lbl)
        top.addStretch(1)
        top.addWidget(self._val_lbl)
        layout.addLayout(top)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setValue(value)
        self._slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self._slider)

    def _on_changed(self, value: int) -> None:
        self._val_lbl.setText(f"{value}{self._suffix}")
        self.valueChanged.emit(value)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value: int) -> None:
        self._slider.setValue(value)


class _TriggerModeCard(QFrame):
    """Tarjeta desplegable tipo acordeón para un modo de gatillo adaptativo."""

    selected = Signal(str)
    changed = Signal()

    def __init__(
        self,
        mode_key: str,
        title: str,
        description: str,
        params: List[Tuple[str, int, int, int, str]],
        *,
        extra_toggle: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode_key = mode_key
        self.sliders: List[_ParamSliderRow] = []
        self.extra_checkbox: QCheckBox | None = None
        self._is_selected = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Cabecera clicable
        self._header = QFrame()
        self._header.setCursor(Qt.PointingHandCursor)
        h_row = QHBoxLayout(self._header)
        h_row.setContentsMargins(12, 10, 12, 10)
        h_row.setSpacing(10)

        self.radio = QRadioButton()
        self.radio.setAutoExclusive(False)
        self.radio.clicked.connect(lambda: self.selected.emit(self.mode_key))
        h_row.addWidget(self.radio, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        self._desc_lbl = QLabel(description)
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet("font-size: 12px; color: #A6A0B8; background: transparent; border: none;")
        text_col.addWidget(self._title_lbl)
        text_col.addWidget(self._desc_lbl)
        h_row.addLayout(text_col, 1)

        self._chevron = QLabel("⌄" if params or extra_toggle else "")
        self._chevron.setStyleSheet("color: #A6A0B8; font-size: 14px; background: transparent; border: none;")
        h_row.addWidget(self._chevron)

        self._header.mousePressEvent = self._on_header_click  # type: ignore[assignment]
        outer.addWidget(self._header)

        # Cuerpo desplegable con sliders
        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(12, 6, 12, 12)
        body_layout.setSpacing(8)

        for label, lo, hi, default_val, suffix in params:
            row = _ParamSliderRow(label, minimum=lo, maximum=hi, value=default_val, suffix=suffix)
            row.valueChanged.connect(lambda _v: self.changed.emit())
            self.sliders.append(row)
            body_layout.addWidget(row)

        if extra_toggle:
            cb_frame = QFrame()
            cb_frame.setStyleSheet(
                "QFrame { background-color: #231F2E; border: 1px solid #352E47; border-radius: 8px; }"
            )
            cb_layout = QVBoxLayout(cb_frame)
            cb_layout.setContentsMargins(12, 8, 12, 8)
            self.extra_checkbox = QCheckBox(extra_toggle)
            self.extra_checkbox.toggled.connect(lambda _c: self.changed.emit())
            cb_layout.addWidget(self.extra_checkbox)
            body_layout.addWidget(cb_frame)

        self._body.setVisible(False)
        outer.addWidget(self._body)
        self._apply_card_style()

    def _on_header_click(self, _event) -> None:
        self.selected.emit(self.mode_key)

    def set_selected(self, active: bool) -> None:
        self._is_selected = active
        self.radio.setChecked(active)
        has_body = bool(self.sliders or self.extra_checkbox)
        self._body.setVisible(active and has_body)
        if has_body:
            self._chevron.setText("⌃" if active else "⌄")
        self._apply_card_style()

    def _apply_card_style(self) -> None:
        if self._is_selected:
            self.setStyleSheet(
                "QFrame { background-color: #2A223B; border: 1.5px solid #8B5CF6; border-radius: 10px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background-color: #1D1A27; border: 1px solid #2F2940; border-radius: 10px; }"
            )


class TriggerColumnEditor(QWidget):
    """Columna independiente para L2 (Left Trigger) o R2 (Right Trigger) con modos
    oficiales y no oficiales desplegables y aplicación en tiempo real."""

    applied = Signal()

    def __init__(
        self,
        badge_text: str,
        title_text: str,
        side_code: str,
        ctx: AppContext,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.side_code = side_code  # "L2" o "R2"
        self.ctx = ctx
        self._cards: Dict[str, _TriggerModeCard] = {}
        self._active_mode_key = "off"
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # Cabecera de columna (Badge L2/R2 + Título)
        hdr = QFrame()
        hdr.setStyleSheet(
            "QFrame { background-color: #241F32; border: 1px solid #352E47; border-radius: 10px; }"
        )
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(14, 10, 14, 10)
        hdr_row.setSpacing(10)

        badge = QLabel(badge_text)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(30, 24)
        badge.setStyleSheet(
            "background-color: #EAE8F2; color: #16131F; border-radius: 6px; font-weight: 800; font-size: 12px;"
        )
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF; border: none; background: transparent;")
        hdr_row.addWidget(badge)
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch(1)
        root.addWidget(hdr)

        # Sección: Official Adaptive Trigger Modes
        sec1 = QLabel("Official Adaptive Trigger Modes")
        sec1.setStyleSheet("font-weight: 700; color: #DCD7EA; margin-top: 2px;")
        root.addWidget(sec1)

        official_defs = [
            ("off", "OFF", "Turns off the Adaptive Trigger effect, and returns the trigger back to normal.", [], None),
            (
                "feedback",
                "Feedback",
                "The trigger will resist movement beyond the start position.",
                [
                    ("Start Position", 0, 9, 2, ""),
                    ("Resistance Strength", 0, 8, 6, ""),
                ],
                None,
            ),
            (
                "weapon",
                "Weapon",
                "The trigger will resist with a snap type feeling.",
                [
                    ("Start Position", 2, 7, 2, ""),
                    ("End Position", 3, 8, 6, ""),
                    ("Resistance Strength", 0, 8, 8, ""),
                ],
                None,
            ),
            (
                "vibration",
                "Vibration",
                "The trigger will vibrate with the input amplitude and frequency beyond the start position.",
                [
                    ("Start Position", 0, 9, 1, ""),
                    ("Amplitude", 0, 8, 8, ""),
                    ("Frequency", 1, 100, 10, " Hz"),
                ],
                "Dynamic Rumble Sync — sincroniza la vibración con la intensidad de los motores",
            ),
            (
                "slope_feedback",
                "Slope Feedback",
                "The trigger will resist movement at a linear range of strengths.",
                [
                    ("Start Position", 0, 8, 1, ""),
                    ("End Position", 1, 9, 7, ""),
                    ("Start Strength", 0, 8, 2, ""),
                    ("End Strength", 0, 8, 8, ""),
                ],
                None,
            ),
            (
                "multi_feedback",
                "Multiple Position Feedback",
                "The trigger will resist movement at varying strengths in 10 regions.",
                [
                    ("Zone 1 Strength", 0, 8, 2, ""),
                    ("Zone 2 Strength", 0, 8, 5, ""),
                    ("Zone 3 Strength", 0, 8, 8, ""),
                ],
                None,
            ),
            (
                "multi_vibration",
                "Multiple Position Vibration",
                "The trigger will vibrate movement at varying amplitudes and one frequency in 10 regions.",
                [
                    ("Frequency", 1, 100, 18, " Hz"),
                    ("Zone 1 Amplitude", 0, 8, 4, ""),
                    ("Zone 2 Amplitude", 0, 8, 8, ""),
                ],
                None,
            ),
        ]

        for key, title, desc, params, toggle in official_defs:
            card = _TriggerModeCard(key, title, desc, params, extra_toggle=toggle)
            card.selected.connect(self._on_mode_selected)
            card.changed.connect(self._apply_live)
            self._cards[key] = card
            root.addWidget(card)

        # Sección: Unofficial Adaptive Trigger Modes
        sec2 = QLabel("Unofficial Adaptive Trigger Modes")
        sec2.setStyleSheet("font-weight: 700; color: #DCD7EA; margin-top: 6px;")
        root.addWidget(sec2)

        unofficial_defs = [
            (
                "bow",
                "Bow",
                "Simulates pulling a bowstring with tension and a snap-back release.",
                [
                    ("Start Position", 0, 8, 1, ""),
                    ("End Position", 1, 8, 6, ""),
                    ("Pull Force", 0, 8, 4, ""),
                    ("Snap Force", 0, 8, 7, ""),
                ],
                None,
            ),
            (
                "galloping",
                "Galloping",
                "Rhythmic two-step pulse sensation along the trigger travel.",
                [
                    ("Start Position", 0, 8, 0, ""),
                    ("End Position", 1, 9, 8, ""),
                    ("Frequency", 1, 60, 12, " Hz"),
                ],
                None,
            ),
            (
                "machine",
                "Machine",
                "Rapid mechanical alternating pulse ideal for automatic weapons.",
                [
                    ("Start Position", 0, 8, 1, ""),
                    ("Strength A", 0, 8, 6, ""),
                    ("Strength B", 0, 8, 8, ""),
                    ("Frequency", 1, 100, 30, " Hz"),
                ],
                None,
            ),
        ]

        for key, title, desc, params, toggle in unofficial_defs:
            card = _TriggerModeCard(key, title, desc, params, extra_toggle=toggle)
            card.selected.connect(self._on_mode_selected)
            card.changed.connect(self._apply_live)
            self._cards[key] = card
            root.addWidget(card)

        root.addStretch(1)
        self._select_card("off", apply_now=False)

    @property
    def sliders(self) -> List[_ParamSliderRow]:
        """Compatibilidad con tests existentes: devuelve los sliders de la tarjeta activa."""
        card = self._cards.get(self._active_mode_key)
        return card.sliders if card is not None else []

    def _apply_preset(self, preset_name: str) -> None:
        """Compatibilidad con tests existentes y presets rápidos."""
        key = preset_name.lower()
        if key not in self._cards:
            key = "off"
        self._select_card(key, apply_now=True)

    def _on_mode_selected(self, mode_key: str) -> None:
        self._select_card(mode_key, apply_now=True)

    def _select_card(self, mode_key: str, *, apply_now: bool) -> None:
        self._active_mode_key = mode_key
        for k, card in self._cards.items():
            card.set_selected(k == mode_key)
        if apply_now and not self._syncing:
            self._apply_live()

    def build_settings(self) -> TriggerSettings:
        """Traduce el modo y sliders activos a TriggerSettings válidos para el protocolo HID."""
        key = self._active_mode_key
        card = self._cards[key]
        vals = [s.value() for s in card.sliders]

        if key == "off":
            return TriggerSettings(enabled=False, mode=TriggerMode.OFF, forces=[0] * 7, preset_name="off")

        if key == "feedback":
            start, strength = vals[0], _scale_0_8_to_byte(vals[1])
            return TriggerSettings(
                enabled=strength > 0, mode=TriggerMode.RIGID,
                forces=[start, strength, 0, 0, 0, 0, 0], preset_name="feedback",
            ).clamp()

        if key == "weapon":
            start, end, strength = vals[0], vals[1], _scale_0_8_to_byte(vals[2])
            return TriggerSettings(
                enabled=strength > 0, mode=TriggerMode.PULSE,
                forces=[start, strength, end, 0, 0, 0, 0], preset_name="weapon",
            ).clamp()

        if key == "vibration":
            start, amp, freq = vals[0], _scale_0_8_to_byte(vals[1]), vals[2]
            return TriggerSettings(
                enabled=amp > 0, mode=TriggerMode.PULSE_AB,
                forces=[freq, amp, start, 0, 0, 0, 0], preset_name="vibration",
            ).clamp()

        if key == "slope_feedback":
            start, end, s1, s2 = vals[0], vals[1], _scale_0_8_to_byte(vals[2]), _scale_0_8_to_byte(vals[3])
            return TriggerSettings(
                enabled=True, mode=TriggerMode.RIGID_A,
                forces=[start, s1, end, s2, 0, 0, 0], preset_name="slope_feedback",
            ).clamp()

        if key == "multi_feedback":
            z1, z2, z3 = _scale_0_8_to_byte(vals[0]), _scale_0_8_to_byte(vals[1]), _scale_0_8_to_byte(vals[2])
            return TriggerSettings(
                enabled=True, mode=TriggerMode.RIGID_AB,
                forces=[1, z1, 4, z2, 7, z3, 0], preset_name="multi_feedback",
            ).clamp()

        if key == "multi_vibration":
            freq, a1, a2 = vals[0], _scale_0_8_to_byte(vals[1]), _scale_0_8_to_byte(vals[2])
            return TriggerSettings(
                enabled=True, mode=TriggerMode.PULSE_AB,
                forces=[freq, a1, 1, 5, a2, 0, 0], preset_name="multi_vibration",
            ).clamp()

        if key == "bow":
            start, end, pull, snap = vals[0], vals[1], _scale_0_8_to_byte(vals[2]), _scale_0_8_to_byte(vals[3])
            return TriggerSettings(
                enabled=True, mode=TriggerMode.PULSE_A,
                forces=[start, pull, end, snap, 0, 0, 0], preset_name="bow",
            ).clamp()

        if key == "galloping":
            start, end, freq = vals[0], vals[1], vals[2]
            return TriggerSettings(
                enabled=True, mode=TriggerMode.PULSE_AB,
                forces=[start, 200, end, 150, freq, 220, 0], preset_name="galloping",
            ).clamp()

        if key == "machine":
            start, sa, sb, freq = vals[0], _scale_0_8_to_byte(vals[1]), _scale_0_8_to_byte(vals[2]), vals[3]
            return TriggerSettings(
                enabled=True, mode=TriggerMode.PULSE_AB,
                forces=[freq, sa, start, 8, sb, 1, 0], preset_name="machine",
            ).clamp()

        return TriggerSettings(enabled=False, mode=TriggerMode.OFF, forces=[0] * 7)

    def load_settings(self, settings: TriggerSettings) -> None:
        self._syncing = True
        key = settings.preset_name if settings.preset_name in self._cards else "off"
        self._select_card(key, apply_now=False)
        self._syncing = False

    def _apply_live(self) -> None:
        if self._syncing:
            return
        settings = self.build_settings()
        if self.side_code == "L2":
            self.ctx.trigger_l2 = settings
        else:
            self.ctx.trigger_r2 = settings
        self.ctx.controller_service.apply_trigger(self.side_code, settings)
        if settings.enabled:
            self.ctx.mark_physical_trigger_tested()
        self.applied.emit()


class TriggersPage(QWidget):
    """Sección Adaptive Triggers (v0.4.5): columnas L2 y R2 con tarjetas desplegables
    de modos oficiales y no oficiales y envío en tiempo real al DualSense."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

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

        columns = QHBoxLayout()
        columns.setSpacing(16)
        self.l2_editor = TriggerColumnEditor("L2", "Left Trigger", "L2", ctx)
        self.r2_editor = TriggerColumnEditor("R2", "Right Trigger", "R2", ctx)
        columns.addWidget(self.l2_editor, 1)
        columns.addWidget(self.r2_editor, 1)
        root.addLayout(columns)

        # Vista previa plegable del último informe HID
        preview_card = Card("Vista previa — bytes del último informe HID enviado")
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("hexDump")
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(110)
        preview_card.add(self.preview)
        root.addWidget(preview_card)

        self.l2_editor.applied.connect(self._refresh_preview)
        self.r2_editor.applied.connect(self._refresh_preview)
        self.ctx.profile_applied.connect(self._on_profile_applied)
        self._refresh_preview()

    def _on_profile_applied(self, profile) -> None:
        self.l2_editor.load_settings(profile.trigger_l2)
        self.r2_editor.load_settings(profile.trigger_r2)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        data = self.ctx.controller_service.last_output_report()
        self.preview.setPlainText(hex_dump(data))
