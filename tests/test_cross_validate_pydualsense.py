"""Valida que dualcontrol.protocol.encode_output_report coloca los bytes en los
mismos desplazamientos que la biblioteca de referencia pydualsense (MIT), sin
necesidad de ningún DualSense físico: se construye un ``pydualsense.pydualsense``
y se rellenan a mano los atributos que normalmente pone ``init()`` (que sí requiere
el dispositivo), y se llama directamente a su ``prepareReport()``.

Si ``pydualsense``/``hidapi`` no están instalados (por ejemplo, en una máquina sin
``libhidapi-dev``), esta prueba se omite en vez de fallar: es una comprobación
adicional de nuestro propio protocolo, no una dependencia obligatoria de Dualless.
"""

import pytest

pydualsense_mod = pytest.importorskip("pydualsense", reason="pydualsense/hidapi no disponibles en este sistema")

from dualcontrol import protocol  # noqa: E402
from dualcontrol.models import HapticSettings, LightingSettings, TriggerMode, TriggerSettings  # noqa: E402


def _reference_report(*, trigger_l2: TriggerSettings, trigger_r2: TriggerSettings,
                       lighting: LightingSettings, haptics: HapticSettings):
    """Construye el mismo informe usando pydualsense directamente, sin abrir hardware."""
    from pydualsense.pydualsense import pydualsense as PDS, DSTrigger, DSLight, DSAudio
    from pydualsense.enums import ConnectionType, TriggerModes, Brightness, PlayerID

    ds = PDS()
    ds.conType = ConnectionType.USB
    ds.output_report_length = 64
    ds.triggerL = DSTrigger()
    ds.triggerR = DSTrigger()
    ds.light = DSLight()
    ds.audio = DSAudio()
    ds.leftMotor = haptics.left_motor
    ds.rightMotor = haptics.right_motor

    mode_value = {
        TriggerMode.OFF: TriggerModes.Off,
        TriggerMode.RIGID: TriggerModes.Rigid,
        TriggerMode.PULSE: TriggerModes.Pulse,
        TriggerMode.RIGID_A: TriggerModes.Rigid_A,
        TriggerMode.RIGID_B: TriggerModes.Rigid_B,
        TriggerMode.RIGID_AB: TriggerModes.Rigid_AB,
        TriggerMode.PULSE_A: TriggerModes.Pulse_A,
        TriggerMode.PULSE_B: TriggerModes.Pulse_B,
        TriggerMode.PULSE_AB: TriggerModes.Pulse_AB,
    }
    ds.triggerL.mode = mode_value[trigger_l2.mode]
    ds.triggerL.forces = list(trigger_l2.clamp().forces)
    ds.triggerR.mode = mode_value[trigger_r2.mode]
    ds.triggerR.forces = list(trigger_r2.clamp().forces)

    ds.light.TouchpadColor = (lighting.red, lighting.green, lighting.blue)
    ds.light.brightness = {0: Brightness.high, 1: Brightness.medium, 2: Brightness.low}[lighting.brightness]
    ds.light.playerNumber = {0: PlayerID.PLAYER_1, 1: PlayerID.PLAYER_1, 2: PlayerID.PLAYER_2,
                              3: PlayerID.PLAYER_3, 4: PlayerID.PLAYER_4, 5: PlayerID.ALL}[lighting.player_led]

    return bytes(ds.prepareReport())


@pytest.mark.parametrize(
    "trigger_l2,trigger_r2,lighting,haptics",
    [
        (
            TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[2, 180, 0, 0, 0, 0, 0]),
            TriggerSettings(enabled=True, mode=TriggerMode.PULSE_AB, forces=[0, 200, 4, 150, 8, 220, 0]),
            LightingSettings(red=10, green=200, blue=90, brightness=1, player_led=3),
            HapticSettings(left_motor=180, right_motor=90),
        ),
        (
            TriggerSettings(),
            TriggerSettings(),
            LightingSettings(),
            HapticSettings(),
        ),
    ],
)
def test_encoder_matches_pydualsense_reference(trigger_l2, trigger_r2, lighting, haptics):
    ours = protocol.encode_output_report(
        haptics=haptics, trigger_l2=trigger_l2, trigger_r2=trigger_r2, lighting=lighting,
    )
    reference = _reference_report(
        trigger_l2=trigger_l2, trigger_r2=trigger_r2, lighting=lighting, haptics=haptics,
    )

    # Comparamos únicamente los campos que ambas implementaciones codifican, byte a
    # byte, en vez de todo el array (nuestros flags [1]/[2] declaran explícitamente
    # qué se está modificando y pueden diferir en bits que pydualsense fija siempre
    # a "todo activado"; eso es una decisión de diseño, no un error de offset).
    fields_to_compare = {
        "motor derecho [3]": (3, 3),
        "motor izquierdo [4]": (4, 4),
        "modo gatillo R2 [11]": (11, 11),
        "forces R2 [12:18]": (12, 18),
        "force6 R2 [20]": (20, 20),
        "modo gatillo L2 [22]": (22, 22),
        "forces L2 [23:29]": (23, 29),
        "force6 L2 [31]": (31, 31),
        "brillo [43]": (43, 43),
        "jugador [44]": (44, 44),
        "color RGB [45:48]": (45, 48),
    }

    mismatches = []
    for name, (start, end) in fields_to_compare.items():
        if ours[start:end + 1] != reference[start:end + 1]:
            mismatches.append(f"{name}: dualcontrol={ours[start:end+1].hex()} pydualsense={reference[start:end+1].hex()}")

    assert not mismatches, "Discrepancias con la referencia pydualsense:\n" + "\n".join(mismatches)
