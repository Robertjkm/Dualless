import pytest

from dualcontrol.backend.base import BackendError
from dualcontrol.backend.simulated import SimulatedBackend
from dualcontrol.models import ConnectionState, HapticSettings, LightingSettings, TriggerMode, TriggerSettings


def test_detect_and_open_happy_path():
    backend = SimulatedBackend()
    assert backend.detect() is True
    backend.open()
    assert backend.connection_state == ConnectionState.OPENED


def test_detect_failure_raises_on_open():
    backend = SimulatedBackend(fail_detect=True)
    assert backend.detect() is False
    with pytest.raises(BackendError):
        backend.open()


def test_read_state_progresses_connection_state():
    backend = SimulatedBackend()
    backend.detect()
    backend.open()
    backend.read_state()
    assert backend.connection_state == ConnectionState.INPUT_OK


def test_apply_trigger_updates_output_and_state_machine():
    backend = SimulatedBackend()
    backend.detect()
    backend.open()
    backend.read_state()

    settings = TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[2, 200, 0, 0, 0, 0, 0])
    backend.apply_trigger("L2", settings)

    assert backend.connection_state == ConnectionState.OUTPUT_OK
    report = backend.last_output_report()
    assert report is not None
    assert report[22] == 0x01  # modo Rigid
    assert report[23] == 2
    assert report[24] == 200


def test_apply_trigger_invalid_side_raises():
    backend = SimulatedBackend()
    backend.open()
    with pytest.raises(ValueError):
        backend.apply_trigger("L3", TriggerSettings())


def test_restore_defaults_resets_output():
    backend = SimulatedBackend()
    backend.open()
    backend.apply_lighting(LightingSettings(red=255, green=0, blue=0))
    backend.restore_defaults()
    report = backend.last_output_report()
    default_lighting = LightingSettings()
    assert report[45] == default_lighting.red
    assert report[46] == default_lighting.green
    assert report[47] == default_lighting.blue


def test_inject_state_notifies_listeners():
    backend = SimulatedBackend()
    backend.open()
    received = []
    backend.on_state_changed(lambda s: received.append(s))

    from dualcontrol.models import ControllerState
    fake_state = ControllerState(cross=True)
    backend.inject_state(fake_state)

    assert len(received) == 1
    assert received[0].cross is True
    assert backend.read_state().cross is True


def test_apply_haptics_changes_motor_bytes():
    backend = SimulatedBackend()
    backend.open()
    backend.apply_haptics(HapticSettings(left_motor=33, right_motor=200))
    report = backend.last_output_report()
    assert report[3] == 200
    assert report[4] == 33
