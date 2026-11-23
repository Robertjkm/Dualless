from __future__ import annotations

import colorsys
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.models import LightingSettings
from dualcontrol.ui.widgets import Card

_EFFECT_MODES: List[Tuple[str, str, str]] = [
    ("static", "Static Color", "Mantiene un color fijo en la barra LED con el brillo configurado."),
    ("multi_color", "Multi Color", "Ciclo suave por todo el espectro RGB en la barra LED."),
    ("breathing", "Breathing", "Efecto respiración de 0% hasta el brillo máximo configurado."),
    ("strobing", "Strobing", "Parpadeo rítmico configurable en velocidad y color."),
    ("battery", "Battery", "Cambia el color según el nivel de batería del DualSense (verde/amarillo/rojo)."),
]

_QUICK_COLORS: List[str] = [
    "#EF4444", "#F97316", "#F59E0B", "#EAB308",
    "#22C55E", "#10B981", "#14B8A6", "#06B6D4",
    "#0078D7", "#2563EB", "#6366F1", "#8B5CF6",
    "#A855F7", "#D946EF", "#EC4899", "#FFFFFF",
]


class ColorWheelWidget(QWidget):
    """Rueda cromática interactiva (Matiz + Saturación) para elegir color con clic o arrastre."""

    hueSatChanged = Signal(float, float)  # hue (0..1), sat (0..1)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self._hue = 0.57
        self._sat = 1.0
        self._dragging = False

    def set_hue_sat(self, hue: float, sat: float) -> None:
        self._hue = hue % 1.0
        self._sat = max(0.0, min(1.0, sat))
        self.update()

    def _update_from_pos(self, pos: QPointF) -> None:
        cx, cy = self.width() / 2.0, self.height() / 2.0
        radius = min(cx, cy) - 6.0
        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = math.hypot(dx, dy)
        sat = min(1.0, dist / radius) if radius > 0 else 0.0
        angle = math.degrees(math.atan2(-dy, dx))
        if angle < 0:
            angle += 360.0
        hue = (angle / 360.0) % 1.0
        self._hue = hue
        self._sat = sat
        self.update()
        self.hueSatChanged.emit(hue, sat)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._update_from_pos(event.position())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._update_from_pos(event.position())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._dragging = False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        radius = min(cx, cy) - 6.0

        # Gradiente cónico de matices (Hue)
        conical = QConicalGradient(cx, cy, 0)
        for i in range(7):
            conical.setColorAt(i / 6.0, QColor.fromHsvF((i % 6) / 6.0, 1.0, 1.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(conical)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Desaturación hacia el centro
        radial = QRadialGradient(cx, cy, radius)
        radial.setColorAt(0.0, QColor(255, 255, 255, 255))
        radial.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(radial)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Borde exterior sutil
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#3A3452"), 1.5))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Indicador del punto seleccionado
        ang_rad = math.radians(self._hue * 360.0)
        px = cx + math.cos(ang_rad) * (self._sat * radius)
        py = cy - math.sin(ang_rad) * (self._sat * radius)
        painter.setPen(QPen(QColor("#FFFFFF"), 2.2))
        painter.setBrush(QColor.fromHsvF(self._hue, self._sat, 1.0))
        painter.drawEllipse(QPointF(px, py), 6.5, 6.5)


class LightingPage(QWidget):
    """Sección Lighting avanzada (v0.4.4): Presets LED, 5 modos de efecto en vivo,
    rueda de color interactiva, RGB/HEX, Quick Colors y DualSense Features."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._syncing = False
        self._hue = 0.57
        self._sat = 1.0
        self._val = 0.84
        self._presets_file = Path(self.ctx.profile_manager.profiles_dir).parent / "led_presets.json"
        self._presets: Dict[str, dict] = self._load_presets()

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

        # --- Barra superior: Controller LED Presets ------------------------------
        preset_card = Card("")
        p_row = QHBoxLayout()
        p_info = QVBoxLayout()
        p_title = QLabel("Controller LED Presets")
        p_title.setObjectName("cardTitle")
        p_sub = QLabel("Guarda y cambia entre configuraciones LED; el preset activo se envía al DualSense.")
        p_sub.setObjectName("pageSubtitle")
        p_info.addWidget(p_title)
        p_info.addWidget(p_sub)
        p_row.addLayout(p_info, 1)

        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(170)
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        p_row.addWidget(self.preset_combo)

        save_preset_btn = QPushButton("+ Guardar preset")
        save_preset_btn.setObjectName("primary")
        save_preset_btn.clicked.connect(self._save_new_preset)
        p_row.addWidget(save_preset_btn)

        del_preset_btn = QPushButton("Eliminar")
        del_preset_btn.setObjectName("secondary")
        del_preset_btn.clicked.connect(self._delete_current_preset)
        p_row.addWidget(del_preset_btn)
        preset_card.add_layout(p_row)
        root.addWidget(preset_card)

        # --- Sub-pestañas: Light Bar Configuration | DualSense Features ----------
        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        self._sub_group = QButtonGroup(self)
        self._sub_group.setExclusive(True)
        self._sub_stack = QStackedWidget()

        btn_lightbar = QPushButton("Light Bar Configuration")
        btn_lightbar.setObjectName("subNavButton")
        btn_lightbar.setCheckable(True)
        btn_lightbar.setChecked(True)
        btn_lightbar.clicked.connect(lambda: self._sub_stack.setCurrentIndex(0))

        btn_features = QPushButton("DualSense Features (Player LEDs)")
        btn_features.setObjectName("subNavButton")
        btn_features.setCheckable(True)
        btn_features.clicked.connect(lambda: self._sub_stack.setCurrentIndex(1))

        self._sub_group.addButton(btn_lightbar, 0)
        self._sub_group.addButton(btn_features, 1)
        sub_row.addWidget(btn_lightbar)
        sub_row.addWidget(btn_features)
        sub_row.addStretch(1)
        root.addLayout(sub_row)

        # --- Vista 0: Light Bar Configuration ------------------------------------
        lightbar_page = QWidget()
        lb_grid = QGridLayout(lightbar_page)
        lb_grid.setContentsMargins(0, 0, 0, 0)
        lb_grid.setSpacing(14)
        lb_grid.setColumnStretch(0, 4)
        lb_grid.setColumnStretch(1, 7)

        # Columna izquierda
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        bright_card = Card("Light Bar Brightness")
        b_row = QHBoxLayout()
        self.lb_brightness_slider = QSlider(Qt.Horizontal)
        self.lb_brightness_slider.setRange(0, 100)
        self.lb_brightness_slider.setValue(90)
        self.lb_brightness_val = QLabel("90")
        self.lb_brightness_val.setFixedWidth(34)
        self.lb_brightness_val.setAlignment(Qt.AlignCenter)
        self.lb_brightness_val.setStyleSheet(
            "background-color: #16131F; border: 1px solid #322B45; border-radius: 6px; padding: 3px; font-weight: 700;"
        )
        self.lb_brightness_slider.valueChanged.connect(self._on_lb_brightness_changed)
        b_row.addWidget(self.lb_brightness_slider, 1)
        b_row.addWidget(self.lb_brightness_val)
        bright_card.add_layout(b_row)
        left_col.addWidget(bright_card)

        modes_card = Card("Efecto de la barra LED")
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_buttons: Dict[str, QPushButton] = {}
        for idx, (mode_key, mode_label, _desc) in enumerate(_EFFECT_MODES):
            btn = QPushButton(mode_label)
            btn.setCheckable(True)
            btn.setObjectName("subNavButton")
            btn.setStyleSheet("text-align: left; padding: 10px 14px;")
            btn.clicked.connect(lambda _c, k=mode_key: self._select_mode(k))
            self._mode_group.addButton(btn, idx)
            self._mode_buttons[mode_key] = btn
            modes_card.add(btn)
        left_col.addWidget(modes_card)

        low_bat_card = Card("Battery Low Flashing")
        self.low_bat_check = QCheckBox("Parpadear en rojo cuando la batería esté baja (≤ 20%)")
        self.low_bat_check.toggled.connect(self._emit_settings)
        low_bat_card.add(self.low_bat_check)
        left_col.addWidget(low_bat_card)
        left_col.addStretch(1)
        lb_grid.addLayout(left_col, 0, 0)

        # Columna derecha
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        mode_header_card = Card("")
        self.mode_title_label = QLabel("Static Color")
        self.mode_title_label.setObjectName("cardTitle")
        self.mode_desc_label = QLabel("")
        self.mode_desc_label.setObjectName("pageSubtitle")
        self.mode_desc_label.setWordWrap(True)
        mode_header_card.add(self.mode_title_label)
        mode_header_card.add(self.mode_desc_label)
        right_col.addWidget(mode_header_card)

        self.anim_card = Card("Ajustes del efecto")
        sp_row = QHBoxLayout()
        self.speed_label = QLabel("Effect Speed")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(30)
        self.speed_val = QLabel("30")
        self.speed_val.setFixedWidth(34)
        self.speed_val.setAlignment(Qt.AlignCenter)
        self.speed_val.setStyleSheet(
            "background-color: #16131F; border: 1px solid #322B45; border-radius: 6px; padding: 3px; font-weight: 700;"
        )
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        sp_row.addWidget(self.speed_label)
        sp_row.addWidget(self.speed_slider, 1)
        sp_row.addWidget(self.speed_val)
        self.anim_card.add_layout(sp_row)

        self.random_color_check = QCheckBox("Random Color — elegir un color nuevo en cada ciclo")
        self.random_color_check.toggled.connect(self._emit_settings)
        self.anim_card.add(self.random_color_check)
        right_col.addWidget(self.anim_card)

        # Barra de vista previa en vivo
        self.live_preview_bar = QFrame()
        self.live_preview_bar.setFixedHeight(22)
        right_col.addWidget(self.live_preview_bar)

        # Tarjeta de selector de color (Rueda + Sliders + RGB/HEX + Quick Colors)
        color_card = Card("Selector de color")
        c_row = QHBoxLayout()
        c_row.setSpacing(16)

        self.wheel = ColorWheelWidget()
        self.wheel.hueSatChanged.connect(self._on_wheel_changed)
        c_row.addWidget(self.wheel)

        mid_col = QVBoxLayout()
        mid_col.setSpacing(8)

        mid_col.addWidget(QLabel("Saturation"))
        self.sat_slider = QSlider(Qt.Horizontal)
        self.sat_slider.setRange(0, 100)
        self.sat_slider.setValue(100)
        self.sat_slider.valueChanged.connect(self._on_hsv_slider_changed)
        mid_col.addWidget(self.sat_slider)

        mid_col.addWidget(QLabel("Brightness"))
        self.val_slider = QSlider(Qt.Horizontal)
        self.val_slider.setRange(0, 100)
        self.val_slider.setValue(84)
        self.val_slider.valueChanged.connect(self._on_hsv_slider_changed)
        mid_col.addWidget(self.val_slider)

        rgb_row = QHBoxLayout()
        self.r_spin = QSpinBox()
        self.g_spin = QSpinBox()
        self.b_spin = QSpinBox()
        for prefix, sp in (("R", self.r_spin), ("G", self.g_spin), ("B", self.b_spin)):
            sp.setRange(0, 255)
            sp.setPrefix(f"{prefix} ")
            sp.valueChanged.connect(self._on_rgb_spin_changed)
            rgb_row.addWidget(sp)
        mid_col.addLayout(rgb_row)

        self.hex_edit = QLineEdit("#0078D7")
        self.hex_edit.setAlignment(Qt.AlignCenter)
        self.hex_edit.editingFinished.connect(self._on_hex_edited)
        mid_col.addWidget(self.hex_edit)
        c_row.addLayout(mid_col, 1)

        # Quick Colors 4x4
        quick_box = QVBoxLayout()
        quick_lbl = QLabel("Quick Colors")
        quick_lbl.setStyleSheet("color: #9A93B0; font-size: 12px; font-weight: 600;")
        quick_box.addWidget(quick_lbl)
        swatch_grid = QGridLayout()
        swatch_grid.setSpacing(6)
        for i, hex_code in enumerate(_QUICK_COLORS):
            sw = QPushButton()
            sw.setFixedSize(26, 26)
            sw.setCursor(Qt.PointingHandCursor)
            sw.setStyleSheet(
                f"background-color: {hex_code}; border: 1.5px solid #3B3452; border-radius: 13px;"
            )
            sw.clicked.connect(lambda _c, hx=hex_code: self._apply_quick_color(hx))
            swatch_grid.addWidget(sw, i // 4, i % 4)
        quick_box.addLayout(swatch_grid)
        quick_box.addStretch(1)
        c_row.addLayout(quick_box)

        color_card.add_layout(c_row)
        right_col.addWidget(color_card)
        right_col.addStretch(1)
        lb_grid.addLayout(right_col, 0, 1)

        self._sub_stack.addWidget(lightbar_page)

        # --- Vista 1: DualSense Features (Player LEDs) ---------------------------
        features_page = QWidget()
        f_layout = QVBoxLayout(features_page)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(14)

        player_card = Card("Indicadores de jugador (LEDs bajo el touchpad)")
        p_row2 = QHBoxLayout()
        p_row2.addWidget(QLabel("Brillo de los LEDs de jugador:"))
        self.brightness_combo = QComboBox()
        self.brightness_combo.addItems(["Alto", "Medio", "Bajo"])
        self.brightness_combo.setCurrentIndex(2)
        self.brightness_combo.currentIndexChanged.connect(self._emit_settings)
        p_row2.addWidget(self.brightness_combo)
        p_row2.addSpacing(20)
        p_row2.addWidget(QLabel("Nº de luces encendidas (0–5):"))
        self.player_spin = QSpinBox()
        self.player_spin.setRange(0, 5)
        self.player_spin.setValue(1)
        self.player_spin.valueChanged.connect(self._emit_settings)
        p_row2.addWidget(self.player_spin)
        p_row2.addStretch(1)
        player_card.add_layout(p_row2)
        f_layout.addWidget(player_card)
        f_layout.addStretch(1)

        self._sub_stack.addWidget(features_page)
        root.addWidget(self._sub_stack, 1)

        # Conectar señales de contexto y motor LED
        if self.ctx.lighting_engine is not None:
            self.ctx.lighting_engine.live_color_changed.connect(self._update_live_bar)
        self.ctx.profile_applied.connect(lambda p: self._load_from_settings(p.lighting))

        self._refresh_preset_combo()
        self._load_from_settings(self.ctx.lighting)

    # --- Presets LED -----------------------------------------------------------
    def _load_presets(self) -> Dict[str, dict]:
        defaults = {
            "Default Preset": asdict(LightingSettings()),
            "Breathing Blue": asdict(
                LightingSettings(red=0, green=120, blue=215, effect_mode="breathing", effect_speed=30, lightbar_brightness=90)
            ),
            "Rainbow Cycle": asdict(
                LightingSettings(effect_mode="multi_color", effect_speed=40, lightbar_brightness=90)
            ),
            "Battery Status": asdict(
                LightingSettings(effect_mode="battery", battery_low_flashing=True, lightbar_brightness=90)
            ),
        }
        if self._presets_file.exists():
            try:
                loaded = json.loads(self._presets_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded:
                    return loaded
            except (OSError, json.JSONDecodeError):
                pass
        return defaults

    def _save_presets_file(self) -> None:
        self._presets_file.parent.mkdir(parents=True, exist_ok=True)
        self._presets_file.write_text(json.dumps(self._presets, indent=2, ensure_ascii=False), encoding="utf-8")

    def _refresh_preset_combo(self, select: str | None = None) -> None:
        self._syncing = True
        self.preset_combo.clear()
        for name in self._presets:
            self.preset_combo.addItem(name)
        if select and select in self._presets:
            self.preset_combo.setCurrentText(select)
        self._syncing = False

    def _on_preset_selected(self, name: str) -> None:
        if self._syncing or name not in self._presets:
            return
        raw = self._presets[name]
        cfg = LightingSettings(**{k: v for k, v in raw.items() if k in LightingSettings.__dataclass_fields__}).clamp()
        cfg.preset_name = name
        self._load_from_settings(cfg)
        self._emit_settings()

    def _save_new_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Guardar preset LED", "Nombre del preset:")
        if not ok or not name.strip():
            return
        clean = name.strip()
        cfg = self._read_from_ui()
        cfg.preset_name = clean
        self._presets[clean] = asdict(cfg)
        self._save_presets_file()
        self._refresh_preset_combo(select=clean)

    def _delete_current_preset(self) -> None:
        name = self.preset_combo.currentText()
        if name == "Default Preset" or name not in self._presets:
            return
        del self._presets[name]
        self._save_presets_file()
        self._refresh_preset_combo(select="Default Preset")

    # --- Sincronización UI <-> LightingSettings --------------------------------
    def _load_from_settings(self, settings: LightingSettings) -> None:
        cfg = settings.clamp()
        self._syncing = True
        self.lb_brightness_slider.setValue(cfg.lightbar_brightness)
        self.lb_brightness_val.setText(str(cfg.lightbar_brightness))
        self.speed_slider.setValue(cfg.effect_speed)
        self.speed_val.setText(str(cfg.effect_speed))
        self.random_color_check.setChecked(cfg.random_color)
        self.low_bat_check.setChecked(cfg.battery_low_flashing)
        self.brightness_combo.setCurrentIndex(cfg.brightness)
        self.player_spin.setValue(cfg.player_led)

        self._set_rgb_controls(cfg.red, cfg.green, cfg.blue)
        self._syncing = False
        self._select_mode(cfg.effect_mode, emit=False)
        self._update_live_bar(cfg.red, cfg.green, cfg.blue)

    def _set_rgb_controls(self, r: int, g: int, b: int) -> None:
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        self._hue, self._sat, self._val = h, s, v
        self.wheel.set_hue_sat(h, s)
        self.sat_slider.setValue(int(round(s * 100)))
        self.val_slider.setValue(int(round(v * 100)))
        self.r_spin.setValue(r)
        self.g_spin.setValue(g)
        self.b_spin.setValue(b)
        self.hex_edit.setText(f"#{r:02X}{g:02X}{b:02X}")

    def _select_mode(self, mode_key: str, *, emit: bool = True) -> None:
        btn = self._mode_buttons.get(mode_key)
        if btn is not None:
            btn.setChecked(True)
        for key, label, desc in _EFFECT_MODES:
            if key == mode_key:
                self.mode_title_label.setText(label)
                self.mode_desc_label.setText(desc)
                break

        is_animated = mode_key in ("multi_color", "breathing", "strobing")
        self.anim_card.setVisible(is_animated)
        self.random_color_check.setVisible(mode_key in ("breathing", "strobing"))
        speed_titles = {
            "breathing": "Breathing Speed",
            "strobing": "Strobing Speed",
            "multi_color": "Color Cycle Speed",
        }
        self.speed_label.setText(speed_titles.get(mode_key, "Effect Speed"))

        if emit:
            self._emit_settings()

    def _active_mode_key(self) -> str:
        for key, btn in self._mode_buttons.items():
            if btn.isChecked():
                return key
        return "static"

    def _on_lb_brightness_changed(self, value: int) -> None:
        self.lb_brightness_val.setText(str(value))
        if not self._syncing:
            self._emit_settings()

    def _on_speed_changed(self, value: int) -> None:
        self.speed_val.setText(str(value))
        if not self._syncing:
            self._emit_settings()

    def _on_wheel_changed(self, hue: float, sat: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._hue = hue
        self._sat = sat
        self.sat_slider.setValue(int(round(sat * 100)))
        r, g, b = colorsys.hsv_to_rgb(self._hue, self._sat, self._val)
        ri, gi, bi = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
        self.r_spin.setValue(ri)
        self.g_spin.setValue(gi)
        self.b_spin.setValue(bi)
        self.hex_edit.setText(f"#{ri:02X}{gi:02X}{bi:02X}")
        self._syncing = False
        self._emit_settings()

    def _on_hsv_slider_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._sat = self.sat_slider.value() / 100.0
        self._val = self.val_slider.value() / 100.0
        self.wheel.set_hue_sat(self._hue, self._sat)
        r, g, b = colorsys.hsv_to_rgb(self._hue, self._sat, self._val)
        ri, gi, bi = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
        self.r_spin.setValue(ri)
        self.g_spin.setValue(gi)
        self.b_spin.setValue(bi)
        self.hex_edit.setText(f"#{ri:02X}{gi:02X}{bi:02X}")
        self._syncing = False
        self._emit_settings()

    def _on_rgb_spin_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._set_rgb_controls(self.r_spin.value(), self.g_spin.value(), self.b_spin.value())
        self._syncing = False
        self._emit_settings()

    def _on_hex_edited(self) -> None:
        if self._syncing:
            return
        raw = self.hex_edit.text().strip().lstrip("#")
        if len(raw) == 6:
            try:
                r = int(raw[0:2], 16)
                g = int(raw[2:4], 16)
                b = int(raw[4:6], 16)
            except ValueError:
                return
            self._syncing = True
            self._set_rgb_controls(r, g, b)
            self._syncing = False
            self._emit_settings()

    def _apply_quick_color(self, hex_code: str) -> None:
        c = QColor(hex_code)
        if not c.isValid():
            return
        self._syncing = True
        self._set_rgb_controls(c.red(), c.green(), c.blue())
        self._syncing = False
        self._emit_settings()

    def _read_from_ui(self) -> LightingSettings:
        return LightingSettings(
            red=self.r_spin.value(),
            green=self.g_spin.value(),
            blue=self.b_spin.value(),
            brightness=self.brightness_combo.currentIndex(),
            player_led=self.player_spin.value(),
            effect_mode=self._active_mode_key(),
            lightbar_brightness=self.lb_brightness_slider.value(),
            effect_speed=self.speed_slider.value(),
            random_color=self.random_color_check.isChecked(),
            battery_low_flashing=self.low_bat_check.isChecked(),
            preset_name=self.preset_combo.currentText() or "Default Preset",
        ).clamp()

    def _emit_settings(self) -> None:
        if self._syncing:
            return
        cfg = self._read_from_ui()
        self.ctx.apply_lighting(cfg)

    def _update_live_bar(self, r: int, g: int, b: int) -> None:
        self.live_preview_bar.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border-radius: 6px; border: 1px solid #322B45;"
        )
