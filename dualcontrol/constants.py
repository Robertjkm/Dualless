"""Constantes del protocolo USB HID del Sony DualSense.

Estos valores están documentados públicamente por la comunidad de ingeniería inversa
(no son secretos de Sony). Las fuentes principales usadas para verificarlos en este
proyecto son:

- flok/pydualsense (MIT) — https://github.com/flok/pydualsense
- El hilo de referencia citado por ese proyecto sobre los informes HID de salida:
  https://www.reddit.com/r/gamedev/comments/jumvi5/
- Ryochan7/DS4Windows — https://github.com/Ryochan7/DS4Windows

Dualless NO copia código de DualSenseX (DSX), que es software propietario de pago
(Paliverse / Paryskye). Solo se ha usado como referencia de producto/UX, nunca de
implementación.
"""

from __future__ import annotations

# --- Identificación USB ------------------------------------------------------------
SONY_VENDOR_ID: int = 0x054C
DUALSENSE_PRODUCT_ID: int = 0x0CE6
DUALSENSE_EDGE_PRODUCT_ID: int = 0x0DF2  # DualSense Edge (soportado con Paddles y botones FN).

# --- Informes HID (modo USB; Bluetooth queda fuera del alcance de esta versión) ----
INPUT_REPORT_ID_USB: int = 0x01
OUTPUT_REPORT_ID_USB: int = 0x02

INPUT_REPORT_LENGTH_USB: int = 64
OUTPUT_REPORT_LENGTH_USB: int = 64

# --- Informes HID (modo Bluetooth) -----------------------------------------------
INPUT_REPORT_ID_BT: int = 0x31
OUTPUT_REPORT_ID_BT: int = 0x31
INPUT_REPORT_LENGTH_BT: int = 78
OUTPUT_REPORT_LENGTH_BT: int = 78
BT_OUTPUT_CRC_SEED: int = 0xA2
BT_FEATURE_CALIBRATION_ID: int = 0x05
BT_FEATURE_CALIBRATION_LEN: int = 41

# --- Máscaras de "flags" del informe de salida (qué bloques de datos son válidos) --
# El DualSense ignora cualquier campo cuyo bit de "válido" no esté activado, así que
# cada escritura debe declarar explícitamente qué está modificando.
FLAG0_COMPATIBLE_VIBRATION = 0x01
FLAG0_HAPTICS_SELECT = 0x02
FLAG0_RIGHT_TRIGGER_EFFECT = 0x04
FLAG0_LEFT_TRIGGER_EFFECT = 0x08
FLAG0_AUDIO_VOLUME = 0x10
FLAG0_MIC_VOLUME = 0x20
FLAG0_SPEAKER_COMPATIBLE = 0x40
FLAG0_MIC_MUTE_LED = 0x80

FLAG1_LIGHTBAR_SETUP_CONTROL = 0x02
FLAG1_RELEASE_LEDS = 0x04
FLAG1_PLAYER_LED = 0x10

FLAG2_LIGHTBAR_SETUP = 0x02

# --- Modos de gatillos adaptativos --------------------------------------------------
# Códigos verificados contra la implementación de pydualsense (clase TriggerModes).
# Se documentan aquí como enteros planos; la capa de aplicación los expone mediante
# un Enum legible en dualcontrol.models.TriggerMode.
TRIGGER_MODE_OFF = 0x00
TRIGGER_MODE_RIGID = 0x01          # "Feedback" — resistencia constante desde un punto.
TRIGGER_MODE_PULSE = 0x02          # "Weapon" — tope rígido entre dos puntos (gatillo de arma).
TRIGGER_MODE_RIGID_A = 0x01 | 0x20
TRIGGER_MODE_RIGID_B = 0x01 | 0x04
TRIGGER_MODE_RIGID_AB = 0x01 | 0x20 | 0x04
TRIGGER_MODE_PULSE_A = 0x02 | 0x20
TRIGGER_MODE_PULSE_B = 0x02 | 0x04
TRIGGER_MODE_PULSE_AB = 0x02 | 0x20 | 0x04
TRIGGER_MODE_CALIBRATION = 0xFC

# --- Botones (bitmask del primer byte de botones del informe de entrada) ----------
BTN_SQUARE = 0x10
BTN_CROSS = 0x20
BTN_CIRCLE = 0x40
BTN_TRIANGLE = 0x80

DPAD_MASK = 0x0F
DPAD_VALUES = (
    "N", "NE", "E", "SE", "S", "SW", "W", "NW", "NONE",
)

BTN2_L1 = 0x01
BTN2_R1 = 0x02
BTN2_L2 = 0x04
BTN2_R2 = 0x08
BTN2_CREATE = 0x10
BTN2_OPTIONS = 0x20
BTN2_L3 = 0x40
BTN2_R3 = 0x80

BTN3_PS = 0x01
BTN3_TOUCHPAD = 0x02
BTN3_MUTE = 0x04
BTN3_EDGE_FN_LEFT = 0x10
BTN3_EDGE_FN_RIGHT = 0x20
BTN3_EDGE_PADDLE_LEFT = 0x40
BTN3_EDGE_PADDLE_RIGHT = 0x80

# --- Rutas de aplicación -------------------------------------------------------------
PROFILES_DIR_NAME = "profiles"
APP_NAME = "Dualless"
APP_VERSION_STAGE = "1.4.0 (Gyro Pro, Rapid Trigger, Dual Stage Táctil y Empaquetado 1-Clic IExpress)"
