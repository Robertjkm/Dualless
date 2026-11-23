"""Adaptadores de mando virtual (Xbox 360 XInput y DualShock 4) usando ViGEmBus vía ``vgamepad``.

Cumple estrictamente con las secciones 10 y 14:
- La emulación es 100% opcional (Modo Nativo por defecto).
- NUNCA instala controladores de modo kernel ni oculta dispositivos en segundo plano.
- Verifica de forma transparente si ``vgamepad`` y el driver ``ViGEmBus`` están
  disponibles en Windows, y guía al usuario si falta alguno.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from dualcontrol.models import ControllerState, MappingSettings
from dualcontrol.virtualcontroller.base import VirtualControllerAdapter, VirtualControllerError
from dualcontrol.virtualcontroller.mapper import MapperRuntimeState, XInputSnapshot, map_dualsense_to_xinput

VIGEMBUS_DOWNLOAD_URL = "https://github.com/nefarius/ViGEmBus/releases"


@dataclass
class XInputPrerequisites:
    is_windows: bool
    vgamepad_installed: bool
    vigembus_driver_detected: bool
    summary: str
    dualless_vhf_detected: bool = False

    @property
    def ready(self) -> bool:
        return self.is_windows and self.vgamepad_installed and self.vigembus_driver_detected


def _detect_vigembus_windows() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        for subkey in (
            r"SYSTEM\CurrentControlSet\Services\ViGEmBus",
            r"SYSTEM\CurrentControlSet\Services\vigembus",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey):
                    return True
            except OSError:
                continue
    except Exception:
        return False
    return False


def _detect_dualless_vhf_windows() -> bool:
    """Detecta si el usuario compiló e instaló manualmente la plantilla KMDF/VHF de Dualless."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\DuallessVhf"):
            return True
    except OSError:
        return False


def extract_ds4_lightbar_rgb(lightbar_color) -> Optional[tuple[int, int, int]]:
    """Extrae (R, G, B) desde el objeto lightbar_color que entrega vgamepad / ViGEmBus."""
    if lightbar_color is None:
        return None
    for attrs in (("Red", "Green", "Blue"), ("red", "green", "blue"), ("r", "g", "b")):
        if all(hasattr(lightbar_color, a) for a in attrs):
            return (
                max(0, min(255, int(getattr(lightbar_color, attrs[0])))),
                max(0, min(255, int(getattr(lightbar_color, attrs[1])))),
                max(0, min(255, int(getattr(lightbar_color, attrs[2])))),
            )
    if isinstance(lightbar_color, (tuple, list)) and len(lightbar_color) >= 3:
        return (
            max(0, min(255, int(lightbar_color[0]))),
            max(0, min(255, int(lightbar_color[1]))),
            max(0, min(255, int(lightbar_color[2]))),
        )
    return None


def check_xinput_prerequisites() -> XInputPrerequisites:
    is_win = sys.platform == "win32"
    has_vgamepad = importlib.util.find_spec("vgamepad") is not None
    has_driver = _detect_vigembus_windows() if is_win else False
    has_vhf = _detect_dualless_vhf_windows() if is_win else False

    if not is_win:
        return XInputPrerequisites(
            is_windows=False,
            vgamepad_installed=has_vgamepad,
            vigembus_driver_detected=False,
            summary="La emulación de mando virtual (ViGEmBus) solo está disponible en Windows.",
        )

    if not has_vgamepad:
        return XInputPrerequisites(
            is_windows=True,
            vgamepad_installed=False,
            vigembus_driver_detected=has_driver,
            summary="Falta el paquete Python 'vgamepad'. Vuelve a ejecutar ejecutar.bat para instalarlo.",
        )

    if not has_driver:
        return XInputPrerequisites(
            is_windows=True,
            vgamepad_installed=True,
            vigembus_driver_detected=False,
            summary=(
                "vgamepad está listo, pero falta el driver ViGEmBus en Windows. "
                "Descárgalo e instálalo manualmente desde el enlace oficial (Dualless "
                "no instala drivers de kernel sin tu autorización)."
            ),
        )

    return XInputPrerequisites(
        is_windows=True,
        vgamepad_installed=True,
        vigembus_driver_detected=True,
        dualless_vhf_detected=has_vhf,
        summary="Todo listo: vgamepad y ViGEmBus detectados en Windows.",
    )


