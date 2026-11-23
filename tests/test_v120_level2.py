from dualcontrol import constants, protocol
from dualcontrol.models import (
    AudioSettings,
    ControllerState,
    HapticSettings,
    LightingSettings,
    MappingSettings,
    TriggerSettings,
)
from dualcontrol.services.keyboard_mapper import KeyboardMouseMapperService
from dualcontrol.virtualcontroller.mapper import map_dualsense_to_xinput


def test_gyro_to_stick_maps_gyro_to_right_stick():
    cfg = MappingSettings(
        deadzone_right=0.0,
        gyro_to_stick_enabled=True,
        gyro_to_stick_only_when_l2=True,
        gyro_to_stick_sensitivity=1.0,
    )
    # Sin L2 presionado -> sin movimiento de gyro
    idle = map_dualsense_to_xinput(ControllerState(l2_value=0, gyro_x=500, gyro_y=-600), cfg)
    assert idle.right_x == 0 and idle.right_y == 0

    # Con L2 presionado -> gyro suma al stick derecho
    aiming = map_dualsense_to_xinput(ControllerState(l2_value=200, gyro_x=500, gyro_y=-600), cfg)
    assert aiming.right_x > 0 and aiming.right_y > 0


def test_hair_trigger_and_trigger_deadzone():
    cfg = MappingSettings(trigger_deadzone_l2=0.20, hair_trigger_r2=True)
    # L2 bajo zona muerta (20% de 255 = 51) -> 0
    s1 = map_dualsense_to_xinput(ControllerState(l2_value=40, r2_value=20), cfg)
    assert s1.left_trigger == 0
    # R2 con Hair Trigger activado al superar umbral mínimo (12) -> 255 instantáneo
    assert s1.right_trigger == 255


def test_turbo_mode_pulses_button():
    cfg = MappingSettings(turbo_buttons=["cross"], turbo_rate_hz=10.0)
    st = ControllerState(cross=True)
    # Con 10 Hz -> semiciclo de 0.05s: en t=0.01 está ON, en t=0.06 está OFF
    snap_on = map_dualsense_to_xinput(st, cfg, now_ts=0.01)
    snap_off = map_dualsense_to_xinput(st, cfg, now_ts=0.06)
    assert snap_on.a is True
    assert snap_off.a is False


def test_dualsense_edge_buttons_decode_and_remap():
    data = bytearray(64)
    data[0] = constants.INPUT_REPORT_ID_USB
    data[10] = constants.BTN3_EDGE_PADDLE_LEFT | constants.BTN3_EDGE_FN_RIGHT
    state = protocol.decode_input_report(bytes(data))
    assert state.paddle_left is True
    assert state.fn_right is True
    assert state.paddle_right is False

    cfg = MappingSettings(remap={"paddle_left": "a", "fn_right": "rb"})
    snap = map_dualsense_to_xinput(state, cfg)
    assert snap.a is True
    assert snap.rb is True


def test_audio_speaker_and_mute_led_protocol():
    audio = AudioSettings(speaker_volume=100, headphone_volume=50, mic_volume=75, speaker_enabled=True, mic_muted=True)
    rep = protocol.encode_output_report(
        haptics=HapticSettings(),
        trigger_l2=TriggerSettings(),
        trigger_r2=TriggerSettings(),
        lighting=LightingSettings(),
        audio=audio,
    )
    assert rep[6] == 0x64   # speaker 100%
    assert rep[8] == 0x21   # speaker enabled
    assert rep[9] == 0x01   # mic LED orange ON
    assert rep[10] == 0x10  # mic mute ON


def test_keyboard_mapper_free_keys_dual_stage_and_mute_sync():
    vk_events = []
    mouse_events = []
    mute_calls = []
    hw_mute_calls = []
    cfg = MappingSettings(
        key_bindings={"paddle_right": "e", "triangle": "mouse_left"},
        dual_stage_r2_action="r",
    )
    svc = KeyboardMouseMapperService(
        lambda: cfg,
        vk_sender=lambda vk, p: vk_events.append((vk, p)),
        mouse_sender=lambda btn, p: mouse_events.append((btn, p)),
        mic_toggle_fn=lambda: mute_calls.append(True) or True,
        on_mute_hardware_toggle=lambda: hw_mute_calls.append(True),
    )
    svc.process_state(ControllerState(paddle_right=True, triangle=True, r2_value=245, mute=True), now_ts=0.01)
    assert (0x45, True) in vk_events   # 'e' down
    assert (0x52, True) in vk_events   # 'r' down (Dual Stage R2)
    assert ("left", True) in mouse_events
    assert len(mute_calls) == 1 and len(hw_mute_calls) == 1

    # Soltar todo -> KEYUP y MOUSEUP
    svc.process_state(ControllerState(paddle_right=False, triangle=False, r2_value=0, mute=False), now_ts=0.02)
    assert (0x45, False) in vk_events
    assert (0x52, False) in vk_events
    assert ("left", False) in mouse_events
