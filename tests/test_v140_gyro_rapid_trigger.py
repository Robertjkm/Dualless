from dualcontrol.models import ControllerState, MappingSettings
from dualcontrol.services.keyboard_mapper import KeyboardMouseMapperService
from dualcontrol.services.touchpad_mouse import TouchpadGyroMouseService
from dualcontrol.virtualcontroller.mapper import (
    MapperRuntimeState,
    map_dualsense_to_xinput,
)


def test_rapid_trigger_releases_and_retriggers_mid_travel():
    cfg = MappingSettings(
        rapid_trigger_r2=True,
        hair_trigger_threshold=0.05,
        rapid_trigger_release=0.10,  # ~26 unidades
    )
    rt = MapperRuntimeState()

    # 1. Presionar R2 hasta 180 -> dispara inmediatamente (255)
    s1 = map_dualsense_to_xinput(ControllerState(r2_value=180), cfg, runtime_state=rt)
    assert s1.right_trigger == 255

    # 2. Retroceder ligeramente (180 -> 145, delta=35 >= 26) -> libera a 0 sin volver a cero!
    s2 = map_dualsense_to_xinput(ControllerState(r2_value=145), cfg, runtime_state=rt)
    assert s2.right_trigger == 0

    # 3. Volver a presionar un poco (145 -> 178, delta=33 >= 26) -> vuelve a disparar (255)!
    s3 = map_dualsense_to_xinput(ControllerState(r2_value=178), cfg, runtime_state=rt)
    assert s3.right_trigger == 255


def test_hair_trigger_custom_threshold():
    cfg = MappingSettings(hair_trigger_l2=True, hair_trigger_threshold=0.20)  # ~51
    low = map_dualsense_to_xinput(ControllerState(l2_value=40), cfg)
    high = map_dualsense_to_xinput(ControllerState(l2_value=60), cfg)
    assert low.left_trigger == 0
    assert high.left_trigger == 255


def test_gyro_pro_activation_roll_axis_and_ema_smoothing():
    cfg = MappingSettings(
        deadzone_right=0.0,
        gyro_to_stick_enabled=True,
        gyro_activation="r1",
        gyro_horizontal_axis="roll",
        gyro_deadzone=80,
        gyro_smoothing=0.50,
    )
    rt = MapperRuntimeState()

    # Sin R1 -> sin salida
    s_off = map_dualsense_to_xinput(ControllerState(r1=False, gyro_z=-600), cfg, runtime_state=rt)
    assert s_off.right_x == 0

    # Con R1 y gyro_z dentro de deadzone (50 <= 80) -> sin salida
    s_dz = map_dualsense_to_xinput(ControllerState(r1=True, gyro_z=-50), cfg, runtime_state=rt)
    assert s_dz.right_x == 0

    # Con R1 y gyro_z fuerte -> primera muestra suavizada al 50% (EMA), segunda muestra sube más
    s_ema1 = map_dualsense_to_xinput(ControllerState(r1=True, gyro_z=-500), cfg, runtime_state=rt)
    s_ema2 = map_dualsense_to_xinput(ControllerState(r1=True, gyro_z=-500), cfg, runtime_state=rt)
    assert 0 < s_ema1.right_x < s_ema2.right_x


def test_touchpad_gyro_mouse_pro_axis_and_activation():
    moves = []
    svc = TouchpadGyroMouseService(None, move_fn=lambda dx, dy: moves.append((dx, dy)), button_fn=lambda b, p: None)
    svc.gyro_mouse_enabled = True
    svc.gyro_activation = "paddle_left"
    svc.gyro_horizontal_axis = "roll"
    svc.gyro_deadzone = 30
    svc.gyro_smoothing = 0.0
    svc.gyro_sensitivity = 0.02

    svc.process_state(ControllerState(paddle_left=False, gyro_z=-500))
    assert moves == []
    svc.process_state(ControllerState(paddle_left=True, gyro_z=-500))
    assert len(moves) == 1 and moves[0][0] > 0


def test_dual_stage_custom_threshold():
    events = []
    cfg = MappingSettings(dual_stage_r2_action="e", dual_stage_threshold=0.75)  # ~191
    svc = KeyboardMouseMapperService(lambda: cfg, vk_sender=lambda vk, p: events.append((vk, p)))
    svc.process_state(ControllerState(r2_value=180))
    assert events == []
    svc.process_state(ControllerState(r2_value=200))
    assert (0x45, True) in events
