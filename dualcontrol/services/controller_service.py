"""Servicio Qt que envuelve un ``ControllerBackend`` con señales.

Sección 13: "La interfaz nunca debe comunicarse directamente con el hardware."
Todas las páginas de la interfaz hablan con este servicio, nunca con
``SimulatedBackend``/``RealBackend`` directamente.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from dualcontrol.backend.base import BackendError, ControllerBackend
from dualcontrol.models import (
    AudioSettings,
    ConnectionState,
    ControllerState,
    HapticSettings,
    LightingSettings,
    TriggerSettings,
)


class ControllerService(QObject):
    state_changed = Signal(object)        # ControllerState
    connection_changed = Signal(object)   # ConnectionState
    error_occurred = Signal(str)

    POLL_INTERVAL_MS = 16  # ~60 Hz, razonable para un monitor de entradas en pantalla

    def __init__(self, backend: ControllerBackend, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._last_state: Optional[ControllerState] = None
        self._last_error: str = ""

    @property
    def backend(self) -> ControllerBackend:
        return self._backend

    @property
    def last_error(self) -> str:
        return self._last_error

    def _emit_error(self, message: str) -> None:
        self._last_error = message
        self.error_occurred.emit(message)

    def set_backend(self, backend: ControllerBackend) -> bool:
        """Permite cambiar en caliente entre backend simulado y real (Settings)."""
        self.disconnect_controller()
        self._backend = backend
        self._last_error = ""
        return self.connect_controller()

    def detect_controller(self) -> bool:
        """Detecta el mando de forma segura sin lanzar excepciones a la interfaz."""
        self._last_error = ""
        try:
            found = self._backend.detect()
        except BackendError as exc:
            self._emit_error(str(exc))
            self.connection_changed.emit(ConnectionState.ERROR)
            return False
        self.connection_changed.emit(self._backend.connection_state)
        return found

    def connect_controller(self) -> bool:
        self._last_error = ""
        try:
            if not self._backend.detect():
                self.connection_changed.emit(ConnectionState.NOT_DETECTED)
                return False
            self._backend.open()
        except BackendError as exc:
            self._emit_error(str(exc))
            self.connection_changed.emit(ConnectionState.ERROR)
            return False
        self.connection_changed.emit(self._backend.connection_state)
        self._timer.start(self.POLL_INTERVAL_MS)
        return True

    def disconnect_controller(self) -> None:
        self._timer.stop()
        try:
            self._backend.close()
        except BackendError as exc:
            self._emit_error(str(exc))
        self.connection_changed.emit(self._backend.connection_state)

    def _poll(self) -> None:
        try:
            state = self._backend.read_state()
        except BackendError as exc:
            self._emit_error(str(exc))
            self._timer.stop()
            self.connection_changed.emit(self._backend.connection_state)
            return
        self._last_state = state
        self.state_changed.emit(state)
        self.connection_changed.emit(self._backend.connection_state)

    # --- comandos de salida (todos pasan por el backend, nunca se "simulan" solos) --
    def apply_trigger(self, side: str, settings: TriggerSettings) -> None:
        try:
            self._backend.apply_trigger(side, settings)
        except BackendError as exc:
            self._emit_error(str(exc))

    def apply_haptics(self, settings: HapticSettings) -> None:
        try:
            self._backend.apply_haptics(settings)
        except BackendError as exc:
            self._emit_error(str(exc))

    def apply_lighting(self, settings: LightingSettings) -> None:
        try:
            self._backend.apply_lighting(settings)
        except BackendError as exc:
            self._emit_error(str(exc))

    def apply_audio(self, settings: AudioSettings) -> None:
        try:
            self._backend.apply_audio(settings)
        except BackendError as exc:
            self._emit_error(str(exc))

    def restore_defaults(self) -> None:
        try:
            self._backend.restore_defaults()
        except BackendError as exc:
            self._emit_error(str(exc))

    def last_output_report(self):
        return self._backend.last_output_report()
