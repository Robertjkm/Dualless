from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dualcontrol import constants
from dualcontrol.app_context import AppContext
from dualcontrol.services.windows_integration import (
    is_start_with_windows_enabled,
    set_start_with_windows,
)
from dualcontrol.ui.widgets import Card


class SettingsPage(QWidget):
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
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        # --- Backend y detección automática ---
        backend_card = Card("Backend de comunicación y detección automática")
        self.auto_detect_check = QCheckBox(
            "Detección automática de DualSense (USB / Bluetooth) — cambia a Real al conectar el mando"
        )
        self.auto_detect_check.setChecked(ctx.auto_detect_enabled)
        self.auto_detect_check.toggled.connect(self._on_auto_detect_toggled)
        backend_card.add(self.auto_detect_check)

        self.sim_radio = QRadioButton("Simulado (sin hardware — para probar la interfaz)")
        self.real_radio = QRadioButton(
            "Real (USB y Bluetooth nativo de Windows — conecta tu DualSense por cable o Bluetooth)"
        )
        self.sim_radio.setChecked(not ctx.using_real_backend)
        self.real_radio.setChecked(ctx.using_real_backend)
        backend_card.add(self.sim_radio)
        backend_card.add(self.real_radio)

        apply_btn = QPushButton("Aplicar cambio de backend")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._apply_backend)
        backend_card.add(apply_btn)
        root.addWidget(backend_card)

        # --- Sistema, Bandeja y Automatización (v0.8.0) ---
        sys_card = Card("Sistema, bandeja (System Tray) y automatización")
        self.tray_check = QCheckBox(
            "Minimizar a la bandeja del sistema al cerrar la ventana (sigue corriendo en segundo plano)"
        )
        self.tray_check.setChecked(ctx.minimize_to_tray)
        self.tray_check.toggled.connect(lambda c: setattr(self.ctx, "minimize_to_tray", bool(c)))
        sys_card.add(self.tray_check)

        self.startup_check = QCheckBox("Iniciar Dualless automáticamente al arrancar Windows")
        self.startup_check.setChecked(is_start_with_windows_enabled())
        self.startup_check.toggled.connect(self._on_startup_toggled)
        sys_card.add(self.startup_check)

        self.game_profile_check = QCheckBox(
            "Cambio automático de perfil por juego (detecta el .exe activo y aplica su perfil guardado)"
        )
        self.game_profile_check.setChecked(ctx.game_watcher.enabled)
        self.game_profile_check.toggled.connect(ctx.game_watcher.set_enabled)
        sys_card.add(self.game_profile_check)

        self.low_bat_check = QCheckBox(
            "Notificar en Windows cuando la batería del DualSense baje del 15%"
        )
        self.low_bat_check.setChecked(ctx.low_battery_alerts)
        self.low_bat_check.toggled.connect(lambda c: setattr(self.ctx, "low_battery_alerts", bool(c)))
        sys_card.add(self.low_bat_check)
        root.addWidget(sys_card)

        # --- Restaurar ---
        reset_card = Card("Restaurar valores predeterminados")
        reset_btn = QPushButton("Restaurar todo (gatillos, hápticos, iluminación)")
        reset_btn.setObjectName("secondary")
        reset_btn.clicked.connect(self._restore_defaults)
        reset_card.add(reset_btn)
        root.addWidget(reset_card)

        # --- Acerca de ---
        about_card = Card("Acerca de")
        about_card.add(QLabel(f"{constants.APP_NAME} — {constants.APP_VERSION_STAGE}"))
        about_card.add(QLabel(
            "Alternativa independiente para controlar tu Sony DualSense en Windows por USB y Bluetooth "
            "nativo (hid.dll / setupapi.dll) sin dependencias externas."
        ))
        root.addWidget(about_card)

        root.addStretch(1)
        self.ctx.backend_changed.connect(self._sync_from_context)

    def _sync_from_context(self, using_real: bool) -> None:
        self.real_radio.setChecked(using_real)
        self.sim_radio.setChecked(not using_real)
        self.auto_detect_check.blockSignals(True)
        self.auto_detect_check.setChecked(self.ctx.auto_detect_enabled)
        self.auto_detect_check.blockSignals(False)

    def _on_auto_detect_toggled(self, checked: bool) -> None:
        self.ctx.set_auto_detect(checked)

    def _on_startup_toggled(self, checked: bool) -> None:
        ok = set_start_with_windows(checked)
        if not ok:
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(is_start_with_windows_enabled())
            self.startup_check.blockSignals(False)
            QMessageBox.information(
                self,
                "Inicio con Windows",
                "Esta opción solo está disponible al ejecutar Dualless en Windows.",
            )

    def _apply_backend(self) -> None:
        if self.real_radio.isChecked():
            connected = self.ctx.switch_backend_manual(True)
            if connected:
                QMessageBox.information(
                    self,
                    "DualSense conectado",
                    "Backend Real (USB / Bluetooth) activado y DualSense detectado correctamente.",
                )
            else:
                detail = self.ctx.controller_service.last_error or (
                    "No se detectó ningún DualSense conectado por USB o Bluetooth. "
                    "Conéctalo y Dualless lo detectará automáticamente si la detección automática está activa."
                )
                QMessageBox.warning(self, "Backend real seleccionado", detail)
        else:
            self.ctx.switch_backend_manual(False)

    def _restore_defaults(self) -> None:
        self.ctx.controller_service.restore_defaults()
        QMessageBox.information(self, "Listo", "Valores predeterminados restaurados.")
