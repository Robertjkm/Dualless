"""Servicio de Mapeo libre a Teclado/Ratón, Dual Stage L2/R2 y sincronización de Mute (v1.2.0)."""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Set

from PySide6.QtCore import QObject, Signal

from dualcontrol.models import ControllerState, MappingSettings
from dualcontrol.services.windows_integration import (
    KEY_VK_MAP,
    VK_LWIN,
    VK_SNAPSHOT,
    VK_VOLUME_DOWN,
    VK_VOLUME_UP,
    mouse_button_event,
    send_key_combo,
    send_vk_event,
    toggle_windows_mic_mute,
)

DUAL_STAGE_THRESHOLD = 235  # 92% del recorrido físico del gatillo


class KeyboardMouseMapperService(QObject):
    """Traduce botones individuales del DualSense / DualSense Edge y la segunda etapa
    (Dual Stage) de L2/R2 en pulsaciones reales de teclado/ratón de Windows, con
    soporte de Turbo y sincronización del botón físico Mute."""

    mute_toggled = Signal(bool)  # True = silenciado

    def __init__(
        self,
        mapping_getter: Callable[[], MappingSettings],
        *,
        vk_sender: Callable[[int, bool], None] = send_vk_event,
        mouse_sender: Callable[[str, bool], None] = mouse_button_event,
        combo_sender: Callable[[list[int]], None] = send_key_combo,
        mic_toggle_fn: Callable[[], bool] = toggle_windows_mic_mute,
        on_mute_hardware_toggle: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._mapping_getter = mapping_getter
        self._vk_sender = vk_sender
        self._mouse_sender = mouse_sender
        self._combo_sender = combo_sender
        self._mic_toggle_fn = mic_toggle_fn
        self._on_mute_hardware_toggle = on_mute_hardware_toggle

        self.sync_windows_mute: bool = True
        self._held_actions: Set[str] = set()
        self._prev_mute_btn: bool = False

    def _emit_action(self, action_key: str, pressed: bool) -> None:
        if action_key == "mouse_left":
            self._mouse_sender("left", pressed)
        elif action_key == "mouse_right":
            self._mouse_sender("right", pressed)
        elif action_key in KEY_VK_MAP:
            self._vk_sender(KEY_VK_MAP[action_key], pressed)
        elif pressed:
            if action_key == "volume_up":
                self._combo_sender([VK_VOLUME_UP])
            elif action_key == "volume_down":
                self._combo_sender([VK_VOLUME_DOWN])
            elif action_key == "screenshot":
                self._combo_sender([VK_LWIN, VK_SNAPSHOT])

    def process_state(self, state: ControllerState, *, now_ts: Optional[float] = None) -> None:
        mute_now = bool(state.mute)
        if mute_now and not self._prev_mute_btn:
            if self.sync_windows_mute:
                self._mic_toggle_fn()
                if self._on_mute_hardware_toggle is not None:
                    self._on_mute_hardware_toggle()
        self._prev_mute_btn = mute_now

        cfg = self._mapping_getter().clamp()
        bindings: Dict[str, str] = dict(cfg.key_bindings or {})
        turbo_set = set(cfg.turbo_buttons or [])
        ts = time.monotonic() if now_ts is None else float(now_ts)
        turbo_high = (int(ts * cfg.turbo_rate_hz * 2.0) % 2) == 0

        desired_held: Set[str] = set()

        for btn_key, act_key in bindings.items():
            if not act_key or act_key == "none":
                continue
            if bool(getattr(state, btn_key, False)):
                if btn_key in turbo_set and not turbo_high:
                    continue
                desired_held.add(act_key)

        ds_threshold = max(175, min(252, int(round(cfg.dual_stage_threshold * 255.0))))
        if cfg.dual_stage_l2_action and cfg.dual_stage_l2_action != "none":
            if int(state.l2_value) >= ds_threshold:
                desired_held.add(cfg.dual_stage_l2_action)
        if cfg.dual_stage_r2_action and cfg.dual_stage_r2_action != "none":
            if int(state.r2_value) >= ds_threshold:
                desired_held.add(cfg.dual_stage_r2_action)

        for act in list(self._held_actions - desired_held):
            self._held_actions.discard(act)
            if act in KEY_VK_MAP or act in ("mouse_left", "mouse_right"):
                self._emit_action(act, False)

        for act in list(desired_held - self._held_actions):
            self._held_actions.add(act)
            self._emit_action(act, True)

    def release_all(self) -> None:
        for act in list(self._held_actions):
            if act in KEY_VK_MAP or act in ("mouse_left", "mouse_right"):
                self._emit_action(act, False)
        self._held_actions.clear()
