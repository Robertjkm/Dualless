"""Backend simulado — sección 16: "Utiliza simuladores para probar los componentes
que no dependan de hardware físico."

No abre ningún dispositivo HID. Mantiene un ``ControllerState`` en memoria que se
puede editar directamente (útil para probar la interfaz gráfica y los tests
automatizados) y codifica/decodifica usando el mismo módulo ``dualcontrol.protocol``
que usaría un backend real basado en bytes crudos, así las pruebas ejercitan el
codificador de verdad y no un doble de prueba separado.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from dualcontrol import protocol
from dualcontrol.backend.base import BackendError, ControllerBackend
from dualcontrol.models import (
    AudioSettings,
    ConnectionState,
    ControllerState,
    HapticSettings,
    LightingSettings,
    TriggerSettings,
)


class SimulatedBackend(ControllerBackend):
    def __init__(self, *, fail_detect: bool = False) -> None:
        self._fail_detect = fail_detect
        self._state = ConnectionState.NOT_DETECTED
        self._controller_state = ControllerState()
        self._last_output: Optional[bytes] = None
        self._listeners: List[Callable[[ControllerState], None]] = []

        self._trigger_l2 = TriggerSettings()
        self._trigger_r2 = TriggerSettings()
        self._haptics = HapticSettings()
        self._lighting = LightingSettings()
        self._audio = AudioSettings()

    # --- ciclo de vida -----------------------------------------------------------
    def detect(self) -> bool:
        if self._fail_detect:
            self._state = ConnectionState.NOT_DETECTED
            return False
        self._state = ConnectionState.DETECTED
        return True

    def open(self) -> None:
        if self._fail_detect:
            raise BackendError("Simulador configurado para no detectar ningún mando")
        self._state = ConnectionState.OPENED
        self._encode_and_store()  # primer informe "enviado" al abrir

    def close(self) -> None:
        self._state = ConnectionState.NOT_DETECTED

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    # --- entrada -----------------------------------------------------------------
    def read_state(self) -> ControllerState:
        if self._state in (ConnectionState.NOT_DETECTED,):
            raise BackendError("El mando no está abierto")
        if self._state in (ConnectionState.OPENED, ConnectionState.DETECTED):
            self._state = ConnectionState.INPUT_OK
        return self._controller_state

    def on_state_changed(self, callback: Callable[[ControllerState], None]) -> None:
        self._listeners.append(callback)

    def inject_state(self, state: ControllerState) -> None:
        """Solo para pruebas/depuración: simula que llegó un nuevo informe de entrada."""
        self._controller_state = state
        for cb in self._listeners:
            cb(state)

    # --- salida --------------------------------------------------------------------
    def apply_trigger(self, side: str, settings: TriggerSettings) -> None:
        if side not in ("L2", "R2"):
            raise ValueError("side debe ser 'L2' o 'R2'")
        if side == "L2":
            self._trigger_l2 = settings.clamp()
        else:
            self._trigger_r2 = settings.clamp()
        self._encode_and_store()

    def apply_haptics(self, settings: HapticSettings) -> None:
        self._haptics = settings
        self._encode_and_store()

    def apply_lighting(self, settings: LightingSettings) -> None:
        self._lighting = settings
        self._encode_and_store()

    def apply_audio(self, settings: AudioSettings) -> None:
        self._audio = settings.clamp()
        self._encode_and_store()

    def restore_defaults(self) -> None:
        self._trigger_l2 = TriggerSettings()
        self._trigger_r2 = TriggerSettings()
        self._haptics = HapticSettings()
        self._lighting = LightingSettings()
        self._audio = AudioSettings()
        self._encode_and_store()

    def last_output_report(self) -> Optional[bytes]:
        return self._last_output

    # --- interno -------------------------------------------------------------------
    def _encode_and_store(self) -> None:
        self._last_output = protocol.encode_output_report(
            haptics=self._haptics,
            trigger_l2=self._trigger_l2,
            trigger_r2=self._trigger_r2,
            lighting=self._lighting,
            audio=self._audio,
        )
        if self._state in (ConnectionState.INPUT_OK, ConnectionState.OUTPUT_OK):
            self._state = ConnectionState.OUTPUT_OK
