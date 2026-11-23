"""Backend real — comunicación USB HID directa con un Sony DualSense físico.

En Windows utiliza ``dualcontrol.backend.win32_hid`` (API nativa de Windows vía
``hid.dll`` y ``setupapi.dll``), por lo que NO necesita ``hidapi.dll`` externa ni
bibliotecas nativas adicionales.

En Linux/macOS intenta utilizar el paquete ``hid`` (``cython-hidapi``) si está
disponible.

Toda la codificación de informes de salida (gatillos adaptativos, hápticos,
iluminación) y decodificación de entradas (sticks, botones, IMU, panel táctil,
batería) usa ``dualcontrol.protocol``.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable, List, Optional

from dualcontrol import constants as C
from dualcontrol import protocol
from dualcontrol.backend.base import BackendError, ControllerBackend
from dualcontrol.backend.win32_hid import HidDeviceInfo, Win32HidDevice, enumerate_devices
from dualcontrol.models import (
    AudioSettings,
    ConnectionState,
    ControllerState,
    HapticSettings,
    LightingSettings,
    TriggerSettings,
)

_SUPPORTED_PIDS = (C.DUALSENSE_PRODUCT_ID, C.DUALSENSE_EDGE_PRODUCT_ID)


def list_connected_dualsense() -> List[dict]:
    """Enumera todos los mandos Sony DualSense conectados (USB y Bluetooth) para Multi-Mando."""
    if sys.platform != "win32":
        return []
    devices = enumerate_devices(C.SONY_VENDOR_ID, _SUPPORTED_PIDS)
    result = []
    for idx, d in enumerate(devices):
        result.append(
            {
                "index": idx,
                "connection_type": d.connection_type,
                "pid": d.product_id,
                "path": d.path,
            }
        )
    return result


class RealBackend(ControllerBackend):
    def __init__(self, device_index: int = 0) -> None:
        self._device: Optional[object] = None
        self._device_info: Optional[HidDeviceInfo] = None
        self._device_index: int = max(0, int(device_index))
        self._connection_type: str = "NONE"  # "USB" | "BT" | "NONE"
        self._state = ConnectionState.NOT_DETECTED
        self._listeners: List[Callable[[ControllerState], None]] = []
        self._last_output: Optional[bytes] = None

        self._lock = threading.Lock()
        self._latest_state: ControllerState = ControllerState()
        self._has_input = False
        self._read_error: Optional[str] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reading = threading.Event()

        self._trigger_l2 = TriggerSettings()
        self._trigger_r2 = TriggerSettings()
        self._haptics = HapticSettings()
        self._lighting = LightingSettings()
        self._audio = AudioSettings()

    # --- ciclo de vida ---------------------------------------------------------
    def detect(self) -> bool:
        if sys.platform == "win32":
            devices = enumerate_devices(C.SONY_VENDOR_ID, _SUPPORTED_PIDS)
            if devices:
                idx = self._device_index if self._device_index < len(devices) else 0
                self._device_info = devices[idx]
                if self._state == ConnectionState.NOT_DETECTED:
                    self._state = ConnectionState.DETECTED
                return True
            self._device_info = None
            self._connection_type = "NONE"
            self._state = ConnectionState.NOT_DETECTED
            return False

        # Fallback para Linux / macOS
        try:
            import hid  # type: ignore
        except Exception as exc:
            raise BackendError(
                "En Linux/macOS se requiere el paquete 'hidapi' (pip install hidapi) "
                "y la librería del sistema libhidapi."
            ) from exc

        devices = hid.enumerate(C.SONY_VENDOR_ID)
        found = any(d.get("product_id") in _SUPPORTED_PIDS for d in devices)
        self._state = ConnectionState.DETECTED if found else ConnectionState.NOT_DETECTED
        return found

    def open(self) -> None:
        self.close()
        self._read_error = None
        self._has_input = False

        if sys.platform == "win32":
            devices = enumerate_devices(C.SONY_VENDOR_ID, _SUPPORTED_PIDS)
            if not devices:
                self._connection_type = "NONE"
                self._state = ConnectionState.NOT_DETECTED
                raise BackendError(
                    "No se detectó ningún Sony DualSense conectado por USB. "
                    "Conecta el mando con un cable USB de datos y vuelve a intentarlo."
                )

            last_exc: Optional[Exception] = None
            ordered = ([devices[self._device_index]] + [d for i, d in enumerate(devices) if i != self._device_index]) if self._device_index < len(devices) else devices
            for info in ordered:
                try:
                    dev_w = Win32HidDevice(info)
                    self._device = dev_w
                    self._device_info = info
                    self._connection_type = info.connection_type
                    if info.connection_type == "BT":
                        # Desbloquear modo Bluetooth completo (informes 0x31 de 78 bytes)
                        dev_w.get_feature_report(C.BT_FEATURE_CALIBRATION_ID, C.BT_FEATURE_CALIBRATION_LEN)
                    break
                except OSError as exc:
                    last_exc = exc

            if self._device is None:
                self._state = ConnectionState.ERROR
                raise BackendError(
                    f"Se detectó el DualSense pero no se pudo abrir el dispositivo HID: {last_exc}"
                )

            self._state = ConnectionState.OPENED
            self._stop_reading.clear()
            self._reader_thread = threading.Thread(
                target=self._win32_reader_loop,
                name="Dualless-USB-Reader",
                daemon=True,
            )
            self._reader_thread.start()
            return

        # Fallback Linux / macOS con cython-hidapi
        try:
            import hid  # type: ignore
        except Exception as exc:
            self._state = ConnectionState.ERROR
            raise BackendError(
                "No se encontró el módulo 'hid' en este sistema. Instala 'hidapi'."
            ) from exc

        dev = hid.device()
        opened = False
        last_exc = None
        for pid in _SUPPORTED_PIDS:
            try:
                dev.open(C.SONY_VENDOR_ID, pid)
                dev.set_nonblocking(1)
                opened = True
                break
            except Exception as exc:
                last_exc = exc

        if not opened:
            self._state = ConnectionState.ERROR
            raise BackendError(f"No se pudo abrir el DualSense por USB: {last_exc}")

        self._device = dev
        self._state = ConnectionState.OPENED

    def close(self) -> None:
        self._stop_reading.set()
        dev = self._device
        self._device = None
        if dev is not None:
            try:
                dev.close()
            except Exception:
                pass
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        self._reader_thread = None
        self._connection_type = "NONE"
        self._state = ConnectionState.NOT_DETECTED

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    @property
    def connection_type(self) -> str:
        return self._connection_type

    # --- entrada ---------------------------------------------------------------
    def _win32_reader_loop(self) -> None:
        while not self._stop_reading.is_set():
            dev = self._device
            if not isinstance(dev, Win32HidDevice):
                break
            try:
                data = dev.read(timeout_ms=100)
            except OSError as exc:
                if not self._stop_reading.is_set():
                    self._read_error = f"DualSense desconectado o error de lectura USB: {exc}"
                    self._state = ConnectionState.ERROR
                break

            if not data:
                continue

            # Aceptar USB (0x01, >=54B), BT completo (0x31, >=55B) o BT simple (0x01, >=10B)
            if (data[0] == C.INPUT_REPORT_ID_USB and len(data) >= 10) or (data[0] == C.INPUT_REPORT_ID_BT and len(data) >= 55):
                try:
                    parsed = protocol.decode_input_report(data)
                except ValueError:
                    continue
                with self._lock:
                    self._latest_state = parsed
                    self._has_input = True
                    if self._state in (ConnectionState.OPENED, ConnectionState.DETECTED):
                        self._state = ConnectionState.INPUT_OK
                for cb in list(self._listeners):
                    try:
                        cb(parsed)
                    except Exception:
                        pass

    def read_state(self) -> ControllerState:
        if self._read_error is not None:
            err = self._read_error
            self._read_error = None
            raise BackendError(err)

        if self._device is None:
            raise BackendError("El mando no está abierto")

        if isinstance(self._device, Win32HidDevice):
            with self._lock:
                return self._latest_state

        # Fallback Linux / macOS (non-blocking hid.device)
        try:
            raw = bytes(self._device.read(64))  # type: ignore[attr-defined]
        except Exception as exc:
            self._state = ConnectionState.ERROR
            raise BackendError(f"Error al leer del DualSense: {exc}") from exc

        if raw and raw[0] == C.INPUT_REPORT_ID_USB and len(raw) >= 54:
            self._latest_state = protocol.decode_input_report(raw)
            if self._state in (ConnectionState.OPENED, ConnectionState.DETECTED):
                self._state = ConnectionState.INPUT_OK
        return self._latest_state

    def on_state_changed(self, callback: Callable[[ControllerState], None]) -> None:
        self._listeners.append(callback)

    # --- salida ----------------------------------------------------------------
    def apply_trigger(self, side: str, settings: TriggerSettings) -> None:
        if side not in ("L2", "R2"):
            raise ValueError("side debe ser 'L2' o 'R2'")
        if side == "L2":
            self._trigger_l2 = settings.clamp()
        else:
            self._trigger_r2 = settings.clamp()
        self._send_output_report()

    def apply_haptics(self, settings: HapticSettings) -> None:
        self._haptics = settings
        self._send_output_report()

    def apply_lighting(self, settings: LightingSettings) -> None:
        self._lighting = settings
        self._send_output_report()

    def apply_audio(self, settings: AudioSettings) -> None:
        self._audio = settings.clamp()
        self._send_output_report()

    def restore_defaults(self) -> None:
        self._trigger_l2 = TriggerSettings()
        self._trigger_r2 = TriggerSettings()
        self._haptics = HapticSettings()
        self._lighting = LightingSettings()
        self._audio = AudioSettings()
        if self._device is not None:
            self._send_output_report()

    def last_output_report(self) -> Optional[bytes]:
        return self._last_output

    def _send_output_report(self) -> None:
        if self._device is None:
            raise BackendError("El mando no está abierto. Conecta el DualSense por USB primero.")

        if self._connection_type == "BT":
            report = protocol.encode_output_report_bt(
                haptics=self._haptics,
                trigger_l2=self._trigger_l2,
                trigger_r2=self._trigger_r2,
                lighting=self._lighting,
                audio=self._audio,
            )
        else:
            report = protocol.encode_output_report(
                haptics=self._haptics,
                trigger_l2=self._trigger_l2,
                trigger_r2=self._trigger_r2,
                lighting=self._lighting,
                audio=self._audio,
            )

        try:
            if isinstance(self._device, Win32HidDevice):
                out_len = self._device.output_report_length
                self._device.write(report)
                self._last_output = report[:out_len] if len(report) >= out_len else report
            else:
                self._device.write(report)  # type: ignore[attr-defined]
                self._last_output = report
        except Exception as exc:
            self._state = ConnectionState.ERROR
            raise BackendError(f"Error al enviar comando HID al DualSense: {exc}") from exc

        self._state = ConnectionState.OUTPUT_OK
