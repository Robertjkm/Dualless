"""Traductor de entradas Sony DualSense / DualSense Edge -> mando Xbox 360 (XInput).

Soporta reasignación de botones (incluyendo Paddles traseros y FN del DualSense Edge),
zonas muertas, curvas de respuesta, calibración anti-drift, Hair Trigger ajustable,
Rapid Trigger (liberación rápida), Modo Turbo (Rapid Fire) y Gyro-to-Stick Pro
(selector de botón de activación, eje Yaw/Roll, zona muerta y suavizado EMA).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from dualcontrol.models import ControllerState, MappingSettings

DEFAULT_BUTTON_MAP: Dict[str, str] = {
    "cross": "a",
    "circle": "b",
    "square": "x",
    "triangle": "y",
    "l1": "lb",
    "r1": "rb",
    "create": "back",
    "options": "start",
    "ps": "guide",
    "l3": "left_thumb",
    "r3": "right_thumb",
    "paddle_left": "none",
    "paddle_right": "none",
    "fn_left": "none",
    "fn_right": "none",
}

PHYSICAL_BUTTON_LABELS: Tuple[Tuple[str, str], ...] = (
    ("cross", "✕  Cruz (Cross)"),
    ("circle", "○  Círculo (Circle)"),
    ("square", "□  Cuadrado (Square)"),
    ("triangle", "△  Triángulo (Triangle)"),
    ("l1", "L1"),
    ("r1", "R1"),
    ("l3", "L3 (clic stick izq.)"),
    ("r3", "R3 (clic stick der.)"),
    ("create", "Create / Share"),
    ("options", "Options"),
    ("ps", "Botón PS"),
    ("paddle_left", "Edge — Paddle Izquierdo (LB trasero)"),
    ("paddle_right", "Edge — Paddle Derecho (RB trasero)"),
    ("fn_left", "Edge — Botón FN Izquierdo"),
    ("fn_right", "Edge — Botón FN Derecho"),
)

XINPUT_TARGET_LABELS: Tuple[Tuple[str, str], ...] = (
    ("a", "Xbox A"),
    ("b", "Xbox B"),
    ("x", "Xbox X"),
    ("y", "Xbox Y"),
    ("lb", "Xbox LB"),
    ("rb", "Xbox RB"),
    ("left_thumb", "Xbox LS (clic izq.)"),
    ("right_thumb", "Xbox RS (clic der.)"),
    ("back", "Xbox Back / View"),
    ("start", "Xbox Start / Menu"),
    ("guide", "Xbox Guide"),
    ("none", "Desactivado"),
)

GYRO_ACTIVATION_LABELS: Tuple[Tuple[str, str], ...] = (
    ("always", "Siempre activo"),
    ("l2", "Al mantener L2 (Apuntar)"),
    ("r2", "Al mantener R2"),
    ("l1", "Al mantener L1"),
    ("r1", "Al mantener R1"),
    ("touchpad", "Al tocar el Touchpad"),
    ("paddle_left", "Al mantener Edge Paddle Izquierdo"),
    ("paddle_right", "Al mantener Edge Paddle Derecho"),
)

GYRO_AXIS_LABELS: Tuple[Tuple[str, str], ...] = (
    ("yaw", "Yaw (girar mando izquierda/derecha)"),
    ("roll", "Roll (inclinar como volante)"),
)


def is_gyro_activation_active(state: ControllerState, activation: str, fallback_only_l2: bool = True) -> bool:
    """Evalúa si el botón/condición de activación del giroscopio está activo."""
    mode = (activation or "").strip().lower()
    if not mode:
        mode = "l2" if fallback_only_l2 else "always"
    if mode == "always":
        return True
    if mode == "l2":
        return int(state.l2_value) >= 60 or bool(state.l2_button)
    if mode == "r2":
        return int(state.r2_value) >= 60 or bool(state.r2_button)
    if mode == "l1":
        return bool(state.l1)
    if mode == "r1":
        return bool(state.r1)
    if mode == "touchpad":
        return bool(state.touch1.active or state.touchpad_button)
    if mode == "paddle_left":
        return bool(state.paddle_left)
    if mode == "paddle_right":
        return bool(state.paddle_right)
    return True


def _apply_curve(mag: float, curve: str) -> float:
    if curve == "precision":
        return mag ** 1.8
    if curve == "fast":
        return mag ** 0.65
    return mag


def _process_axis(
    value: int,
    *,
    deadzone: float = 0.0,
    sensitivity: float = 1.0,
    invert: bool = False,
    curve: str = "linear",
    center_offset: int = 0,
) -> int:
    v = max(0, min(255, int(value) + int(center_offset)))
    if v == 128:
        return 0

    norm = (v - 128) / 128.0 if v < 128 else (v - 128) / 127.0

    dz = max(0.0, min(0.5, float(deadzone)))
    mag = abs(norm)
    if mag <= dz:
        return 0
    sign = -1.0 if norm < 0 else 1.0
    if dz > 0.0:
        mag = (mag - dz) / (1.0 - dz)

    mag = _apply_curve(mag, curve)
    sens = max(0.25, min(2.0, float(sensitivity)))
    norm = sign * min(1.0, mag * sens)

    if invert:
        norm = -norm

    if norm < 0:
        return max(-32768, int(round(norm * 32768)))
    return min(32767, int(round(norm * 32767)))


def _process_trigger(
    value: int,
    *,
    deadzone: float = 0.0,
    hair_trigger: bool = False,
    hair_threshold: float = 0.05,
) -> int:
    """Procesa un gatillo analógico (0..255) aplicando zona muerta y Hair Trigger ajustable."""
    v = max(0, min(255, int(value)))
    dz_raw = int(round(max(0.0, min(0.5, float(deadzone))) * 255.0))
    ht_raw = max(5, int(round(max(0.02, min(0.35, float(hair_threshold))) * 255.0)))
    threshold = max(dz_raw, ht_raw) if hair_trigger else dz_raw
    if v <= threshold:
        return 0
    if hair_trigger:
        return 255
    if dz_raw <= 0:
        return v
    scaled = (v - dz_raw) / max(1.0, 255.0 - dz_raw)
    return max(0, min(255, int(round(scaled * 255.0))))


@dataclass
class RapidTriggerChannel:
    """Rastreador de Rapid Trigger por gatillo: activa al presionar sobre el umbral y
    libera de inmediato al retroceder `release_delta` sin volver a cero."""

    active: bool = False
    peak: int = 0
    trough: int = 0

    def update(self, value: int, *, base_threshold: int, release_delta: int) -> int:
        v = max(0, min(255, int(value)))
        delta = max(6, int(release_delta))
        thr = max(5, int(base_threshold))

        if not self.active:
            if v < self.trough:
                self.trough = v
            if v >= thr and (v - self.trough) >= delta or (self.trough == 0 and v >= thr):
                self.active = True
                self.peak = v
                return 255
            return 0

        # Activo: actualiza el pico máximo alcanzado
        if v > self.peak:
            self.peak = v
        # Si soltamos por debajo del umbral base o retrocedemos `delta` desde el pico -> libera al instante
        if v < thr or (self.peak - v) >= delta:
            self.active = False
            self.trough = v
            return 0
        return 255


@dataclass
class MapperRuntimeState:
    """Estado temporal opcional para suavizado EMA del Gyro y Rapid Trigger en vivo."""

    ema_gyro_x: float = 0.0
    ema_gyro_h: float = 0.0
    rapid_l2: RapidTriggerChannel = None  # type: ignore[assignment]
    rapid_r2: RapidTriggerChannel = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rapid_l2 is None:
            self.rapid_l2 = RapidTriggerChannel()
        if self.rapid_r2 is None:
            self.rapid_r2 = RapidTriggerChannel()


@dataclass
class XInputSnapshot:
    """Estado equivalente en formato Xbox 360 (XInput)."""

    a: bool = False
    b: bool = False
    x: bool = False
    y: bool = False
    lb: bool = False
    rb: bool = False
    back: bool = False
    start: bool = False
    guide: bool = False
    left_thumb: bool = False
    right_thumb: bool = False
    dpad_up: bool = False
    dpad_down: bool = False
    dpad_left: bool = False
    dpad_right: bool = False

    left_trigger: int = 0
    right_trigger: int = 0

    left_x: int = 0
    left_y: int = 0
    right_x: int = 0
    right_y: int = 0

    def pressed_labels(self) -> List[str]:
        names = [
            ("A", self.a), ("B", self.b), ("X", self.x), ("Y", self.y),
            ("LB", self.lb), ("RB", self.rb), ("Back", self.back), ("Start", self.start),
            ("Guide", self.guide), ("LS", self.left_thumb), ("RS", self.right_thumb),
            ("Up", self.dpad_up), ("Down", self.dpad_down),
            ("Left", self.dpad_left), ("Right", self.dpad_right),
        ]
        return [label for label, active in names if active]


def map_dualsense_to_xinput(
    state: ControllerState,
    mapping: Optional[MappingSettings] = None,
    *,
    now_ts: Optional[float] = None,
    runtime_state: Optional[MapperRuntimeState] = None,
) -> XInputSnapshot:
    """Convierte un snapshot de DualSense / DualSense Edge en XInput aplicando MappingSettings."""
    cfg = mapping.clamp() if mapping is not None else MappingSettings(deadzone_left=0.0, deadzone_right=0.0)
    remap = cfg.remap or {}
    turbo_set = set(cfg.turbo_buttons or [])
    ts = time.monotonic() if now_ts is None else float(now_ts)
    turbo_pulse_high = (int(ts * cfg.turbo_rate_hz * 2.0) % 2) == 0

    out_buttons: Dict[str, bool] = {
        "a": False,
        "b": False,
        "x": False,
        "y": False,
        "lb": False,
        "rb": False,
        "back": False,
        "start": False,
        "guide": False,
        "left_thumb": False,
        "right_thumb": False,
    }

    for phys_key, default_target in DEFAULT_BUTTON_MAP.items():
        if bool(getattr(state, phys_key, False)):
            if phys_key in turbo_set and not turbo_pulse_high:
                continue
            target = str(remap.get(phys_key, default_target)).strip().lower()
            if target in out_buttons:
                out_buttons[target] = True

    dpad = (state.dpad or "NONE").upper()

    right_x = _process_axis(
        state.right_stick.x,
        deadzone=cfg.deadzone_right,
        sensitivity=cfg.sensitivity_right,
        invert=cfg.invert_right_x,
        curve=cfg.curve_right,
        center_offset=cfg.offset_right_x,
    )
    right_y = _process_axis(
        state.right_stick.y,
        deadzone=cfg.deadzone_right,
        sensitivity=cfg.sensitivity_right,
        invert=not cfg.invert_right_y,
        curve=cfg.curve_right,
        center_offset=cfg.offset_right_y,
    )

    # Gyro-to-Stick Pro: botón de activación, eje Yaw/Roll, deadzone configurable y suavizado EMA
    if cfg.gyro_to_stick_enabled:
        act_mode = cfg.gyro_activation
        # Compatibilidad con perfiles v1.2 donde solo se usaba gyro_to_stick_only_when_l2=False
        if act_mode == "l2" and not cfg.gyro_to_stick_only_when_l2:
            act_mode = "always"
        gyro_active = is_gyro_activation_active(state, act_mode, fallback_only_l2=cfg.gyro_to_stick_only_when_l2)
        if gyro_active:
            raw_h = float(state.gyro_z if cfg.gyro_horizontal_axis == "roll" else state.gyro_y)
            raw_x = float(state.gyro_x)
            dz = float(cfg.gyro_deadzone)
            gh = raw_h if abs(raw_h) > dz else 0.0
            gx = raw_x if abs(raw_x) > dz else 0.0

            if runtime_state is not None and cfg.gyro_smoothing > 0.0:
                alpha = 1.0 - cfg.gyro_smoothing
                runtime_state.ema_gyro_h += alpha * (gh - runtime_state.ema_gyro_h)
                runtime_state.ema_gyro_x += alpha * (gx - runtime_state.ema_gyro_x)
                gh = runtime_state.ema_gyro_h
                gx = runtime_state.ema_gyro_x

            scale = 9.0 * cfg.gyro_to_stick_sensitivity
            dx = -gh * scale
            dy = gx * scale
            if cfg.gyro_to_stick_invert_x:
                dx = -dx
            if cfg.gyro_to_stick_invert_y:
                dy = -dy
            right_x = max(-32768, min(32767, int(round(right_x + dx))))
            right_y = max(-32768, min(32767, int(round(right_y + dy))))
        elif runtime_state is not None:
            runtime_state.ema_gyro_h = 0.0
            runtime_state.ema_gyro_x = 0.0

    # Gatillos: Rapid Trigger o Hair Trigger / Deadzone
    ht_raw = max(5, int(round(cfg.hair_trigger_threshold * 255.0)))
    rt_delta = max(6, int(round(cfg.rapid_trigger_release * 255.0)))

    if cfg.rapid_trigger_l2 and runtime_state is not None:
        l2_out = runtime_state.rapid_l2.update(
            state.l2_value,
            base_threshold=max(ht_raw, int(round(cfg.trigger_deadzone_l2 * 255.0))),
            release_delta=rt_delta,
        )
    else:
        l2_out = _process_trigger(
            state.l2_value,
            deadzone=cfg.trigger_deadzone_l2,
            hair_trigger=cfg.hair_trigger_l2 or cfg.rapid_trigger_l2,
            hair_threshold=cfg.hair_trigger_threshold,
        )

    if cfg.rapid_trigger_r2 and runtime_state is not None:
        r2_out = runtime_state.rapid_r2.update(
            state.r2_value,
            base_threshold=max(ht_raw, int(round(cfg.trigger_deadzone_r2 * 255.0))),
            release_delta=rt_delta,
        )
    else:
        r2_out = _process_trigger(
            state.r2_value,
            deadzone=cfg.trigger_deadzone_r2,
            hair_trigger=cfg.hair_trigger_r2 or cfg.rapid_trigger_r2,
            hair_threshold=cfg.hair_trigger_threshold,
        )

    return XInputSnapshot(
        a=out_buttons["a"],
        b=out_buttons["b"],
        x=out_buttons["x"],
        y=out_buttons["y"],
        lb=out_buttons["lb"],
        rb=out_buttons["rb"],
        back=out_buttons["back"],
        start=out_buttons["start"],
        guide=out_buttons["guide"],
        left_thumb=out_buttons["left_thumb"],
        right_thumb=out_buttons["right_thumb"],
        dpad_up=dpad in ("N", "NE", "NW"),
        dpad_down=dpad in ("S", "SE", "SW"),
        dpad_left=dpad in ("W", "NW", "SW"),
        dpad_right=dpad in ("E", "NE", "SE"),
        left_trigger=l2_out,
        right_trigger=r2_out,
        left_x=_process_axis(
            state.left_stick.x,
            deadzone=cfg.deadzone_left,
            sensitivity=cfg.sensitivity_left,
            invert=cfg.invert_left_x,
            curve=cfg.curve_left,
            center_offset=cfg.offset_left_x,
        ),
        left_y=_process_axis(
            state.left_stick.y,
            deadzone=cfg.deadzone_left,
            sensitivity=cfg.sensitivity_left,
            invert=not cfg.invert_left_y,
            curve=cfg.curve_left,
            center_offset=cfg.offset_left_y,
        ),
        right_x=right_x,
        right_y=right_y,
    )
