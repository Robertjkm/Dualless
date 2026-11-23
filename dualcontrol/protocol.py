"""Codificador/decodificador del protocolo HID del DualSense (modo USB).

Este módulo es implementación ORIGINAL de Dualless: no contiene código copiado de
ningún otro proyecto. Los desplazamientos (offsets) de cada campo dentro del informe
de 64 bytes se han verificado leyendo el código fuente de ``pydualsense`` 0.7.5
(MIT, https://github.com/flok/pydualsense), instalado en este mismo entorno de
desarrollo para poder inspeccionarlo, que a su vez cita como fuente un hilo público
de ingeniería inversa en Reddit y el proyecto Ryochan7/DS4Windows. Es decir: el
*formato* es un hecho técnico de dominio público, documentado por la comunidad desde
2020; el *código* de este archivo es nuevo.

``tests/test_cross_validate_pydualsense.py`` compara byte a byte la salida de este
módulo con la de ``pydualsense`` (construyendo su informe sin abrir ningún
dispositivo) para detectar cualquier divergencia de forma automática.

IMPORTANTE — qué NO está verificado todavía: estos bytes nunca se han enviado a un
DualSense físico desde este entorno (no hay hardware conectado aquí). La validación
final con el mando real queda pendiente y se documenta en STATUS.md.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from dualcontrol import constants as C
from typing import Optional

from dualcontrol.models import (
    AudioSettings,
    ControllerState,
    HapticSettings,
    LightingSettings,
    StickState,
    TouchPoint,
    TriggerMode,
    TriggerSettings,
)

# Valor numérico de cada TriggerMode en el firmware (ver docstring del módulo).
_TRIGGER_MODE_BYTE = {
    TriggerMode.OFF: 0x00,
    TriggerMode.RIGID: 0x01,
    TriggerMode.PULSE: 0x02,
    TriggerMode.RIGID_A: 0x01 | 0x20,
    TriggerMode.RIGID_B: 0x01 | 0x04,
    TriggerMode.RIGID_AB: 0x01 | 0x20 | 0x04,
    TriggerMode.PULSE_A: 0x02 | 0x20,
    TriggerMode.PULSE_B: 0x02 | 0x04,
    TriggerMode.PULSE_AB: 0x02 | 0x20 | 0x04,
}

# PlayerID: patrón de bits de los 5 LEDs bajo el touchpad (centro, y 2 a cada lado).
# Valores reales del firmware (no inventados): 1 luz=4, 2 luces=10, 3 luces=21,
# 4 luces=27, 5 luces=31.
_PLAYER_LED_BITMASK = {0: 0x00, 1: 4, 2: 10, 3: 21, 4: 27, 5: 31}


def _player_led_bitmask(count: int) -> int:
    count = max(0, min(5, count))
    return _PLAYER_LED_BITMASK[count]


@dataclass
class TriggerPreset:
    """Un preset de alto nivel (sección 5) traducido a modo + 7 parámetros crudos."""

    mode: TriggerMode
    forces: list


# Presets razonables basados en los rangos documentados por la comunidad para cada
# modo. Se marcan como aproximación en la interfaz: no son una tabla oficial de Sony.
TRIGGER_PRESETS: dict[str, TriggerPreset] = {
    "off": TriggerPreset(TriggerMode.OFF, [0, 0, 0, 0, 0, 0, 0]),
    "feedback": TriggerPreset(TriggerMode.RIGID, [2, 180, 0, 0, 0, 0, 0]),
    "weapon": TriggerPreset(TriggerMode.PULSE, [2, 255, 5, 0, 0, 0, 0]),
    "vibration": TriggerPreset(TriggerMode.RIGID_AB, [1, 160, 0, 0, 0, 0, 0]),
    "bow": TriggerPreset(TriggerMode.PULSE_A, [1, 90, 6, 220, 0, 0, 0]),
    "galloping": TriggerPreset(TriggerMode.PULSE_AB, [0, 200, 4, 150, 8, 220, 0]),
}


def apply_trigger_preset(settings: TriggerSettings, preset_name: str) -> TriggerSettings:
    preset = TRIGGER_PRESETS[preset_name]
    settings.mode = preset.mode
    settings.forces = list(preset.forces)
    settings.preset_name = preset_name
    settings.enabled = preset_name != "off"
    return settings.clamp()


def encode_output_report(
    *,
    haptics: HapticSettings,
    trigger_l2: TriggerSettings,
    trigger_r2: TriggerSettings,
    lighting: LightingSettings,
    mic_led: bool = False,
    mic_mute: bool = False,
    audio: Optional[AudioSettings] = None,
) -> bytes:
    """Construye el informe de salida (Report ID 0x02, 64 bytes, modo USB).

    Desplazamientos verificados (ver docstring del módulo): [1]/[2] flags de validez,
    [3]/[4] motores, [9]/[10] micrófono, [11..20] gatillo derecho, [22..31] gatillo
    izquierdo, [39] opciones de LED, [42] pulso, [43] brillo, [44] jugador,
    [45..47] color RGB del touchpad.
    """

    report = bytearray(C.OUTPUT_REPORT_LENGTH_USB)
    report[0] = C.OUTPUT_REPORT_ID_USB

    # Flags: declaramos que este paquete modifica motores, mic, ambos gatillos,
    # volumen de audio y volumen de mic (0xFF = todo lo del primer grupo).
    report[1] = 0xFF
    # Segundo grupo: LED de mic, mute, tira LED lateral, LEDs de jugador y potencia
    # global de los efectos de gatillo.
    report[2] = 0x01 | 0x02 | 0x04 | 0x10 | 0x40

    eff_left, eff_right = haptics.clamp().effective_motors()
    report[3] = eff_right
    report[4] = eff_left

    if audio is not None:
        a_cfg = audio.clamp()
        report[5] = int(round((a_cfg.headphone_volume / 100.0) * 0x7F))
        report[6] = int(round((a_cfg.speaker_volume / 100.0) * 0x64))
        report[7] = int(round((a_cfg.mic_volume / 100.0) * 0x40))
        report[8] = 0x21 if a_cfg.speaker_enabled else 0x00
        effective_mic_led = bool(mic_led or a_cfg.mic_muted)
        effective_mic_mute = bool(mic_mute or a_cfg.mic_muted)
    else:
        effective_mic_led = bool(mic_led)
        effective_mic_mute = bool(mic_mute)

    report[9] = 0x01 if effective_mic_led else 0x00
    report[10] = 0x10 if effective_mic_mute else 0x00

    r_mode = _TRIGGER_MODE_BYTE[trigger_r2.mode]
    report[11] = r_mode
    for i, value in enumerate(trigger_r2.clamp().forces[:6]):
        report[12 + i] = value
    report[20] = trigger_r2.forces[6] if len(trigger_r2.forces) > 6 else 0

    l_mode = _TRIGGER_MODE_BYTE[trigger_l2.mode]
    report[22] = l_mode
    for i, value in enumerate(trigger_l2.clamp().forces[:6]):
        report[23 + i] = value
    report[31] = trigger_l2.forces[6] if len(trigger_l2.forces) > 6 else 0

    report[39] = 0x01 | 0x02  # tira LED lateral + brillo del LED de jugador activos
    report[42] = 0x00  # sin parpadeo (PulseOptions.Off)
    report[43] = max(0, min(2, lighting.brightness))
    report[44] = _player_led_bitmask(lighting.player_led)
    report[45] = max(0, min(255, lighting.red))
    report[46] = max(0, min(255, lighting.green))
    report[47] = max(0, min(255, lighting.blue))

    return bytes(report)




def encode_output_report_bt(
    *,
    haptics: HapticSettings,
    trigger_l2: TriggerSettings,
    trigger_r2: TriggerSettings,
    lighting: LightingSettings,
    mic_led: bool = False,
    mic_mute: bool = False,
    audio: Optional[AudioSettings] = None,
) -> bytes:
    """Construye el informe de salida Bluetooth (Report ID 0x31, 78 bytes + CRC-32).

    Estructura verificada del protocolo DualSense Bluetooth:
    - Byte 0: 0x31 (Report ID)
    - Byte 1: 0x02 (etiqueta de informe HID estándar)
    - Bytes 2..48: mismo bloque de datos que USB bytes 1..47
    - Bytes 74..77: CRC-32 little-endian sobre (0xA2 + bytes 0..73)
    """
    usb_rep = encode_output_report(
        haptics=haptics,
        trigger_l2=trigger_l2,
        trigger_r2=trigger_r2,
        lighting=lighting,
        mic_led=mic_led,
        mic_mute=mic_mute,
        audio=audio,
    )
    bt_rep = bytearray(C.OUTPUT_REPORT_LENGTH_BT)
    bt_rep[0] = C.OUTPUT_REPORT_ID_BT
    bt_rep[1] = 0x02
    bt_rep[2:49] = usb_rep[1:48]

    crc = zlib.crc32(bytes([C.BT_OUTPUT_CRC_SEED]) + bytes(bt_rep[:74])) & 0xFFFFFFFF
    struct.pack_into("<I", bt_rep, 74, crc)
    return bytes(bt_rep)


def decode_input_report(data: bytes) -> ControllerState:
    """Decodifica un informe de entrada (Report ID 0x01, 64 bytes, modo USB).

    Desplazamientos verificados: [1]/[2] sticks izq., [3]/[4] sticks der.,
    [5]/[6] gatillos analógicos, [8] botones de cara + dpad, [9] L1/R1/L2/R2/
    Create/Options/L3/R3, [10] PS/touchpad/mute, [16..21] acelerómetro+giro,
    [33..40] puntos táctiles, [53] batería.
    """

    # Modo Bluetooth completo (Report ID 0x31, 78 bytes): los datos útiles empiezan en data[2]
    if len(data) >= 55 and data[0] == C.INPUT_REPORT_ID_BT:
        data = bytes([C.INPUT_REPORT_ID_USB]) + data[2:]

    # Modo Bluetooth simple (Report ID 0x01, 10 bytes, antes de activar Feature Report 0x05)
    if 10 <= len(data) < 54 and data[0] == C.INPUT_REPORT_ID_USB:
        state = ControllerState()
        state.left_stick = StickState(x=data[1], y=data[2])
        state.right_stick = StickState(x=data[3], y=data[4])
        face = data[5]
        state.square = bool(face & 0x10)
        state.cross = bool(face & 0x20)
        state.circle = bool(face & 0x40)
        state.triangle = bool(face & 0x80)
        dpad_index = face & 0x0F
        state.dpad = C.DPAD_VALUES[dpad_index] if dpad_index < len(C.DPAD_VALUES) else "NONE"
        misc = data[6]
        state.l1 = bool(misc & C.BTN2_L1)
        state.r1 = bool(misc & C.BTN2_R1)
        state.l2_button = bool(misc & C.BTN2_L2)
        state.r2_button = bool(misc & C.BTN2_R2)
        state.create = bool(misc & C.BTN2_CREATE)
        state.options = bool(misc & C.BTN2_OPTIONS)
        state.l3 = bool(misc & C.BTN2_L3)
        state.r3 = bool(misc & C.BTN2_R3)
        misc2 = data[7]
        state.ps = bool(misc2 & C.BTN3_PS)
        state.touchpad_button = bool(misc2 & C.BTN3_TOUCHPAD)
        state.l2_value = data[8]
        state.r2_value = data[9]
        return state

    if len(data) < 54:
        raise ValueError("Informe de entrada demasiado corto (se esperaban >= 54 bytes para USB o 10/78 para BT)")

    state = ControllerState()
    state.left_stick = StickState(x=data[1], y=data[2])
    state.right_stick = StickState(x=data[3], y=data[4])
    state.l2_value = data[5]
    state.r2_value = data[6]

    face = data[8]
    state.square = bool(face & 0x10)
    state.cross = bool(face & 0x20)
    state.circle = bool(face & 0x40)
    state.triangle = bool(face & 0x80)
    dpad_index = face & 0x0F
    state.dpad = C.DPAD_VALUES[dpad_index] if dpad_index < len(C.DPAD_VALUES) else "NONE"

    misc = data[9]
    state.l1 = bool(misc & C.BTN2_L1)
    state.r1 = bool(misc & C.BTN2_R1)
    state.l2_button = bool(misc & C.BTN2_L2)
    state.r2_button = bool(misc & C.BTN2_R2)
    state.create = bool(misc & C.BTN2_CREATE)
    state.options = bool(misc & C.BTN2_OPTIONS)
    state.l3 = bool(misc & C.BTN2_L3)
    state.r3 = bool(misc & C.BTN2_R3)

    misc2 = data[10]
    state.ps = bool(misc2 & C.BTN3_PS)
    state.touchpad_button = bool(misc2 & C.BTN3_TOUCHPAD)
    state.mute = bool(misc2 & C.BTN3_MUTE)
    state.fn_left = bool(misc2 & C.BTN3_EDGE_FN_LEFT)
    state.fn_right = bool(misc2 & C.BTN3_EDGE_FN_RIGHT)
    state.paddle_left = bool(misc2 & C.BTN3_EDGE_PADDLE_LEFT)
    state.paddle_right = bool(misc2 & C.BTN3_EDGE_PADDLE_RIGHT)

    def _s16(lo: int, hi: int) -> int:
        value = lo | (hi << 8)
        return value - 0x10000 if value & 0x8000 else value

    if len(data) >= 28:
        state.accel_x = _s16(data[16], data[17])
        state.accel_y = _s16(data[18], data[19])
        state.accel_z = _s16(data[20], data[21])
        state.gyro_x = _s16(data[22], data[23])
        state.gyro_y = _s16(data[24], data[25])
        state.gyro_z = _s16(data[26], data[27])

    if len(data) >= 41:
        t0_active = (data[33] & 0x80) == 0
        t0_x = ((data[35] & 0x0F) << 8) | data[34]
        t0_y = (data[36] << 4) | ((data[35] & 0xF0) >> 4)
        state.touch1 = TouchPoint(active=t0_active, finger_id=data[33] & 0x7F, x=t0_x, y=t0_y)

        t1_active = (data[37] & 0x80) == 0
        t1_x = ((data[39] & 0x0F) << 8) | data[38]
        t1_y = (data[40] << 4) | ((data[39] & 0xF0) >> 4)
        state.touch2 = TouchPoint(active=t1_active, finger_id=data[37] & 0x7F, x=t1_x, y=t1_y)

    if len(data) >= 54:
        battery_byte = data[53]
        state.battery_charging = bool((battery_byte & 0xF0) >> 4 == 0x1)
        state.battery_level = min(((battery_byte & 0x0F) * 10) + 5, 100)

    return state
