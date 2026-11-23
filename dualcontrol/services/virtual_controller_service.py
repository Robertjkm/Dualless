"""Servicio Qt que administra el dispositivo virtual (Native, Xbox 360, DualShock 4 y DualSense).

Conecta la salida en vivo de ``ControllerService`` hacia el adaptador activo, gestiona
los interruptores de Passthrough (Rumble, Adaptive Triggers, LED real en DS4),
el motor **Rumble-to-Triggers** (vibración -> gatillos adaptativos L2/R2),
Key Repeat Rate, reinicio anti doble entrada y el feed de datos en vivo.
"""

from __future__ import annotations

import datetime
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from dualcontrol.models import (
    ControllerState,
    HapticSettings,
    LightingSettings,
    MappingSettings,
    TriggerMode,
    TriggerSettings,
)
from dualcontrol.virtualcontroller.base import (
    VirtualControllerAdapter,
    VirtualControllerError,
    VirtualControllerMode,
)
from dualcontrol.virtualcontroller.mapper import map_dualsense_to_xinput
from dualcontrol.virtualcontroller.xinput_vigem import (
    DS4ViGEmAdapter,
    XInputPrerequisites,
    XInputViGEmAdapter,
    check_xinput_prerequisites,
)


def compute_triggers_from_rumble(
    large_motor: int,
    small_motor: int,
    *,
    strength: float = 1.0,
) -> Tuple[TriggerSettings, TriggerSettings]:
    """Traduce la vibración entrante de un juego (large_motor / small_motor en 0..255)
    en efectos dinámicos de gatillos adaptativos para L2 y R2 (Nivel 3).

    - Si ambos motores están por debajo del umbral (< 18), relaja ambos gatillos (OFF).
    - Motor pequeño fuerte (disparos/impactos rápidos): pulso táctil en R2 y resistencia en L2.
    - Motor grande fuerte (explosiones/motor): resistencia firme progresiva en L2 y R2.
    """
    lm = max(0, min(255, int(large_motor)))
    sm = max(0, min(255, int(small_motor)))
    gain = max(0.25, min(1.5, float(strength)))

    if lm < 18 and sm < 18:
        off = TriggerSettings(enabled=False, mode=TriggerMode.OFF, forces=[0, 0, 0, 0, 0, 0, 0], preset_name="off")
        return off, TriggerSettings(enabled=False, mode=TriggerMode.OFF, forces=[0, 0, 0, 0, 0, 0, 0], preset_name="off")

    force_l2 = max(40, min(255, int(round(max(lm, sm * 0.65) * gain))))
    force_r2 = max(40, min(255, int(round(max(sm, lm * 0.85) * gain))))

    # R2: pulso dinámico si predomina el motor de alta frecuencia (disparos / retroceso)
    if sm >= 110:
        freq = max(3, min(12, int(round(sm / 22.0))))
        r2 = TriggerSettings(
            enabled=True,
            mode=TriggerMode.PULSE_AB,
            forces=[1, force_r2, freq, max(60, force_r2 - 30), 6, force_r2, 0],
            preset_name="rumble_recoil",
        ).clamp()
    elif sm >= 45:
        r2 = TriggerSettings(
            enabled=True,
            mode=TriggerMode.PULSE,
            forces=[2, force_r2, 5, 0, 0, 0, 0],
            preset_name="rumble_pulse",
        ).clamp()
    else:
        r2 = TriggerSettings(
            enabled=True,
            mode=TriggerMode.RIGID,
            forces=[2, force_r2, 0, 0, 0, 0, 0],
            preset_name="rumble_rigid",
        ).clamp()

    # L2: resistencia proporcional a explosiones / baja frecuencia
    if lm >= 130:
        l2 = TriggerSettings(
            enabled=True,
            mode=TriggerMode.RIGID_AB,
            forces=[1, force_l2, 0, 0, 0, 0, 0],
            preset_name="rumble_heavy",
        ).clamp()
    else:
        l2 = TriggerSettings(
            enabled=True,
            mode=TriggerMode.RIGID,
            forces=[2, force_l2, 0, 0, 0, 0, 0],
            preset_name="rumble_feedback",
        ).clamp()

    return l2, r2