class XInputViGEmAdapter(VirtualControllerAdapter):
    """Emula un mando Xbox 360 virtual en Windows usando vgamepad / ViGEmBus."""

    def __init__(self) -> None:
        self._pad = None
        self._vg = None
        self._active = False
        self._last_snapshot: Optional[XInputSnapshot] = None
        self._runtime_state = MapperRuntimeState()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def last_snapshot(self) -> Optional[XInputSnapshot]:
        return self._last_snapshot

    def start(
        self,
        rumble_callback: Optional[Callable[[int, int], None]] = None,
        led_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> None:
        if self._active:
            return
        if sys.platform != "win32":
            raise VirtualControllerError("La emulación Xbox 360 solo está disponible en Windows.")

        try:
            import vgamepad as vg  # type: ignore
        except Exception as exc:
            raise VirtualControllerError(
                "No se pudo importar 'vgamepad'. Ejecuta ejecutar.bat para completar las dependencias."
            ) from exc

        try:
            pad = vg.VX360Gamepad()
        except Exception as exc:
            raise VirtualControllerError(
                "No se pudo crear el mando virtual Xbox 360. Verifica que el driver "
                f"ViGEmBus esté instalado en Windows ({VIGEMBUS_DOWNLOAD_URL}). Detalle: {exc}"
            ) from exc

        if rumble_callback is not None:
            def _on_notification(client, target, large_motor, small_motor, led_number, user_data):
                try:
                    rumble_callback(int(large_motor), int(small_motor))
                except Exception:
                    pass

            try:
                pad.register_notification(callback_function=_on_notification)
            except Exception:
                pass

        self._vg = vg
        self._pad = pad
        self._active = True

    def stop(self) -> None:
        self._active = False
        pad = self._pad
        self._pad = None
        if pad is not None:
            try:
                pad.reset()
                pad.update()
            except Exception:
                pass
            try:
                del pad
            except Exception:
                pass

    def feed_state(self, state: ControllerState, mapping: Optional[MappingSettings] = None) -> None:
        if not self._active or self._pad is None or self._vg is None:
            return

        snap = map_dualsense_to_xinput(state, mapping=mapping, runtime_state=self._runtime_state)
        self._last_snapshot = snap

        vg = self._vg
        pad = self._pad
        btn_enum = vg.XUSB_BUTTON

        button_pairs = (
            (btn_enum.XUSB_GAMEPAD_A, snap.a),
            (btn_enum.XUSB_GAMEPAD_B, snap.b),
            (btn_enum.XUSB_GAMEPAD_X, snap.x),
            (btn_enum.XUSB_GAMEPAD_Y, snap.y),
            (btn_enum.XUSB_GAMEPAD_LEFT_SHOULDER, snap.lb),
            (btn_enum.XUSB_GAMEPAD_RIGHT_SHOULDER, snap.rb),
            (btn_enum.XUSB_GAMEPAD_BACK, snap.back),
            (btn_enum.XUSB_GAMEPAD_START, snap.start),
            (btn_enum.XUSB_GAMEPAD_GUIDE, snap.guide),
            (btn_enum.XUSB_GAMEPAD_LEFT_THUMB, snap.left_thumb),
            (btn_enum.XUSB_GAMEPAD_RIGHT_THUMB, snap.right_thumb),
            (btn_enum.XUSB_GAMEPAD_DPAD_UP, snap.dpad_up),
            (btn_enum.XUSB_GAMEPAD_DPAD_DOWN, snap.dpad_down),
            (btn_enum.XUSB_GAMEPAD_DPAD_LEFT, snap.dpad_left),
            (btn_enum.XUSB_GAMEPAD_DPAD_RIGHT, snap.dpad_right),
        )

        for code, pressed in button_pairs:
            if pressed:
                pad.press_button(button=code)
            else:
                pad.release_button(button=code)

        pad.left_trigger(value=snap.left_trigger)
        pad.right_trigger(value=snap.right_trigger)
        pad.left_joystick(x_value=snap.left_x, y_value=snap.left_y)
        pad.right_joystick(x_value=snap.right_x, y_value=snap.right_y)
        pad.update()


class DS4ViGEmAdapter(VirtualControllerAdapter):
    """Emula un mando Sony DualShock 4 virtual en Windows usando vgamepad / ViGEmBus."""

    def __init__(self) -> None:
        self._pad = None
        self._vg = None
        self._active = False
        self._last_snapshot: Optional[XInputSnapshot] = None
        self._runtime_state = MapperRuntimeState()

    @property
    def is_active(self) -> bool:
        return self._active

    def start(
        self,
        rumble_callback: Optional[Callable[[int, int], None]] = None,
        led_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> None:
        if self._active:
            return
        if sys.platform != "win32":
            raise VirtualControllerError("La emulación DualShock 4 solo está disponible en Windows.")

        try:
            import vgamepad as vg  # type: ignore
        except Exception as exc:
            raise VirtualControllerError(
                "No se pudo importar 'vgamepad'. Ejecuta ejecutar.bat para completar las dependencias."
            ) from exc

        try:
            pad = vg.VDS4Gamepad()
        except Exception as exc:
            raise VirtualControllerError(
                "No se pudo crear el mando virtual DualShock 4. Verifica que el driver "
                f"ViGEmBus esté instalado en Windows ({VIGEMBUS_DOWNLOAD_URL}). Detalle: {exc}"
            ) from exc

        if rumble_callback is not None or led_callback is not None:
            def _on_notification(client, target, large_motor, small_motor, lightbar_color, user_data):
                if rumble_callback is not None:
                    try:
                        rumble_callback(int(large_motor), int(small_motor))
                    except Exception:
                        pass
                if led_callback is not None:
                    try:
                        rgb = extract_ds4_lightbar_rgb(lightbar_color)
                        if rgb is not None:
                            led_callback(rgb[0], rgb[1], rgb[2])
                    except Exception:
                        pass

            try:
                pad.register_notification(callback_function=_on_notification)
            except Exception:
                pass

        self._vg = vg
        self._pad = pad
        self._active = True

    def stop(self) -> None:
        self._active = False
        pad = self._pad
        self._pad = None
        if pad is not None:
            try:
                pad.reset()
                pad.update()
            except Exception:
                pass
            try:
                del pad
            except Exception:
                pass

    def feed_state(self, state: ControllerState, mapping: Optional[MappingSettings] = None) -> None:
        if not self._active or self._pad is None or self._vg is None:
            return

        snap = map_dualsense_to_xinput(state, mapping=mapping, runtime_state=self._runtime_state)
        self._last_snapshot = snap

        vg = self._vg
        pad = self._pad
        b = vg.DS4_BUTTONS
        sb = vg.DS4_SPECIAL_BUTTONS

        pairs = (
            (b.DS4_BUTTON_CROSS, snap.a),
            (b.DS4_BUTTON_CIRCLE, snap.b),
            (b.DS4_BUTTON_SQUARE, snap.x),
            (b.DS4_BUTTON_TRIANGLE, snap.y),
            (b.DS4_BUTTON_SHOULDER_LEFT, snap.lb),
            (b.DS4_BUTTON_SHOULDER_RIGHT, snap.rb),
            (b.DS4_BUTTON_SHARE, snap.back),
            (b.DS4_BUTTON_OPTIONS, snap.start),
            (b.DS4_BUTTON_THUMB_LEFT, snap.left_thumb),
            (b.DS4_BUTTON_THUMB_RIGHT, snap.right_thumb),
        )
        for code, pressed in pairs:
            if pressed:
                pad.press_button(button=code)
            else:
                pad.release_button(button=code)

        if snap.guide:
            pad.press_special_button(special_button=sb.DS4_SPECIAL_BUTTON_PS)
        else:
            pad.release_special_button(special_button=sb.DS4_SPECIAL_BUTTON_PS)

        if state.touchpad_button:
            pad.press_special_button(special_button=sb.DS4_SPECIAL_BUTTON_TOUCHPAD)
        else:
            pad.release_special_button(special_button=sb.DS4_SPECIAL_BUTTON_TOUCHPAD)

        # D-pad DS4
        d = vg.DS4_DPAD_DIRECTIONS
        dpad_map = {
            (True, False, False, False): d.DS4_BUTTON_DPAD_NORTH,
            (True, False, False, True): d.DS4_BUTTON_DPAD_NORTHEAST,
            (False, False, False, True): d.DS4_BUTTON_DPAD_EAST,
            (False, True, False, True): d.DS4_BUTTON_DPAD_SOUTHEAST,
            (False, True, False, False): d.DS4_BUTTON_DPAD_SOUTH,
            (False, True, True, False): d.DS4_BUTTON_DPAD_SOUTHWEST,
            (False, False, True, False): d.DS4_BUTTON_DPAD_WEST,
            (True, False, True, False): d.DS4_BUTTON_DPAD_NORTHWEST,
        }
        pad.directional_pad(
            direction=dpad_map.get(
                (snap.dpad_up, snap.dpad_down, snap.dpad_left, snap.dpad_right),
                d.DS4_BUTTON_DPAD_NONE,
            )
        )

        # Sticks DS4 usan rango 0..255 (invertiendo Y de vuelta a 0=arriba)
        def _s16_to_u8(val: int, invert_y: bool = False) -> int:
            v = -val if invert_y else val
            return max(0, min(255, int(round(((v + 32768) / 65535.0) * 255))))

        pad.left_trigger(value=snap.left_trigger)
        pad.right_trigger(value=snap.right_trigger)
        pad.left_joystick(x_value=_s16_to_u8(snap.left_x), y_value=_s16_to_u8(snap.left_y, True))
        pad.right_joystick(x_value=_s16_to_u8(snap.right_x), y_value=_s16_to_u8(snap.right_y, True))
        pad.update()


class SimulatedXInputAdapter(VirtualControllerAdapter):
    """Adaptador simulado para pruebas automatizadas sin driver ViGEmBus."""

    def __init__(self) -> None:
        self._active = False
        self.last_snapshot: Optional[XInputSnapshot] = None
        self.frames_sent: int = 0

    @property
    def is_active(self) -> bool:
        return self._active

    def start(
        self,
        rumble_callback: Optional[Callable[[int, int], None]] = None,
        led_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    def feed_state(self, state: ControllerState, mapping: Optional[MappingSettings] = None) -> None:
        if not self._active:
            return
        self.last_snapshot = map_dualsense_to_xinput(state, mapping=mapping)
        self.frames_sent += 1
