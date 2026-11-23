"""Motor de efectos dinámicos para la barra LED del DualSense (v0.4.4).

Soporta:
- Static Color
- Multi Color (ciclo RGB suave)
- Breathing (respiración 0 -> brillo configurado, con opción Random Color)
- Strobing (parpadeo rítmico, con opción Random Color)
- Battery (verde / amarillo / rojo según nivel de batería)
- Battery Low Flashing (alerta parpadeante roja cuando la batería <= 20%)
"""

from __future__ import annotations

import colorsys
import math
import random
import time
from dataclasses import replace
from typing import Optional, Tuple

from dualcontrol.models import LightingSettings


def _scale_rgb(r: int, g: int, b: int, factor: float) -> Tuple[int, int, int]:
    f = max(0.0, min(1.0, factor))
    return (
        max(0, min(255, int(round(r * f)))),
        max(0, min(255, int(round(g * f)))),
        max(0, min(255, int(round(b * f)))),
    )


def random_vivid_rgb(rng: Optional[random.Random] = None) -> Tuple[int, int, int]:
    gen = rng or random
    h = gen.random()
    r, g, b = colorsys.hsv_to_rgb(h, 0.9, 1.0)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def compute_effect_rgb(
    settings: LightingSettings,
    elapsed_s: float,
    battery_level: int = 100,
    active_rgb: Optional[Tuple[int, int, int]] = None,
) -> Tuple[int, int, int]:
    """Calcula el color (R, G, B) instantáneo para el efecto y tiempo dados."""
    cfg = settings.clamp()
    max_bright = cfg.lightbar_brightness / 100.0
    base_r, base_g, base_b = active_rgb if active_rgb is not None else (cfg.red, cfg.green, cfg.blue)

    # Prioridad: alerta de batería baja parpadeante
    if cfg.battery_low_flashing and 0 < battery_level <= 20:
        on = (int(elapsed_s * 3.0) % 2) == 0
        return _scale_rgb(255, 24, 24, max_bright if on else 0.0)

    mode = cfg.effect_mode
    if mode == "static":
        return _scale_rgb(base_r, base_g, base_b, max_bright)

    if mode == "battery":
        if battery_level >= 70:
            return _scale_rgb(34, 197, 94, max_bright)
        if battery_level >= 30:
            return _scale_rgb(245, 158, 11, max_bright)
        return _scale_rgb(239, 68, 68, max_bright)

    # Velocidad normalizada (1..100 -> ~0.12 Hz .. 2.5 Hz)
    freq_hz = 0.10 + (cfg.effect_speed / 100.0) * 1.90

    if mode == "multi_color":
        hue = (elapsed_s * (freq_hz * 0.25)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return _scale_rgb(int(r * 255), int(g * 255), int(b * 255), max_bright)

    if mode == "breathing":
        # Onda suave 0..1..0
        wave = 0.5 * (1.0 - math.cos(2.0 * math.pi * freq_hz * elapsed_s))
        return _scale_rgb(base_r, base_g, base_b, max_bright * wave)

    if mode == "strobing":
        phase = (elapsed_s * freq_hz * 2.0) % 1.0
        on = phase < 0.5
        return _scale_rgb(base_r, base_g, base_b, max_bright if on else 0.0)

    return _scale_rgb(base_r, base_g, base_b, max_bright)


try:
    from PySide6.QtCore import QObject, QTimer, Signal

    class LightingEffectController(QObject):
        """Aplica efectos LED en tiempo real al DualSense y emite el color vivo para la UI."""

        live_color_changed = Signal(int, int, int)

        TICK_MS = 40  # 25 Hz: suave para Breathing/Rainbow sin saturar el bus USB

        def __init__(self, controller_service, parent: Optional[QObject] = None) -> None:
            super().__init__(parent)
            self._controller_service = controller_service
            self._settings = LightingSettings()
            self._battery_level = 100
            self._start_time = time.monotonic()
            self._active_rgb = (self._settings.red, self._settings.green, self._settings.blue)
            self._last_cycle_idx = -1
            self._last_sent_rgb: Optional[Tuple[int, int, int]] = None

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)

            self._controller_service.state_changed.connect(self._on_state_changed)

        @property
        def settings(self) -> LightingSettings:
            return self._settings

        def _on_state_changed(self, state) -> None:
            self._battery_level = int(getattr(state, "battery_level", 100))

        def set_settings(self, settings: LightingSettings) -> None:
            self._settings = replace(settings).clamp()
            self._active_rgb = (self._settings.red, self._settings.green, self._settings.blue)
            self._start_time = time.monotonic()
            self._last_cycle_idx = -1
            self._last_sent_rgb = None

            needs_timer = (
                self._settings.effect_mode in ("multi_color", "breathing", "strobing", "battery")
                or self._settings.battery_low_flashing
            )
            if needs_timer:
                if not self._timer.isActive():
                    self._timer.start(self.TICK_MS)
            else:
                self._timer.stop()

            self._tick(force=True)

        def _tick(self, *, force: bool = False) -> None:
            elapsed = time.monotonic() - self._start_time
            cfg = self._settings

            if cfg.random_color and cfg.effect_mode in ("breathing", "strobing"):
                freq_hz = 0.10 + (cfg.effect_speed / 100.0) * 1.90
                cycle_idx = int(elapsed * freq_hz)
                if cycle_idx != self._last_cycle_idx:
                    self._last_cycle_idx = cycle_idx
                    if cycle_idx > 0:
                        self._active_rgb = random_vivid_rgb()

            r, g, b = compute_effect_rgb(
                cfg,
                elapsed,
                battery_level=self._battery_level,
                active_rgb=self._active_rgb,
            )
            self.live_color_changed.emit(r, g, b)

            if force or self._last_sent_rgb != (r, g, b):
                self._last_sent_rgb = (r, g, b)
                out = replace(cfg, red=r, green=g, blue=b)
                self._controller_service.apply_lighting(out)

        def stop(self) -> None:
            self._timer.stop()

except ImportError:
    LightingEffectController = None  # type: ignore
