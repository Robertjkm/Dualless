from dualcontrol import constants, protocol
from dualcontrol.models import HapticSettings, LightingSettings, TriggerMode, TriggerSettings


def _base_kwargs():
    return dict(
        haptics=HapticSettings(),
        trigger_l2=TriggerSettings(),
        trigger_r2=TriggerSettings(),
        lighting=LightingSettings(),
    )


def test_output_report_length_and_id():
    report = protocol.encode_output_report(**_base_kwargs())
    assert len(report) == constants.OUTPUT_REPORT_LENGTH_USB
    assert report[0] == constants.OUTPUT_REPORT_ID_USB


def test_trigger_bytes_are_independent_for_l2_and_r2():
    kwargs = _base_kwargs()
    kwargs["trigger_l2"] = TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[2, 180, 0, 0, 0, 0, 0])
    kwargs["trigger_r2"] = TriggerSettings(enabled=True, mode=TriggerMode.PULSE, forces=[4, 90, 0, 0, 0, 0, 0])
    report = protocol.encode_output_report(**kwargs)

    # R2: offset 11 (modo) + 12..17 (forces 0-5) + 20 (force 6)
    assert report[11] == 0x02
    assert report[12] == 4
    assert report[13] == 90

    # L2: offset 22 (modo) + 23..28 (forces 0-5) + 31 (force 6)
    assert report[22] == 0x01
    assert report[23] == 2
    assert report[24] == 180

    # Cambiar L2 no debe afectar los bytes de R2
    assert report[11] == 0x02
    assert report[12] == 4


def test_lighting_bytes_offsets():
    kwargs = _base_kwargs()
    kwargs["lighting"] = LightingSettings(red=10, green=20, blue=30, brightness=1, player_led=3)
    report = protocol.encode_output_report(**kwargs)
    assert report[43] == 1
    assert report[45] == 10
    assert report[46] == 20
    assert report[47] == 30
    # player_led=3 -> bitmask conocido del firmware (PLAYER_3 = 21)
    assert report[44] == 21


def test_haptics_bytes_offsets():
    kwargs = _base_kwargs()
    kwargs["haptics"] = HapticSettings(left_motor=200, right_motor=100)
    report = protocol.encode_output_report(**kwargs)
    assert report[3] == 100  # right motor
    assert report[4] == 200  # left motor


def test_trigger_settings_clamp_rejects_out_of_range():
    settings = TriggerSettings(forces=[999, -5, 0, 0, 0, 0, 0])
    settings.clamp()
    assert settings.forces[0] == 255
    assert settings.forces[1] == 0


def test_decode_input_report_buttons_and_sticks():
    data = bytearray(64)
    data[0] = constants.INPUT_REPORT_ID_USB
    data[1] = 200  # left stick x
    data[2] = 50   # left stick y
    data[5] = 77   # L2 analog
    data[6] = 150  # R2 analog
    data[8] = constants.BTN_CROSS | 0x05  # cross pressed + dpad=5 (SW)
    data[9] = constants.BTN2_L1 | constants.BTN2_R2
    data[10] = constants.BTN3_PS

    state = protocol.decode_input_report(bytes(data))
    assert state.left_stick.x == 200
    assert state.left_stick.y == 50
    assert state.l2_value == 77
    assert state.r2_value == 150
    assert state.cross is True
    assert state.square is False
    assert state.dpad == "SW"
    assert state.l1 is True
    assert state.r2_button is True
    assert state.ps is True


def test_apply_trigger_preset_sets_enabled_and_mode():
    settings = TriggerSettings()
    protocol.apply_trigger_preset(settings, "weapon")
    assert settings.enabled is True
    assert settings.mode == TriggerMode.PULSE
    assert settings.preset_name == "weapon"

    protocol.apply_trigger_preset(settings, "off")
    assert settings.enabled is False
    assert settings.mode == TriggerMode.OFF
