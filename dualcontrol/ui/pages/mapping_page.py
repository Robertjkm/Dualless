from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from dualcontrol.models import MappingSettings
from dualcontrol.ui.widgets import Card, LabeledSlider
from dualcontrol.virtualcontroller.mapper import (
    DEFAULT_BUTTON_MAP,
    PHYSICAL_BUTTON_LABELS,
    XINPUT_TARGET_LABELS,
)


class MappingPage(QWidget):
    """Sección 9: Button Mapping (reasignación de botones, zonas muertas,
    sensibilidad e inversión de ejes aplicados al mando virtual XInput)."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._combos: Dict[str, QComboBox] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Button Mapping")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Reasigna botones y ajusta zonas muertas, sensibilidad e inversión de sticks. "
            "Estos cambios se aplican sobre la salida del mando virtual Xbox 360 (Modo XInput) "
            "y se guardan automáticamente dentro de tus perfiles."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.mode_notice = QLabel("")
        self.mode_notice.setWordWrap(True)
        root.addWidget(self.mode_notice)

        grid = QGridLayout()
        grid.setSpacing(16)
        root.addLayout(grid)

        # --- Columna izquierda: Reasignación de botones -------------------------
        buttons_card = Card("Reasignación de botones (DualSense → Xbox XInput)")
        btn_grid = QGridLayout()
        btn_grid.setSpacing(8)
        for row_idx, (phys_key, phys_label) in enumerate(PHYSICAL_BUTTON_LABELS):
            btn_grid.addWidget(QLabel(phys_label), row_idx, 0)
            combo = QComboBox()
            for target_key, target_label in XINPUT_TARGET_LABELS:
                combo.addItem(target_label, target_key)
            self._combos[phys_key] = combo
            btn_grid.addWidget(combo, row_idx, 1)
        buttons_card.add_layout(btn_grid)
        grid.addWidget(buttons_card, 0, 0)

        # --- Columna derecha: Sticks analógicos ---------------------------------
        sticks_col = QVBoxLayout()
        sticks_col.setSpacing(16)

        left_card = Card("Stick Izquierdo (L)")
        self.dz_left = LabeledSlider("Zona muerta (%)", minimum=0, maximum=50, value=5)
        self.sens_left = LabeledSlider("Sensibilidad (%)", minimum=25, maximum=200, value=100)
        self.inv_left_x = QCheckBox("Invertir eje X (izquierda / derecha)")
        self.inv_left_y = QCheckBox("Invertir eje Y (arriba / abajo)")
        left_card.add(self.dz_left)
        left_card.add(self.sens_left)
        left_card.add(self.inv_left_x)
        left_card.add(self.inv_left_y)
        sticks_col.addWidget(left_card)

        right_card = Card("Stick Derecho (R)")
        self.dz_right = LabeledSlider("Zona muerta (%)", minimum=0, maximum=50, value=5)
        self.sens_right = LabeledSlider("Sensibilidad (%)", minimum=25, maximum=200, value=100)
        self.inv_right_x = QCheckBox("Invertir eje X (izquierda / derecha)")
        self.inv_right_y = QCheckBox("Invertir eje Y (arriba / abajo)")
        right_card.add(self.dz_right)
        right_card.add(self.sens_right)
        right_card.add(self.inv_right_x)
        right_card.add(self.inv_right_y)
        sticks_col.addWidget(right_card)

        sticks_col.addStretch(1)
        grid.addLayout(sticks_col, 0, 1)

        # --- Barra inferior de acciones -----------------------------------------
        action_row = QHBoxLayout()
        self.apply_btn = QPushButton("Aplicar mapeo")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self._apply)
        action_row.addWidget(self.apply_btn)

        self.reset_btn = QPushButton("Restaurar predeterminados")
        self.reset_btn.setObjectName("secondary")
        self.reset_btn.clicked.connect(self._reset_defaults)
        action_row.addWidget(self.reset_btn)
        action_row.addStretch(1)
        root.addLayout(action_row)
        root.addStretch(1)

        self.ctx.profile_applied.connect(lambda p: self._load_from_settings(p.mapping))
        self.ctx.virtual_controller_service.status_changed.connect(lambda _a, _m: self._refresh_notice())
        self._load_from_settings(self.ctx.mapping)
        self._refresh_notice()

    def _refresh_notice(self) -> None:
        if self.ctx.virtual_controller_service.is_xinput_active:
            self.mode_notice.setText(
                "● Modo XInput activo: los cambios aplicados aquí se reflejan en tiempo real en tu mando virtual Xbox 360."
            )
            self.mode_notice.setStyleSheet("color: #35D07F; font-weight: 600;")
        else:
            self.mode_notice.setText(
                "● Modo Nativo activo: puedes configurar y guardar tu mapeo en perfiles ahora, "
                "y activar Modo XInput en Game Compatibility cuando quieras usarlo en un juego."
            )
            self.mode_notice.setStyleSheet("color: #F2B84B;")

    def _load_from_settings(self, settings: MappingSettings) -> None:
        cfg = settings.clamp()
        remap = cfg.remap or {}
        for phys_key, combo in self._combos.items():
            target = remap.get(phys_key, DEFAULT_BUTTON_MAP[phys_key])
            idx = combo.findData(target)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        self.dz_left.set_value(int(round(cfg.deadzone_left * 100)))
        self.dz_right.set_value(int(round(cfg.deadzone_right * 100)))
        self.sens_left.set_value(int(round(cfg.sensitivity_left * 100)))
        self.sens_right.set_value(int(round(cfg.sensitivity_right * 100)))
        self.inv_left_x.setChecked(cfg.invert_left_x)
        self.inv_left_y.setChecked(cfg.invert_left_y)
        self.inv_right_x.setChecked(cfg.invert_right_x)
        self.inv_right_y.setChecked(cfg.invert_right_y)

    def _read_from_ui(self) -> MappingSettings:
        remap = {}
        for phys_key, combo in self._combos.items():
            target = combo.currentData()
            if target != DEFAULT_BUTTON_MAP[phys_key]:
                remap[phys_key] = target

        return MappingSettings(
            remap=remap,
            deadzone_left=self.dz_left.value() / 100.0,
            deadzone_right=self.dz_right.value() / 100.0,
            sensitivity_left=self.sens_left.value() / 100.0,
            sensitivity_right=self.sens_right.value() / 100.0,
            invert_left_x=self.inv_left_x.isChecked(),
            invert_left_y=self.inv_left_y.isChecked(),
            invert_right_x=self.inv_right_x.isChecked(),
            invert_right_y=self.inv_right_y.isChecked(),
        ).clamp()

    def _apply(self) -> None:
        settings = self._read_from_ui()
        self.ctx.apply_mapping(settings)
        QMessageBox.information(
            self,
            "Mapeo aplicado",
            "Configuración de Button Mapping aplicada correctamente. "
            "Recuerda guardarla en la pestaña Profiles si quieres conservarla por juego.",
        )

    def _reset_defaults(self) -> None:
        default_cfg = MappingSettings()
        self._load_from_settings(default_cfg)
        self.ctx.apply_mapping(default_cfg)
