"""Servicio Audio To Rumble & HD USB 4-Channel Haptics (WASAPI Loopback, v1.1.0).

Modo 1 — HD USB 4-Channel Haptics (cuando Haptic Feedback Mode está activo y el
DualSense está conectado por USB como dispositivo de audio de 4 canales):
  Captura el audio del sistema por WASAPI Loopback, aplica un filtro paso-bajo
  táctil (40–180 Hz) con realce de transitorios y envía la señal estéreo directamente
  a los canales 3 y 4 del DualSense (actuadores hápticos VCM izquierdo y derecho),
  dejando los canales 1 y 2 (auriculares) en silencio.

Modo 2 — Rumble HID estándar (cuando Rumble Mode está activo o por Bluetooth):
  Traduce la energía RMS y picos del audio en comandos HID de vibración para los
  motores del mando.
"""

from __future__ import annotations

import array
import math
import sys
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from dualcontrol.models import HapticSettings


def compute_rumble_from_pcm16(pcm_bytes: bytes, gain: float = 2.6) -> tuple[int, int]:
    """Calcula (left_motor, right_motor) en 0..255 a partir de audio PCM 16-bit estéreo."""
    if not pcm_bytes or len(pcm_bytes) < 4:
        return 0, 0
    samples = array.array("h")
    samples.frombytes(pcm_bytes[: (len(pcm_bytes) // 2) * 2])
    if not samples:
        return 0, 0
    sq_sum = 0.0
    peak = 0
    step = max(1, len(samples) // 256)
    count = 0
    for i in range(0, len(samples), step):
        v = abs(samples[i])
        sq_sum += v * v
        if v > peak:
            peak = v
        count += 1
    rms = math.sqrt(sq_sum / max(1, count)) / 32768.0
    peak_norm = peak / 32768.0
    if rms < 0.015:
        return 0, 0
    left = max(0, min(255, int(round(rms * gain * 255.0))))
    right = max(0, min(255, int(round(peak_norm * (gain * 0.75) * 255.0))))
    return left, right


def process_pcm16_to_usb_haptics_4ch(
    pcm_stereo_bytes: bytes,
    *,
    gain: float = 1.65,
    alpha: float = 0.045,
) -> bytes:
    """Convierte audio PCM 16-bit estéreo en PCM 16-bit de 4 canales para el DualSense USB:
      - Canal 0 (Headphone L) = 0
      - Canal 1 (Headphone R) = 0
      - Canal 2 (VCM Haptic L) = señal táctil filtrada (graves/impactos)
      - Canal 3 (VCM Haptic R) = señal táctil filtrada (graves/impactos)
    """
    if not pcm_stereo_bytes or len(pcm_stereo_bytes) < 4:
        return b""
    usable = (len(pcm_stereo_bytes) // 4) * 4
    src = array.array("h")
    src.frombytes(pcm_stereo_bytes[:usable])
    frames = len(src) // 2
    out = array.array("h", [0] * (frames * 4))

    lp_l = 0.0
    lp_r = 0.0
    for i in range(frames):
        raw_l = float(src[i * 2])
        raw_r = float(src[i * 2 + 1])
        lp_l += alpha * (raw_l - lp_l)
        lp_r += alpha * (raw_r - lp_r)
        hl = max(-32767, min(32767, int(round(lp_l * gain))))
        hr = max(-32767, min(32767, int(round(lp_r * gain))))
        base = i * 4
        out[base + 2] = hl
        out[base + 3] = hr
    return out.tobytes()


def find_dualsense_4ch_audio_device(pyaudio_instance) -> Optional[dict]:
    """Busca el endpoint de salida WASAPI de 4 canales del DualSense conectado por USB."""
    try:
        wasapi_info = pyaudio_instance.get_host_api_info_by_type(pyaudio_instance.paWASAPI)
        host_idx = wasapi_info["index"]
        for idx in range(pyaudio_instance.get_device_count()):
            info = pyaudio_instance.get_device_info_by_index(idx)
            if info.get("hostApi") != host_idx:
                continue
            if int(info.get("maxOutputChannels", 0)) >= 4 and not info.get("isLoopbackDevice", False):
                name = str(info.get("name", ""))
                low = name.lower()
                if "wireless controller" in low or "dualsense" in low:
                    return info
    except Exception:
        return None
    return None


class AudioToRumbleService(QObject):
    status_changed = Signal(bool, str)  # running, status_text
    _motors_ready = Signal(int, int)

    def __init__(
        self,
        controller_service,
        haptics_getter: Callable[[], HapticSettings],
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._controller_service = controller_service
        self._haptics_getter = haptics_getter
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_status = "Inactivo"
        self._active_mode_label = "Inactivo"
        self._motors_ready.connect(self._apply_motors_main_thread)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status_text(self) -> str:
        return self._last_status

    def start(self) -> bool:
        if self._running:
            return True
        if sys.platform != "win32":
            self._last_status = "Audio To Rumble / HD Haptics (WASAPI) solo está disponible en Windows."
            self.status_changed.emit(False, self._last_status)
            return False
        try:
            import pyaudiowpatch  # type: ignore  # noqa: F401
        except Exception:
            self._last_status = (
                "Falta 'pyaudiowpatch' para capturar audio WASAPI. "
                "Ejecuta ejecutar.bat o: pip install pyaudiowpatch"
            )
            self.status_changed.emit(False, self._last_status)
            return False

        self._stop_event.clear()
        self._running = True
        self._last_status = "Iniciando captura WASAPI Loopback..."
        self.status_changed.emit(True, self._last_status)
        self._thread = threading.Thread(target=self._capture_loop, name="Dualless-AudioHaptics", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        was_running = self._running
        self._stop_event.set()
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        if was_running:
            self._motors_ready.emit(0, 0)
            self._last_status = "Detenido"
            self.status_changed.emit(False, self._last_status)

    def _capture_loop(self) -> None:
        try:
            import pyaudiowpatch as pyaudio  # type: ignore

            with pyaudio.PyAudio() as p:
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                if not default_speakers.get("isLoopbackDevice", False):
                    for loopback in p.get_loopback_device_info_generator():
                        if default_speakers["name"] in loopback["name"]:
                            default_speakers = loopback
                            break

                ds_4ch = find_dualsense_4ch_audio_device(p)
                rate = int(ds_4ch["defaultSampleRate"]) if ds_4ch else int(default_speakers["defaultSampleRate"])
                in_channels = max(1, min(2, int(default_speakers["maxInputChannels"])))
                chunk = max(512, rate // 40)

                in_stream = p.open(
                    format=pyaudio.paInt16,
                    channels=in_channels,
                    rate=rate,
                    frames_per_buffer=chunk,
                    input=True,
                    input_device_index=default_speakers["index"],
                )

                out_stream = None
                if ds_4ch is not None:
                    try:
                        out_stream = p.open(
                            format=pyaudio.paInt16,
                            channels=4,
                            rate=rate,
                            frames_per_buffer=chunk,
                            output=True,
                            output_device_index=ds_4ch["index"],
                        )
                    except Exception:
                        out_stream = None

                current_announced = ""
                try:
                    while not self._stop_event.is_set():
                        data = in_stream.read(chunk, exception_on_overflow=False)
                        cfg = self._haptics_getter()
                        if not cfg.enabled:
                            continue

                        scale = max(0.0, min(1.0, cfg.intensity / 8.0))
                        # Si Haptic Feedback Mode está seleccionado y tenemos salida USB de 4 canales
                        if cfg.use_haptics and out_stream is not None:
                            if current_announced != "usb_4ch":
                                current_announced = "usb_4ch"
                                self._last_status = (
                                    f"HD USB 4-Canales activo (Canales 3–4 VCM en '{ds_4ch['name']}')"
                                )
                                self.status_changed.emit(True, self._last_status)
                            # Asegurar estéreo antes de expandir a 4 canales
                            stereo = data if in_channels == 2 else self._mono_to_stereo(data)
                            haptic_4ch = process_pcm16_to_usb_haptics_4ch(stereo, gain=1.75 * scale)
                            if haptic_4ch:
                                out_stream.write(haptic_4ch)
                        else:
                            if current_announced != "hid_rumble":
                                current_announced = "hid_rumble"
                                self._last_status = "Rumble HID en vivo (WASAPI Loopback → Motores L/R)"
                                self.status_changed.emit(True, self._last_status)
                            l_mot, r_mot = compute_rumble_from_pcm16(data, gain=2.6 * scale)
                            self._motors_ready.emit(l_mot, r_mot)
                finally:
                    in_stream.stop_stream()
                    in_stream.close()
                    if out_stream is not None:
                        out_stream.stop_stream()
                        out_stream.close()
        except Exception as exc:
            self._running = False
            self._last_status = f"Error de captura WASAPI: {exc}"
            self.status_changed.emit(False, self._last_status)

    @staticmethod
    def _mono_to_stereo(mono_bytes: bytes) -> bytes:
        usable = (len(mono_bytes) // 2) * 2
        src = array.array("h")
        src.frombytes(mono_bytes[:usable])
        dst = array.array("h", [0] * (len(src) * 2))
        for i, s in enumerate(src):
            dst[i * 2] = s
            dst[i * 2 + 1] = s
        return dst.tobytes()

    def _apply_motors_main_thread(self, left: int, right: int) -> None:
        cfg = self._haptics_getter()
        if not cfg.enabled:
            return
        self._controller_service.apply_haptics(
            HapticSettings(
                left_motor=left,
                right_motor=right,
                use_haptics=False,
                enabled=cfg.enabled,
                intensity=cfg.intensity,
                enhanced_rumble=cfg.enhanced_rumble,
                audio_to_rumble=True,
                preset_name=cfg.preset_name,
            )
        )
