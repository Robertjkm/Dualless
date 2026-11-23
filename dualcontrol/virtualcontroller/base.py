"""Interfaces base para emulación de mando virtual (sección 10)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Optional

from dualcontrol.models import ControllerState, MappingSettings


class VirtualControllerMode(str, Enum):
    NATIVE = "nativo"
    XINPUT = "xinput"
    DUALSHOCK4 = "ds4"
    DUALSENSE = "dualsense"


class VirtualControllerError(Exception):
    """Error al inicializar o alimentar el dispositivo de mando virtual."""


class VirtualControllerAdapter(ABC):
    """Contrato común para cualquier adaptador de mando virtual (ViGEm o simulado)."""

    @property
    @abstractmethod
    def is_active(self) -> bool: ...

    @abstractmethod
    def start(
        self,
        rumble_callback: Optional[Callable[[int, int], None]] = None,
        led_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> None:
        """Crea y conecta el dispositivo virtual en el sistema."""

    @abstractmethod
    def stop(self) -> None:
        """Desconecta y libera limpiamente el dispositivo virtual."""

    @abstractmethod
    def feed_state(self, state: ControllerState, mapping: Optional[MappingSettings] = None) -> None:
        """Traduce un ControllerState del DualSense y actualiza el mando virtual."""
