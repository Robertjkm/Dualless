from pathlib import Path

from dualcontrol.models import ControllerState, MappingSettings, StickState
from dualcontrol.services.macro_service import MacroService
from dualcontrol.services.settings_store import AppSettings, SettingsStore
from dualcontrol.virtualcontroller.mapper import map_dualsense_to_xinput


def test_settings_store_roundtrip(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.json")
    orig = AppSettings(minimize_to_tray=False, last_profile_name="RDR2", touchpad_sensitivity=0.8)
    store.save(orig)
    loaded = store.load()
    assert loaded.minimize_to_tray is False
    assert loaded.last_profile_name == "RDR2"
    assert abs(loaded.touchpad_sensitivity - 0.8) < 1e-6


def test_anti_drift_calibration_and_curves():
    # Stick con drift en reposo (x=136 en lugar de 128)
    drifting = ControllerState(left_stick=StickState(x=136, y=128))
    calibrated = MappingSettings(deadzone_left=0.0, offset_left_x=-8)
    snap = map_dualsense_to_xinput(drifting, calibrated)
    assert snap.left_x == 0

    # Curva precision reduce magnitud a medio recorrido respecto a lineal
    half = ControllerState(left_stick=StickState(x=192, y=128))
    lin = map_dualsense_to_xinput(half, MappingSettings(deadzone_left=0.0, curve_left="linear")).left_x
    prec = map_dualsense_to_xinput(half, MappingSettings(deadzone_left=0.0, curve_left="precision")).left_x
    fast = map_dualsense_to_xinput(half, MappingSettings(deadzone_left=0.0, curve_left="fast")).left_x
    assert prec < lin < fast
