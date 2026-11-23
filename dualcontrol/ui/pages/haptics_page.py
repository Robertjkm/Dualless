from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.models import AudioSettings, HapticSettings
from dualcontrol.ui.widgets import Card, LabeledSlider


class _ModeOptionCard(QFrame):
    """Tarjeta seleccionable para Rumble Mode / Haptic Feedback Mode."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(10)

        self.radio = QRadioButton()
        self.radio.setAutoExclusive(False)
        row.addWidget(self.radio, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        s_lbl = QLabel(subtitle)
        s_lbl.setWordWrap(True)
        s_lbl.setStyleSheet("font-size: 12px; color: #A6A0B8; background: transparent; border: none;")
        col.addWidget(t_lbl)
        col.addWidget(s_lbl)
        row.addLayout(col, 1)
        self.set_selected(False)

    def set_selected(self, active: bool) -> None:
        self.radio.setChecked(active)
        if active:
            self.setStyleSheet(
                "QFrame { background-color: #2A223B; border: 1.5px solid #A855F7; border-radius: 10px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background-color: #1D1A27; border: 1px solid #2F2940; border-radius: 10px; }"
            )


class HapticsPage(QWidget):
    """Sección Haptic Feedback (v0.4.6): Presets de vibración, Rumble Mode vs
    Haptic Feedback Mode, Enable Rumble, Rumble Intensity (0..8), Enhanced Rumble
    Experience, Audio To Rumble y prueba directa de motores."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._syncing = False
        self._presets_file = Path(self.ctx.profile_manager.profiles_dir).parent / "haptics_presets.json"
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
        root.setSpacing(12)

        # --- 1. Haptics Rumble Presets -------------------------------------------
        preset_card = Card("")
        p_row = QHBoxLayout()
        p_info = QVBoxLayout()
        p_title = QLabel("Haptics Rumble Presets")
        p_title.setObjectName("cardTitle")
        p_sub = QLabel(
            "Administra múltiples configuraciones de vibración y háptica. "
            "El preset seleccionado se envía al DualSense."
        )
        p_sub.setObjectName("pageSubtitle")
        p_sub.setWordWrap(True)
        p_info.addWidget(p_title)
        p_info.addWidget(p_sub)
        p_row.addLayout(p_info, 1)

        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(165)
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        p_row.addWidget(self.preset_combo)

        save_btn = QPushButton("+ Guardar preset")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_new_preset)
        p_row.addWidget(save_btn)

        dup_btn = QPushButton("Duplicar")
        dup_btn.setObjectName("secondary")
        dup_btn.clicked.connect(self._duplicate_preset)
        p_row.addWidget(dup_btn)

        del_btn = QPushButton("Eliminar")
        del_btn.setObjectName("secondary")
        del_btn.clicked.connect(self._delete_preset)
        p_row.addWidget(del_btn)
        preset_card.add_layout(p_row)
        root.addWidget(preset_card)

        # --- 2. Selector de modo: Rumble Mode vs Haptic Feedback Mode ------------
        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        self.rumble_mode_card = _ModeOptionCard(
            "Rumble Mode",
            "When this is checked, standard rumble will be sent to the motors.",
        )
        self.haptic_mode_card = _ModeOptionCard(
            "Haptic Feedback Mode",
            "When this is checked, one of the applied haptic modes will be in effect.",
        )
        self.rumble_mode_card.mousePressEvent = lambda _e: self._select_mode(use_haptics=False)  # type: ignore[assignment]
        self.rumble_mode_card.radio.clicked.connect(lambda: self._select_mode(use_haptics=False))
        self.haptic_mode_card.mousePressEvent = lambda _e: self._select_mode(use_haptics=True)  # type: ignore[assignment]
        self.haptic_mode_card.radio.clicked.connect(lambda: self._select_mode(use_haptics=True))
        mode_row.addWidget(self.rumble_mode_card, 1)
        mode_row.addWidget(self.haptic_mode_card, 1)
        root.addLayout(mode_row)

        # --- 3. Enable Rumble ----------------------------------------------------
        enable_card = Card("")
        e_row = QHBoxLayout()
        e_col = QVBoxLayout()
        e_t = QLabel("Enable Rumble")
        e_t.setObjectName("cardTitle")
        e_s = QLabel("When this is enabled, rumble will be sent to the controller.")
        e_s.setObjectName("pageSubtitle")
        e_col.addWidget(e_t)
        e_col.addWidget(e_s)
        self.enable_rumble_check = QCheckBox("Activado")
        self.enable_rumble_check.setChecked(True)
        self.enable_rumble_check.toggled.connect(self._emit_settings)
        e_row.addLayout(e_col, 1)
        e_row.addWidget(self.enable_rumble_check)
        enable_card.add_layout(e_row)
        root.addWidget(enable_card)

        # --- 4. Rumble Intensity (0..8) ------------------------------------------
        intensity_card = Card("")
        i_row = QHBoxLayout()
        i_col = QVBoxLayout()
        i_t = QLabel("Rumble Intensity")
        i_t.setObjectName("cardTitle")
        i_s = QLabel("Choose how strong the overall motor strength should be.")
        i_s.setObjectName("pageSubtitle")
        i_col.addWidget(i_t)
        i_col.addWidget(i_s)
        i_row.addLayout(i_col, 1)

        self.intensity_slider = QSlider(Qt.Horizontal)
        self.intensity_slider.setRange(0, 8)
        self.intensity_slider.setValue(8)
        self.intensity_slider.setMinimumWidth(260)
        self.intensity_val = QLabel("8")
        self.intensity_val.setFixedWidth(36)
        self.intensity_val.setAlignment(Qt.AlignCenter)
        self.intensity_val.setStyleSheet(
            "background-color: #16131F; border: 1px solid #322B45; border-radius: 6px; padding: 4px; font-weight: 700;"
        )
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)
        i_row.addWidget(self.intensity_slider, 1)
        i_row.addWidget(self.intensity_val)
        intensity_card.add_layout(i_row)
        root.addWidget(intensity_card)

        # --- 5. Enhanced Rumble Experience ---------------------------------------
        enh_card = Card("")
        en_row = QHBoxLayout()
        en_col = QVBoxLayout()
        en_t = QLabel("Enhanced Rumble Experience")
        en_t.setObjectName("cardTitle")
        en_s = QLabel(
            "When enabled, this feature enhances the classic rumble experience by utilizing "
            "the improved rumble introduced in newer DualSense™ firmware."
        )
        en_s.setObjectName("pageSubtitle")
        en_s.setWordWrap(True)
        en_col.addWidget(en_t)
        en_col.addWidget(en_s)
        self.enhanced_check = QCheckBox("Activado")
        self.enhanced_check.setChecked(True)
        self.enhanced_check.toggled.connect(self._emit_settings)
        en_row.addLayout(en_col, 1)
        en_row.addWidget(self.enhanced_check)
        enh_card.add_layout(en_row)
        root.addWidget(enh_card)

        # --- 6. Audio To Rumble --------------------------------------------------
        audio_card = Card("")
        au_row = QHBoxLayout()
        au_col = QVBoxLayout()
        au_t = QLabel("Audio To Rumble")
        au_t.setObjectName("cardTitle")
        au_s = QLabel(
            "Captura el audio de Windows (WASAPI Loopback). Con Haptic Feedback Mode activo por USB, "
            "envía señal táctil filtrada directamente a los canales 3 y 4 del DualSense (actuadores VCM HD); "
            "en Rumble Mode o por Bluetooth utiliza los motores HID."
        )
        au_s.setObjectName("pageSubtitle")
        au_s.setWordWrap(True)
        au_col.addWidget(au_t)
        au_col.addWidget(au_s)
        self.audio_status_lbl = QLabel("Estado WASAPI: Inactivo")
        self.audio_status_lbl.setObjectName("pageSubtitle")
        au_col.addWidget(self.audio_status_lbl)
        self.audio_to_rumble_check = QCheckBox("Activado")
        self.audio_to_rumble_check.setChecked(False)
        self.audio_to_rumble_check.toggled.connect(self._on_audio_rumble_toggled)
        au_row.addLayout(au_col, 1)
        au_row.addWidget(self.audio_to_rumble_check)
        audio_card.add_layout(au_row)
        self.ctx.audio_rumble.status_changed.connect(self._on_audio_status_changed)
        root.addWidget(audio_card)

        # --- 7. Prueba directa de motores ----------------------------------------
        test_card = Card("Prueba directa de motores (L / R)")
        self.left_slider = LabeledSlider("Motor izquierdo (baja frecuencia)", maximum=255, value=0)
        self.right_slider = LabeledSlider("Motor derecho (alta frecuencia)", maximum=255, value=0)
        test_card.add(self.left_slider)
        test_card.add(self.right_slider)

        btn_row = QHBoxLayout()
        pulse_btn = QPushButton("Probar vibración (1s)")
        pulse_btn.setObjectName("primary")
        pulse_btn.clicked.connect(self._test_pulse)
        apply_btn = QPushButton("Aplicar motores")
        apply_btn.setObjectName("secondary")
        apply_btn.clicked.connect(self._emit_settings)
        stop_btn = QPushButton("Detener vibración")
        stop_btn.setObjectName("secondary")
        stop_btn.clicked.connect(self._stop_motors)
        btn_row.addWidget(pulse_btn)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(stop_btn)
        btn_row.addStretch(1)
        test_card.add_layout(btn_row)
        root.addWidget(test_card)

        # --- 8. Altavoz integrado y sincronización real del botón Mute (v1.2.0) ---
        spk_card = Card("Altavoz integrado y sincronización del botón Mute")
        self.spk_enable_check = QCheckBox("Habilitar altavoz integrado del DualSense")
        self.spk_enable_check.setChecked(self.ctx.audio.speaker_enabled)
        self.spk_vol_slider = LabeledSlider("Volumen del altavoz del mando (%)", minimum=0, maximum=100, value=self.ctx.audio.speaker_volume)
        self.hp_vol_slider = LabeledSlider("Volumen de auriculares del mando (%)", minimum=0, maximum=100, value=self.ctx.audio.headphone_volume)
        self.mic_vol_slider = LabeledSlider("Ganancia del micrófono integrado (%)", minimum=0, maximum=100, value=self.ctx.audio.mic_volume)
        self.sync_mute_check = QCheckBox(
            "Sincronizar botón físico Mute con micrófono de Windows y LED naranja del mando"
        )
        self.sync_mute_check.setChecked(self.ctx.audio.sync_windows_mute)

        spk_btn_row = QHBoxLayout()
        apply_audio_btn = QPushButton("Aplicar audio al mando")
        apply_audio_btn.setObjectName("primary")
        apply_audio_btn.clicked.connect(self._apply_audio_settings)
        toggle_mute_btn = QPushButton("Alternar Mute / LED naranja")
        toggle_mute_btn.setObjectName("secondary")
        toggle_mute_btn.clicked.connect(self._toggle_mute_now)
        self.mute_state_lbl = QLabel("Micrófono: Activo")
        self.mute_state_lbl.setObjectName("pageSubtitle")
        spk_btn_row.addWidget(apply_audio_btn)
        spk_btn_row.addWidget(toggle_mute_btn)
        spk_btn_row.addWidget(self.mute_state_lbl)
        spk_btn_row.addStretch(1)

        for w in (self.spk_enable_check, self.spk_vol_slider, self.hp_vol_slider, self.mic_vol_slider, self.sync_mute_check):
            spk_card.add(w)
        spk_card.add_layout(spk_btn_row)
        root.addWidget(spk_card)
        self.ctx.audio_changed.connect(self._on_audio_settings_changed)

        root.addStretch(1)

        self.ctx.profile_applied.connect(lambda p: self._load_from_settings(p.haptics))
        self._refresh_preset_combo()
        self._load_from_settings(self.ctx.haptics)

    # --- Presets ---------------------------------------------------------------
    def _load_presets(self) -> Dict[str, dict]:
        defaults = {
            "Default Preset": asdict(HapticSettings(use_haptics=False, enabled=True, intensity=8, enhanced_rumble=True)),
            "Soft Rumble": asdict(HapticSettings(use_haptics=False, enabled=True, intensity=4, enhanced_rumble=True)),
            "Haptic Focus": asdict(HapticSettings(use_haptics=True, enabled=True, intensity=7, enhanced_rumble=True)),
            "Silent (Off)": asdict(HapticSettings(use_haptics=False, enabled=False, intensity=0, enhanced_rumble=False)),
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
        cfg = HapticSettings(**{k: v for k, v in raw.items() if k in HapticSettings.__dataclass_fields__}).clamp()
        cfg.preset_name = name
        self._load_from_settings(cfg)
        self._emit_settings()

    def _save_new_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Guardar preset", "Nombre del preset de vibración:")
        if not ok or not name.strip():
            return
        clean = name.strip()
        cfg = self._read_from_ui()
        cfg.preset_name = clean
        self._presets[clean] = asdict(cfg)
        self._save_presets_file()
        self._refresh_preset_combo(select=clean)

    def _duplicate_preset(self) -> None:
        cur = self.preset_combo.currentText() or "Default Preset"
        name, ok = QInputDialog.getText(self, "Duplicar preset", "Nombre de la copia:", text=f"{cur} (copia)")
        if not ok or not name.strip():
            return
        clean = name.strip()
        cfg = self._read_from_ui()
        cfg.preset_name = clean
        self._presets[clean] = asdict(cfg)
        self._save_presets_file()
        self._refresh_preset_combo(select=clean)

    def _delete_preset(self) -> None:
        cur = self.preset_combo.currentText()
        if cur == "Default Preset" or cur not in self._presets:
            return
        del self._presets[cur]
        self._save_presets_file()
        self._refresh_preset_combo(select="Default Preset")

    # --- UI <-> HapticSettings -------------------------------------------------
    def _select_mode(self, *, use_haptics: bool) -> None:
        self._use_haptics = use_haptics
        self.rumble_mode_card.set_selected(not use_haptics)
        self.haptic_mode_card.set_selected(use_haptics)
        if not self._syncing:
            self._emit_settings()

    def _on_intensity_changed(self, value: int) -> None:
        self.intensity_val.setText(str(value))
        if not self._syncing:
            self._emit_settings()

    def _load_from_settings(self, settings: HapticSettings) -> None:
        cfg = settings.clamp()
        self._syncing = True
        self._select_mode(use_haptics=cfg.use_haptics)
        self.enable_rumble_check.setChecked(cfg.enabled)
        self.intensity_slider.setValue(cfg.intensity)
        self.intensity_val.setText(str(cfg.intensity))
        self.enhanced_check.setChecked(cfg.enhanced_rumble)
        self.audio_to_rumble_check.setChecked(cfg.audio_to_rumble)
        self.left_slider.set_value(cfg.left_motor)
        self.right_slider.set_value(cfg.right_motor)
        self._syncing = False

    def _read_from_ui(self) -> HapticSettings:
        return HapticSettings(
            left_motor=self.left_slider.value(),
            right_motor=self.right_slider.value(),
            use_haptics=self.haptic_mode_card.radio.isChecked(),
            enabled=self.enable_rumble_check.isChecked(),
            intensity=self.intensity_slider.value(),
            enhanced_rumble=self.enhanced_check.isChecked(),
            audio_to_rumble=self.audio_to_rumble_check.isChecked(),
            preset_name=self.preset_combo.currentText() or "Default Preset",
        ).clamp()

    def _on_audio_rumble_toggled(self, checked: bool) -> None:
        self._emit_settings()
        if checked:
            ok = self.ctx.audio_rumble.start()
            if not ok:
                self.audio_to_rumble_check.blockSignals(True)
                self.audio_to_rumble_check.setChecked(False)
                self.audio_to_rumble_check.blockSignals(False)
        else:
            self.ctx.audio_rumble.stop()

    def _on_audio_status_changed(self, running: bool, text: str) -> None:
        col = "#22C55E" if running else "#9CA0BA"
        self.audio_status_lbl.setStyleSheet(f"color: {col}; font-size: 12px;")
        self.audio_status_lbl.setText(f"Estado WASAPI: {text}")

    def _emit_settings(self) -> None:
        if self._syncing:
            return
        cfg = self._read_from_ui()
        self.ctx.haptics = cfg
        self.ctx.controller_service.apply_haptics(cfg)

    def _test_pulse(self) -> None:
        cfg = self._read_from_ui()
        if not cfg.enabled or cfg.intensity == 0:
            QMessageBox.information(
                self,
                "Vibración desactivada",
                "Activa 'Enable Rumble' y sube 'Rumble Intensity' por encima de 0 para probar la vibración.",
            )
            return
        pulse = HapticSettings(
            left_motor=255,
            right_motor=255,
            use_haptics=cfg.use_haptics,
            enabled=True,
            intensity=cfg.intensity,
            enhanced_rumble=cfg.enhanced_rumble,
        )
        self.ctx.controller_service.apply_haptics(pulse)
        QTimer.singleShot(1000, self._stop_motors)

    def _stop_motors(self) -> None:
        self._syncing = True
        self.left_slider.set_value(0)
        self.right_slider.set_value(0)
        self._syncing = False
        cfg = self._read_from_ui()
        self.ctx.haptics = cfg
        self.ctx.controller_service.apply_haptics(cfg)

    def _apply_audio_settings(self) -> None:
        cfg = AudioSettings(
            speaker_volume=self.spk_vol_slider.value(),
            headphone_volume=self.hp_vol_slider.value(),
            mic_volume=self.mic_vol_slider.value(),
            speaker_enabled=self.spk_enable_check.isChecked(),
            mic_muted=self.ctx.audio.mic_muted,
            sync_windows_mute=self.sync_mute_check.isChecked(),
        ).clamp()
        self.ctx.apply_audio(cfg)

    def _toggle_mute_now(self) -> None:
        self.ctx.toggle_mic_mute_hardware()

    def _on_audio_settings_changed(self, audio: AudioSettings) -> None:
        if audio.mic_muted:
            self.mute_state_lbl.setStyleSheet("color: #F97316; font-weight: 700;")
            self.mute_state_lbl.setText("Micrófono: Silenciado (LED naranja ON)")
        else:
            self.mute_state_lbl.setStyleSheet("color: #22C55E; font-weight: 700;")
            self.mute_state_lbl.setText("Micrófono: Activo (LED OFF)")
