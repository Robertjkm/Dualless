from dualcontrol.models import ControllerState, StickState
from dualcontrol.virtualcontroller.mapper import map_dualsense_to_xinput
from dualcontrol.virtualcontroller.xinput_vigem import SimulatedXInputAdapter


def test_map_dualsense_buttons_and_dpad_to_xinput():
    state = ControllerState(
        cross=True,
        triangle=True,
        l1=True,
        options=True,
        dpad="NE",
        l2_value=120,
        r2_value=255,
    )
    snap = map_dualsense_to_xinput(state)
    assert snap.a is True
    assert snap.y is True
    assert snap.b is False
    assert snap.lb is True
    assert snap.start is True
    assert snap.dpad_up is True
    assert snap.dpad_right is True
    assert snap.dpad_down is False
    assert snap.left_trigger == 120
    assert snap.right_trigger == 255


def test_map_dualsense_sticks_invert_y_axis_for_xinput():
    center = map_dualsense_to_xinput(ControllerState())
    assert center.left_x == 0
    assert center.left_y == 0

    up_left = ControllerState(left_stick=StickState(x=0, y=0))
    snap = map_dualsense_to_xinput(up_left)
    assert snap.left_x == -32768
    assert snap.left_y == 32767  # Y=0 en DualSense es arriba (+32767 en XInput)

    down_right = ControllerState(right_stick=StickState(x=255, y=255))
    snap2 = map_dualsense_to_xinput(down_right)
    assert snap2.right_x == 32767
    assert snap2.right_y == -32768


def test_simulated_xinput_adapter_lifecycle():
    adapter = SimulatedXInputAdapter()
    assert adapter.is_active is False
    adapter.start()
    assert adapter.is_active is True
    adapter.feed_state(ControllerState(cross=True))
    assert adapter.frames_sent == 1
    assert adapter.last_snapshot is not None
    assert adapter.last_snapshot.a is True
    adapter.stop()
    assert adapter.is_active is False


def test_button_remapping_and_disable():
    from dualcontrol.models import MappingSettings

    cfg = MappingSettings(remap={"cross": "b", "circle": "a", "ps": "none"})
    state = ControllerState(cross=True, ps=True)
    snap = map_dualsense_to_xinput(state, mapping=cfg)
    assert snap.b is True
    assert snap.a is False
    assert snap.guide is False


def test_deadzone_sensitivity_and_axis_inversion():
    from dualcontrol.models import MappingSettings

    cfg = MappingSettings(
        deadzone_left=0.20,
        sensitivity_left=1.5,
        invert_left_x=True,
        invert_left_y=True,
    )
    # Dentro de la zona muerta (128 + 10 -> ~7.8% < 20%)
    small = map_dualsense_to_xinput(ControllerState(left_stick=StickState(x=138, y=118)), mapping=cfg)
    assert small.left_x == 0
    assert small.left_y == 0

    # Fuera de la zona muerta con inversión
    big = map_dualsense_to_xinput(ControllerState(left_stick=StickState(x=255, y=0)), mapping=cfg)
    assert big.left_x == -32768  # invert_left_x=True invierte +1.0 -> -1.0
    assert big.left_y == -32768  # Y=0 normal es +1.0 en XInput; invert_left_y=True lo invierte a -1.0