class VirtualControllerService(QObject):
    mode_changed = Signal(str)               # "nativo" | "xinput" | "ds4" | "dualsense"
    status_changed = Signal(bool, str)       # active, message
    error_occurred = Signal(str)
    preview_updated = Signal(object)         # XInputSnapshot
    data_feed_logged = Signal(str)
    led_passthrough_color = Signal(int, int, int)  # R, G, B recibidos de DS4 ViGEmBus
    _rumble_received = Signal(int, int)
    _led_received = Signal(int, int, int)

    def __init__(
        self,
        controller_service,
        adapter: Optional[VirtualControllerAdapter] = None,
        *,
        lighting_getter: Optional[Callable[[], LightingSettings]] = None,
        triggers_restore_cb: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._controller_service = controller_service
        self._custom_adapter = adapter
        self._lighting_getter = lighting_getter
        self._triggers_restore_cb = triggers_restore_cb
        self._xinput_adapter: VirtualControllerAdapter = adapter or XInputViGEmAdapter()
        self._ds4_adapter: VirtualControllerAdapter = DS4ViGEmAdapter()
        self._active_adapter: Optional[VirtualControllerAdapter] = None

        self._mode = VirtualControllerMode.NATIVE
        self._rumble_passthrough = True
        self._triggers_passthrough = True
        self._led_passthrough = True
        self._rumble_to_triggers = False
        self._rumble_to_triggers_strength = 1.0
        self._rumble_triggers_active = False
        self._last_r2t_sig: Optional[Tuple[int, int]] = None
        self._last_led_rgb: Optional[Tuple[int, int, int]] = None
        self._dualsense_audio_device = False
        self._key_repeat_rate = "Do Not Repeat"
        self._feed_enabled = False
        self._last_error = ""
        self._mapping = MappingSettings()
        self._last_feed_sig = ""

        self._controller_service.state_changed.connect(self._on_controller_state)
        self._rumble_received.connect(self._apply_rumble_main_thread)
        self._led_received.connect(self._apply_led_main_thread)

    @property
    def mode(self) -> VirtualControllerMode:
        return self._mode

    @property
    def is_xinput_active(self) -> bool:
        return self._active_adapter is not None and self._active_adapter.is_active

    @property
    def rumble_passthrough(self) -> bool:
        return self._rumble_passthrough

    @property
    def triggers_passthrough(self) -> bool:
        return self._triggers_passthrough

    @property
    def led_passthrough(self) -> bool:
        return self._led_passthrough

    @property
    def rumble_to_triggers(self) -> bool:
        return self._rumble_to_triggers

    @property
    def rumble_to_triggers_strength(self) -> float:
        return self._rumble_to_triggers_strength

    @property
    def dualsense_audio_device(self) -> bool:
        return self._dualsense_audio_device

    @property
    def key_repeat_rate(self) -> str:
        return self._key_repeat_rate

    @property
    def last_error(self) -> str:
        return self._last_error

    def set_rumble_passthrough(self, enabled: bool) -> None:
        self._rumble_passthrough = bool(enabled)

    def set_triggers_passthrough(self, enabled: bool) -> None:
        self._triggers_passthrough = bool(enabled)

    def set_led_passthrough(self, enabled: bool) -> None:
        self._led_passthrough = bool(enabled)
        if not self._led_passthrough:
            self._last_led_rgb = None

    def set_rumble_to_triggers(self, enabled: bool) -> None:
        self._rumble_to_triggers = bool(enabled)
        if not self._rumble_to_triggers and self._rumble_triggers_active:
            self._release_rumble_triggers()

    def set_rumble_to_triggers_strength(self, strength: float) -> None:
        self._rumble_to_triggers_strength = max(0.25, min(1.5, float(strength)))

    def set_dualsense_audio_device(self, enabled: bool) -> None:
        self._dualsense_audio_device = bool(enabled)

    def set_key_repeat_rate(self, rate: str) -> None:
        self._key_repeat_rate = str(rate)

    def set_feed_enabled(self, enabled: bool) -> None:
        self._feed_enabled = bool(enabled)

    def set_mapping(self, mapping: MappingSettings) -> None:
        self._mapping = mapping.clamp()

    def check_prerequisites(self) -> XInputPrerequisites:
        return check_xinput_prerequisites()

    def _emit_feed(self, text: str) -> None:
        if not self._feed_enabled:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.data_feed_logged.emit(f"[{ts}] {text}")

    def _release_rumble_triggers(self) -> None:
        self._rumble_triggers_active = False
        self._last_r2t_sig = None
        if self._triggers_restore_cb is not None:
            self._triggers_restore_cb()
        else:
            off = TriggerSettings(enabled=False, mode=TriggerMode.OFF)
            self._controller_service.apply_trigger("L2", off)
            self._controller_service.apply_trigger("R2", off)

    def _stop_current_adapter(self) -> None:
        if self._rumble_triggers_active:
            self._release_rumble_triggers()
        if self._active_adapter is not None:
            try:
                self._active_adapter.stop()
            except Exception:
                pass
            self._active_adapter = None
        self._last_led_rgb = None

    def set_mode(self, mode: VirtualControllerMode) -> bool:
        self._last_error = ""
        self._stop_current_adapter()

        if mode == VirtualControllerMode.NATIVE:
            self._mode = VirtualControllerMode.NATIVE
            self.mode_changed.emit(self._mode.value)
            self.status_changed.emit(False, "Native Mode activo — DualSense físico sin emulación")
            self._emit_feed("MODE -> Native Mode")
            return True

        if mode == VirtualControllerMode.DUALSENSE:
            prereqs = self.check_prerequisites()
            self._mode = VirtualControllerMode.DUALSENSE
            self.mode_changed.emit(self._mode.value)
            if prereqs.dualless_vhf_detected:
                msg = "DualSense Emulation — Driver KMDF/VHF de Dualless detectado (modo experimental)"
            else:
                msg = (
                    "DualSense Emulation (Modo Passthrough Nativo — ViGEmBus solo emula Xbox 360 / DS4; "
                    "ver driver_vhf_template/README_WDK.md para plantilla KMDF/VHF)"
                )
            self.status_changed.emit(False, msg)
            self._emit_feed(f"MODE -> {msg}")
            return True

        target_adapter = (
            self._xinput_adapter if mode == VirtualControllerMode.XINPUT else self._ds4_adapter
        )
        try:
            target_adapter.start(
                rumble_callback=lambda l_mot, r_mot: self._rumble_received.emit(l_mot, r_mot),
                led_callback=(
                    (lambda r, g, b: self._led_received.emit(r, g, b))
                    if mode == VirtualControllerMode.DUALSHOCK4
                    else None
                ),
            )
        except TypeError:
            # Compatibilidad con adaptadores personalizados de prueba con firma start(rumble_callback=...)
            try:
                target_adapter.start(
                    rumble_callback=lambda l_mot, r_mot: self._rumble_received.emit(l_mot, r_mot)
                )
            except VirtualControllerError as exc:
                self._last_error = str(exc)
                self._mode = VirtualControllerMode.NATIVE
                self.error_occurred.emit(self._last_error)
                self.status_changed.emit(False, f"No se pudo activar {mode.value}: {self._last_error}")
                self.mode_changed.emit(self._mode.value)
                return False
        except VirtualControllerError as exc:
            self._last_error = str(exc)
            self._mode = VirtualControllerMode.NATIVE
            self.error_occurred.emit(self._last_error)
            self.status_changed.emit(False, f"No se pudo activar {mode.value}: {self._last_error}")
            self.mode_changed.emit(self._mode.value)
            return False

        self._active_adapter = target_adapter
        self._mode = mode
        self.mode_changed.emit(self._mode.value)
        label = (
            "Xbox 360 Emulation activa (XInput)"
            if mode == VirtualControllerMode.XINPUT
            else "DualShock 4 Emulation activa (DS4 + LED Passthrough)"
        )
        self.status_changed.emit(True, label)
        self._emit_feed(f"MODE -> {label}")
        return True

    def fix_double_input(self) -> None:
        """Reinicia la conexión del mando físico y del dispositivo virtual para limpiar doble entrada."""
        current_mode = self._mode
        self._emit_feed("FIX DOUBLE INPUT -> reiniciando conexión...")
        self._stop_current_adapter()
        self._controller_service.disconnect_controller()

        def _reconnect() -> None:
            self._controller_service.connect_controller()
            if current_mode != VirtualControllerMode.NATIVE:
                self.set_mode(current_mode)
            self._emit_feed("FIX DOUBLE INPUT -> reconexión completada")

        QTimer.singleShot(350, _reconnect)

    def _on_controller_state(self, state: ControllerState) -> None:
        if not self.is_xinput_active or self._active_adapter is None:
            return
        try:
            self._active_adapter.feed_state(state, mapping=self._mapping)
        except Exception as exc:
            self._last_error = str(exc)
            self.error_occurred.emit(self._last_error)
            return

        snap = map_dualsense_to_xinput(state, mapping=self._mapping)
        self.preview_updated.emit(snap)

        if self._feed_enabled:
            sig = f"{snap.pressed_labels()}|{snap.left_trigger}|{snap.right_trigger}|{snap.left_x//1024}|{snap.right_x//1024}"
            if sig != self._last_feed_sig:
                self._last_feed_sig = sig
                btns = ",".join(snap.pressed_labels()) or "none"
                self._emit_feed(
                    f"OUT({self._mode.value}) btns=[{btns}] LT={snap.left_trigger} RT={snap.right_trigger} "
                    f"LS=({snap.left_x},{snap.left_y}) RS=({snap.right_x},{snap.right_y})"
                )

    def _apply_rumble_main_thread(self, large_motor: int, small_motor: int) -> None:
        lm = max(0, min(255, int(large_motor)))
        sm = max(0, min(255, int(small_motor)))
        self._emit_feed(f"IN(rumble) L={lm} R={sm}")
        if not self.is_xinput_active:
            return

        if self._rumble_passthrough:
            self._controller_service.apply_haptics(
                HapticSettings(
                    left_motor=lm,
                    right_motor=sm,
                    use_haptics=True,
                )
            )

        if self._rumble_to_triggers:
            # Cuantizar a bloques de 16 para evitar saturar escrituras HID en transiciones mínimas
            q_sig = (lm // 16, sm // 16)
            if q_sig != self._last_r2t_sig:
                self._last_r2t_sig = q_sig
                if lm < 18 and sm < 18:
                    if self._rumble_triggers_active:
                        self._release_rumble_triggers()
                else:
                    l2_cfg, r2_cfg = compute_triggers_from_rumble(
                        lm, sm, strength=self._rumble_to_triggers_strength
                    )
                    self._controller_service.apply_trigger("L2", l2_cfg)
                    self._controller_service.apply_trigger("R2", r2_cfg)
                    self._rumble_triggers_active = True

    def _apply_led_main_thread(self, red: int, green: int, blue: int) -> None:
        r = max(0, min(255, int(red)))
        g = max(0, min(255, int(green)))
        b = max(0, min(255, int(blue)))
        self._emit_feed(f"IN(ds4_led) RGB=({r},{g},{b})")
        if not self._led_passthrough or not self.is_xinput_active:
            return
        if self._last_led_rgb == (r, g, b):
            return
        self._last_led_rgb = (r, g, b)

        base = self._lighting_getter() if self._lighting_getter is not None else LightingSettings()
        new_light = LightingSettings(
            red=r,
            green=g,
            blue=b,
            brightness=base.brightness,
            player_led=base.player_led,
            player_led_fade=base.player_led_fade,
            effect_mode="static",
            lightbar_brightness=base.lightbar_brightness,
            effect_speed=base.effect_speed,
        ).clamp()
        self._controller_service.apply_lighting(new_light)
        self.led_passthrough_color.emit(r, g, b)

    def shutdown(self) -> None:
        self._stop_current_adapter()
