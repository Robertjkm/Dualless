from types import SimpleNamespace

from dualcontrol.models import TriggerMode
from dualcontrol.services.conflict_scanner import detect_conflicts, format_conflicts_report
from dualcontrol.services.virtual_controller_service import (
    VirtualControllerService,
    compute_triggers_from_rumble,
)
from dualcontrol.virtualcontroller.base import VirtualControllerMode
from dualcontrol.virtualcontroller.xinput_vigem import (
    SimulatedXInputAdapter,
    extract_ds4_lightbar_rgb,
)


def test_extract_ds4_lightbar_rgb_formats():
    obj_upper = SimpleNamespace(Red=255, Green=40, Blue=10)
    assert extract_ds4_lightbar_rgb(obj_upper) == (255, 40, 10)
    assert extract_ds4_lightbar_rgb((0, 128, 300)) == (0, 128, 255)
    assert extract_ds4_lightbar_rgb(None) is None


def test_compute_triggers_from_rumble_deadband_and_modes():
    l_off, r_off = compute_triggers_from_rumble(10, 5)
    assert l_off.enabled is False and l_off.mode == TriggerMode.OFF
    assert r_off.enabled is False and r_off.mode == TriggerMode.OFF

    # Motor pequeño fuerte (disparo) -> R2 PULSE_AB
    l_gun, r_gun = compute_triggers_from_rumble(80, 200, strength=1.0)
    assert r_gun.enabled is True and r_gun.mode == TriggerMode.PULSE_AB
    assert l_gun.enabled is True and l_gun.mode == TriggerMode.RIGID

    # Motor grande fuerte (explosión) -> L2 RIGID_AB
    l_exp, r_exp = compute_triggers_from_rumble(220, 20, strength=1.2)
    assert l_exp.enabled is True and l_exp.mode == TriggerMode.RIGID_AB
    assert r_exp.enabled is True and r_exp.mode == TriggerMode.RIGID


def test_conflict_scanner_detects_known_apps_and_clean_state():
    clean = detect_conflicts(["explorer.exe", "notepad.exe"])
    assert clean == []
    assert "Sin conflictos" in format_conflicts_report(clean)

    found = detect_conflicts(["Steam.exe", "DS4Windows.exe", "DSX.exe"])
    names = [c.app_name for c in found]
    assert "DSX (DualSenseX)" in names
    assert "DS4Windows" in names
    assert "Steam (Steam Input)" in names
    assert any(c.severity == "alta" for c in found)


def test_virtual_controller_service_rumble_to_triggers_and_ds4_led():
    from dualcontrol.backend.simulated import SimulatedBackend
    from dualcontrol.services.controller_service import ControllerService

    backend = SimulatedBackend()
    cs = ControllerService(backend)
    cs.connect_controller()

    restored = []
    adapter = SimulatedXInputAdapter()
    vcs = VirtualControllerService(cs, adapter=adapter, triggers_restore_cb=lambda: restored.append(True))
    assert vcs.set_mode(VirtualControllerMode.XINPUT) is True

    # Activar Rumble-to-Triggers y simular vibración -> luego parar vibración y verificar restauración
    vcs.set_rumble_to_triggers(True)
    vcs._apply_rumble_main_thread(180, 160)
    assert vcs._rumble_triggers_active is True
    vcs._apply_rumble_main_thread(0, 0)
    assert vcs._rumble_triggers_active is False
    assert len(restored) == 1

    # Probar LED Passthrough real
    vcs.set_led_passthrough(True)
    vcs._apply_led_main_thread(255, 0, 128)
    rep = backend.last_output_report()
    assert rep is not None
    assert (rep[45], rep[46], rep[47]) == (255, 0, 128)

    vcs.shutdown()
    cs.disconnect_controller()
