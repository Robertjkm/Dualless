"""Modelos de datos de Dualless.

Estas clases son puro estado (dataclasses) sin ninguna dependencia de HID ni de la
interfaz gráfica, para que puedan probarse de forma aislada y reutilizarse tanto en
el backend simulado como en el real.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TriggerMode(str, Enum):
    """Modos de gatillo adaptativo a nivel de protocolo (valores reales del firmware).

    Estos nombres y valores son los que expone la biblioteca ``pydualsense`` (MIT) en
    su ``enums.TriggerModes``, verificados leyendo su código fuente instalado en este
    mismo entorno (no inventados): Off=0x0, Rigid=0x1, Pulse=0x2, y las combinaciones
    con las zonas 0x04/0x20 que activan tramos adicionales. ``CALIBRATION`` (0xFC) es
    un modo especial de fábrica y no se expone en la interfaz de usuario.

    Dualless además ofrece "presets" con nombres de la sección 5 de las
    instrucciones (Weapon, Bow, Galloping, Vibration...) que son combinaciones de
    estos modos base + valores de ``forces`` razonables según la documentación
    comunitaria citada en ``dualcontrol/protocol.py``. Esos presets son aproximaciones
    razonables, no una traducción oficial confirmada por Sony — se documenta así en
    la interfaz para no afirmar más precisión de la que existe.
    """

    OFF = "off"
    RIGID = "rigid"            # Resistencia continua desde un punto.
    PULSE = "pulse"            # Tope/resistencia en una zona concreta.
    RIGID_A = "rigid_a"
    RIGID_B = "rigid_b"
    RIGID_AB = "rigid_ab"
    PULSE_A = "pulse_a"
    PULSE_B = "pulse_b"
    PULSE_AB = "pulse_ab"


class ConnectionState(str, Enum):
    """Estados de diagnóstico — ver sección 12 de las instrucciones del proyecto.

    Se distingue explícitamente "detectado" de "controlable": nunca se debe
    confundir ver el dispositivo con poder escribirle datos.
    """

    NOT_DETECTED = "no_detectado"
    DETECTED = "detectado"
    OPENED = "abierto"
    INPUT_OK = "entrada_funcional"
    OUTPUT_OK = "salida_funcional"
    ERROR = "error"


@dataclass
class StickState:
    x: int = 128  # 0-255, 128 = centro
    y: int = 128


@dataclass
class TouchPoint:
    active: bool = False
    finger_id: int = 0
    x: int = 0
    y: int = 0


@dataclass
class ControllerState:
    """Snapshot de todas las entradas del mando en un instante dado."""

    timestamp: float = field(default_factory=time.time)

    left_stick: StickState = field(default_factory=StickState)
    right_stick: StickState = field(default_factory=StickState)

    l2_value: int = 0  # 0-255 analógico
    r2_value: int = 0

    dpad: str = "NONE"

    square: bool = False
    cross: bool = False
    circle: bool = False
    triangle: bool = False

    l1: bool = False
    r1: bool = False
    l2_button: bool = False
    r2_button: bool = False
    l3: bool = False
    r3: bool = False

    create: bool = False
    options: bool = False
    ps: bool = False
    touchpad_button: bool = False
    mute: bool = False
    # Botones exclusivos de DualSense Edge (PID 0x0DF2)
    fn_left: bool = False
    fn_right: bool = False
    paddle_left: bool = False
    paddle_right: bool = False

    touch1: TouchPoint = field(default_factory=TouchPoint)
    touch2: TouchPoint = field(default_factory=TouchPoint)

    gyro_x: int = 0
    gyro_y: int = 0
    gyro_z: int = 0
    accel_x: int = 0
    accel_y: int = 0
    accel_z: int = 0

    battery_level: int = 0  # 0-100
    battery_charging: bool = False
    headphone_connected: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class TriggerSettings:
    """Configuración de un gatillo (L2 o R2) tal como la pide la sección 5.

    ``forces`` son los 7 bytes de parámetro crudos del informe HID (0-255 cada uno).
    Por convención documentada por la comunidad, ``forces[0]`` suele representar el
    punto de inicio del recorrido (0-9) y ``forces[1]`` la fuerza en ese punto; el
    resto de índices se usan según el modo para tramos/curvas adicionales. El editor
    visual expone tanto estos 7 parámetros crudos como presets de alto nivel.
    """

    enabled: bool = False
    mode: TriggerMode = TriggerMode.OFF
    forces: list = field(default_factory=lambda: [0, 0, 0, 0, 0, 0, 0])
    preset_name: str = "custom"  # nombre del preset aplicado (o "custom" si se editó a mano)

    def clamp(self) -> "TriggerSettings":
        self.forces = [max(0, min(255, int(v))) for v in self.forces[:7]]
        while len(self.forces) < 7:
            self.forces.append(0)
        return self

    @property
    def start_position(self) -> int:
        """Lectura cómoda de forces[0], acotada a 0-9 (10 zonas del recorrido físico)."""
        return max(0, min(9, self.forces[0]))

    @property
    def force_at_start(self) -> int:
        return self.forces[1]


@dataclass
class HapticSettings:
    left_motor: int = 0   # 0-255
    right_motor: int = 0  # 0-255
    use_haptics: bool = True  # True = Haptic Feedback Mode; False = Rumble Mode
    enabled: bool = True
    intensity: int = 8  # 0..8 intensidad global
    enhanced_rumble: bool = True
    audio_to_rumble: bool = False
    preset_name: str = "Default Preset"

    def clamp(self) -> "HapticSettings":
        self.left_motor = max(0, min(255, int(self.left_motor)))
        self.right_motor = max(0, min(255, int(self.right_motor)))
        self.intensity = max(0, min(8, int(self.intensity)))
        return self

    def effective_motors(self) -> tuple[int, int]:
        """Devuelve (left, right) escalados por enabled e intensity (0..8)."""
        if not self.enabled or self.intensity <= 0:
            return 0, 0
        scale = self.intensity / 8.0
        return (
            max(0, min(255, int(round(self.left_motor * scale)))),
            max(0, min(255, int(round(self.right_motor * scale)))),
        )


@dataclass
class LightingSettings:
    red: int = 0
    green: int = 120
    blue: int = 215
    brightness: int = 2            # 0=alto 1=medio 2=bajo (LEDs de jugador)
    player_led: int = 1            # 1-5 número de "puntos" encendidos, 0 = apagado
    player_led_fade: bool = True
    effect_mode: str = "static"    # static | multi_color | breathing | strobing | battery
    lightbar_brightness: int = 90  # 0..100 %
    effect_speed: int = 30         # 1..100
    random_color: bool = False
    battery_low_flashing: bool = False
    preset_name: str = "Default Preset"

    def clamp(self) -> "LightingSettings":
        self.red = max(0, min(255, int(self.red)))
        self.green = max(0, min(255, int(self.green)))
        self.blue = max(0, min(255, int(self.blue)))
        self.brightness = max(0, min(2, int(self.brightness)))
        self.player_led = max(0, min(5, int(self.player_led)))
        self.lightbar_brightness = max(0, min(100, int(self.lightbar_brightness)))
        self.effect_speed = max(1, min(100, int(self.effect_speed)))
        if self.effect_mode not in ("static", "multi_color", "breathing", "strobing", "battery"):
            self.effect_mode = "static"
        return self




@dataclass
class AudioSettings:
    """Control del altavoz integrado, volumen de auriculares/micrófono y botón Mute."""

    speaker_volume: int = 80        # 0..100 %
    headphone_volume: int = 100     # 0..100 %
    mic_volume: int = 80            # 0..100 %
    speaker_enabled: bool = True
    mic_muted: bool = False
    sync_windows_mute: bool = True

    def clamp(self) -> "AudioSettings":
        self.speaker_volume = max(0, min(100, int(self.speaker_volume)))
        self.headphone_volume = max(0, min(100, int(self.headphone_volume)))
        self.mic_volume = max(0, min(100, int(self.mic_volume)))
        self.speaker_enabled = bool(self.speaker_enabled)
        self.mic_muted = bool(self.mic_muted)
        self.sync_windows_mute = bool(self.sync_windows_mute)
        return self


@dataclass
class MappingSettings:
    """Configuración de reasignación de botones y sticks (sección 9).

    Se aplica en tiempo real sobre la salida hacia el mando virtual XInput
    sin alterar las lecturas físicas crudas del monitor de entradas.
    """

    remap: dict = field(default_factory=dict)
    deadzone_left: float = 0.05
    deadzone_right: float = 0.05
    sensitivity_left: float = 1.0
    sensitivity_right: float = 1.0
    invert_left_x: bool = False
    invert_left_y: bool = False
    invert_right_x: bool = False
    invert_right_y: bool = False
    curve_left: str = "linear"    # "linear" | "precision" | "fast"
    curve_right: str = "linear"   # "linear" | "precision" | "fast"
    offset_left_x: int = 0        # calibración anti-drift (-40..40)
    offset_left_y: int = 0
    offset_right_x: int = 0
    offset_right_y: int = 0
    # Nivel 2 / v1.4.0 — Gyro Pro (Gyro-to-Stick: activación, eje Yaw/Roll, deadzone y suavizado)
    gyro_to_stick_enabled: bool = False
    gyro_to_stick_only_when_l2: bool = True
    gyro_activation: str = "l2"             # "always" | "l2" | "r2" | "l1" | "r1" | "touchpad" | "paddle_left" | "paddle_right"
    gyro_horizontal_axis: str = "yaw"       # "yaw" (gyro_y) | "roll" (gyro_z)
    gyro_deadzone: int = 45                 # 0..200 unidades crudas
    gyro_smoothing: float = 0.35            # 0.0..0.85 filtro EMA
    gyro_to_stick_sensitivity: float = 1.0  # 0.25..4.0
    gyro_to_stick_invert_x: bool = False
    gyro_to_stick_invert_y: bool = False
    # Nivel 2 / v1.4.0 — Hair Trigger Pro, Rapid Trigger y Dual Stage ajustable
    trigger_deadzone_l2: float = 0.0        # 0.0..0.5
    trigger_deadzone_r2: float = 0.0        # 0.0..0.5
    hair_trigger_l2: bool = False
    hair_trigger_r2: bool = False
    hair_trigger_threshold: float = 0.05    # 0.02..0.35 (2%..35% del recorrido)
    rapid_trigger_l2: bool = False
    rapid_trigger_r2: bool = False
    rapid_trigger_release: float = 0.08     # 0.03..0.25 margen de liberación/re-disparo
    dual_stage_threshold: float = 0.92      # 0.70..0.98
    dual_stage_l2_action: str = "none"
    dual_stage_r2_action: str = "none"
    # Nivel 2 — Turbo / Rapid Fire y Mapeo libre a Teclado/Ratón
    turbo_buttons: list = field(default_factory=list)
    turbo_rate_hz: float = 12.0             # 2.0..25.0 Hz
    key_bindings: dict = field(default_factory=dict)

    def clamp(self) -> "MappingSettings":
        self.deadzone_left = max(0.0, min(0.5, float(self.deadzone_left)))
        self.deadzone_right = max(0.0, min(0.5, float(self.deadzone_right)))
        self.sensitivity_left = max(0.25, min(2.0, float(self.sensitivity_left)))
        self.sensitivity_right = max(0.25, min(2.0, float(self.sensitivity_right)))
        if self.curve_left not in ("linear", "precision", "fast"):
            self.curve_left = "linear"
        if self.curve_right not in ("linear", "precision", "fast"):
            self.curve_right = "linear"
        self.offset_left_x = max(-40, min(40, int(self.offset_left_x)))
        self.offset_left_y = max(-40, min(40, int(self.offset_left_y)))
        self.offset_right_x = max(-40, min(40, int(self.offset_right_x)))
        self.offset_right_y = max(-40, min(40, int(self.offset_right_y)))
        if self.gyro_activation not in ("always", "l2", "r2", "l1", "r1", "touchpad", "paddle_left", "paddle_right"):
            self.gyro_activation = "l2"
        if self.gyro_horizontal_axis not in ("yaw", "roll"):
            self.gyro_horizontal_axis = "yaw"
        self.gyro_deadzone = max(0, min(200, int(self.gyro_deadzone)))
        self.gyro_smoothing = max(0.0, min(0.85, float(self.gyro_smoothing)))
        self.gyro_to_stick_sensitivity = max(0.25, min(4.0, float(self.gyro_to_stick_sensitivity)))
        self.trigger_deadzone_l2 = max(0.0, min(0.5, float(self.trigger_deadzone_l2)))
        self.trigger_deadzone_r2 = max(0.0, min(0.5, float(self.trigger_deadzone_r2)))
        self.hair_trigger_threshold = max(0.02, min(0.35, float(self.hair_trigger_threshold)))
        self.rapid_trigger_release = max(0.03, min(0.25, float(self.rapid_trigger_release)))
        self.dual_stage_threshold = max(0.70, min(0.98, float(self.dual_stage_threshold)))
        self.turbo_rate_hz = max(2.0, min(25.0, float(self.turbo_rate_hz)))
        if not isinstance(self.turbo_buttons, list):
            self.turbo_buttons = []
        if not isinstance(self.key_bindings, dict):
            self.key_bindings = {}
        return self


@dataclass
class Profile:
    name: str
    game: Optional[str] = None
    trigger_l2: TriggerSettings = field(default_factory=TriggerSettings)
    trigger_r2: TriggerSettings = field(default_factory=TriggerSettings)
    haptics: HapticSettings = field(default_factory=HapticSettings)
    lighting: LightingSettings = field(default_factory=LightingSettings)
    mapping: MappingSettings = field(default_factory=MappingSettings)
    schema_version: int = 1
