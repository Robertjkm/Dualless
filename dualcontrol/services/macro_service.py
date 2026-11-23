"""Motor de Macros y Atajos de Windows por combos de botones del DualSense (v1.0.0)."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Set, Tuple

from PySide6.QtCore import QObject, Signal

from dualcontrol.models import ControllerState
from dualcontrol.services.settings_store import DEFAULT_MACROS
from dualcontrol.services.windows_integration import (
    VK_LWIN,
    VK_MEDIA_PLAY_PAUSE,
    VK_MENU,
    VK_SNAPSHOT,
    VK_TAB,
    VK_VOLUME_DOWN,
    VK_VOLUME_MUTE,
    VK_VOLUME_UP,
    send_key_combo,
)

MACRO_COMBO_LABELS: Tuple[Tuple[str, str], ...] = (
    ("ps+l1", "PS + L1"),
    ("ps+r1", "PS + R1"),
    ("mute", "Botón Mute (Mic)"),
    ("create+options", "Create + Options"),
    ("ps+triangle", "PS + △ (Triángulo)"),
)

MACRO_ACTION_LABELS: Tuple[Tuple[str, str], ...] = (
    ("none", "Desactivado"),
    ("volume_up", "Subir volumen (Windows)"),
    ("volume_down", "Bajar volumen (Windows)"),
    ("volume_mute", "Silenciar audio (Windows)"),
    ("play_pause", "Reproducir / Pausar multimedia"),
    ("screenshot", "Captura de pantalla (Win + ImprPant)"),
    ("alt_tab", "Cambiar ventana (Alt + Tab)"),
    ("next_profile", "Siguiente perfil de Dualless"),
)

_ACTION_KEYS: Dict[str, list[int]] = {
    "volume_up": [VK_VOLUME_UP],
    "volume_down": [VK_VOLUME_DOWN],
    "volume_mute": [VK_VOLUME_MUTE],
    "play_pause": [VK_MEDIA_PLAY_PAUSE],
    "screenshot": [VK_LWIN, VK_SNAPSHOT],
    "alt_tab": [VK_MENU, VK_TAB],
}


def combo_is_pressed(combo_key: str, state: ControllerState) -> bool:
    parts = [p.strip().lower() for p in combo_key.split("+") if p.strip()]
    if not parts:
        return False
    return all(bool(getattr(state, p, False)) for p in parts)


class MacroService(QObject):
    macro_triggered = Signal(str, str)  # combo_key, action_key

    def __init__(
        self,
        controller_service=None,
        *,
        key_sender: Callable[[list[int]], None] = send_key_combo,
        next_profile_cb: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._controller_service = controller_service
        self._key_sender = key_sender
        self._next_profile_cb = next_profile_cb
        self.enabled: bool = True
        self.macros: Dict[str, str] = dict(DEFAULT_MACROS)
        self._active_combos: Set[str] = set()

        if self._controller_service is not None:
            self._controller_service.state_changed.connect(self.process_state)

    def process_state(self, state: ControllerState) -> None:
        if not self.enabled:
            self._active_combos.clear()
            return

        for combo_key, action_key in list(self.macros.items()):
            if not action_key or action_key == "none":
                self._active_combos.discard(combo_key)
                continue
            pressed = combo_is_pressed(combo_key, state)
            if pressed and combo_key not in self._active_combos:
                self._active_combos.add(combo_key)
                self._execute_action(combo_key, action_key)
            elif not pressed and combo_key in self._active_combos:
                self._active_combos.discard(combo_key)

    def _execute_action(self, combo_key: str, action_key: str) -> None:
        if action_key == "next_profile":
            if self._next_profile_cb is not None:
                self._next_profile_cb()
        elif action_key in _ACTION_KEYS:
            self._key_sender(_ACTION_KEYS[action_key])
        self.macro_triggered.emit(combo_key, action_key)
