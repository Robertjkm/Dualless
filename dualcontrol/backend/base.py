"""Interfaz que separa la interfaz gráfica/lógica de aplicación del hardware real.

Sección 13 de las instrucciones del proyecto: "La interfaz nunca debe comunicarse
directamente con el hardware." Todo pasa por aquí.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from dualcontrol.models import (
    ControllerState,
    ConnectionState,
    TriggerSettings,
    HapticSettings,
    AudioSettings,
    LightingSettings,
)


class BackendError(Exception):
    """Error de comunicación con el mando (apertura, escritura, desconexión, etc.)."""


class ControllerBackend(ABC):
    """Contrato que debe cumplir cualquier forma de hablar con un DualSense.

    Dos implementaciones conviven en este proyecto:

    - :class:`dualcontrol.backend.simulated.SimulatedBackend` — no requiere hardware,
      se usa en los tests automatizados y permite desarrollar/depurar la interfaz
      gráfica sin tener el mando conectado.
    - :class:`dualcontrol.backend.real.RealBackend` — habla con un DualSense físico
      por USB a través de ``pydualsense``/``hidapi``. Requiere Windows (o Linux con
      ``libhidapi-dev``) y el mando conectado; no puede probarse en este entorno de
      desarrollo porque no tiene un DualSense físico conectado.
    """

    # --- ciclo de vida ---------------------------------------------------------
    @abstractmethod
    def detect(self) -> bool:
        """Busca el dispositivo por VID/PID sin abrirlo. No implica poder controlarlo."""

    @abstractmethod
    def open(self) -> None:
        """Abre el dispositivo HID. Lanza BackendError si falla."""

    @abstractmethod
    def close(self) -> None:
        """Libera el dispositivo HID correctamente (sección 14: no bloquear el mando)."""

    @property
    @abstractmethod
    def connection_state(self) -> ConnectionState: ...

    # --- entrada -----------------------------------------------------------------
    @abstractmethod
    def read_state(self) -> ControllerState:
        """Lee y devuelve el último estado de entrada conocido del mando."""

    @abstractmethod
    def on_state_changed(self, callback: Callable[[ControllerState], None]) -> None:
        """Registra un callback que se invoca cada vez que llega un nuevo informe."""

    # --- salida --------------------------------------------------------------------
    @abstractmethod
    def apply_trigger(self, side: str, settings: TriggerSettings) -> None:
        """side: 'L2' o 'R2'. Debe traducirse a un informe HID real, no solo guardarse."""

    @abstractmethod
    def apply_haptics(self, settings: HapticSettings) -> None: ...

    @abstractmethod
    def apply_lighting(self, settings: LightingSettings) -> None: ...

    def apply_audio(self, settings: AudioSettings) -> None:
        """Opcional: aplica volumen de altavoz/auriculares/micrófono y estado Mute."""

    @abstractmethod
    def restore_defaults(self) -> None:
        """Sección 14: función explícita para restaurar valores predeterminados."""

    # --- diagnóstico -----------------------------------------------------------
    @abstractmethod
    def last_output_report(self) -> Optional[bytes]:
        """Devuelve los últimos bytes realmente enviados al mando (para Diagnostics)."""
