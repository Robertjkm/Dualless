import json
from pathlib import Path

from dualcontrol.models import TriggerMode
from dualcontrol.services.dsx_udp import build_test_weapon_packet, parse_dsx_packet
from dualcontrol.services.mod_portal import ModPortalManager, inspect_mod_source
from dualcontrol.services.profile_manager import ProfileManager


def test_parse_dsx_trigger_weapon_and_rgb():
    packet = build_test_weapon_packet("R2")
    cmds = parse_dsx_packet(packet)
    assert len(cmds) == 2
    assert cmds[0].kind == "trigger"
    assert cmds[0].side == "R2"
    assert cmds[0].trigger is not None
    assert cmds[0].trigger.mode == TriggerMode.PULSE
    assert cmds[0].trigger.forces[0] == 2
    assert cmds[0].trigger.forces[1] == 255
    assert cmds[1].kind == "rgb"
    assert cmds[1].rgb == (46, 107, 255)


def test_parse_dsx_custom_and_reset():
    raw = json.dumps({
        "Instructions": [
            {"Type": 1, "Parameters": [0, 1, 12, 1, 3, 200, 0, 0, 0, 0, 0]},
            {"Type": 7, "Parameters": [0]},
        ]
    })
    cmds = parse_dsx_packet(raw)
    assert len(cmds) == 2
    assert cmds[0].side == "L2"
    assert cmds[0].trigger is not None
    assert cmds[0].trigger.mode == TriggerMode.RIGID
    assert cmds[0].trigger.forces[0] == 3
    assert cmds[0].trigger.forces[1] == 200
    assert cmds[1].kind == "reset"


def test_mod_portal_classifies_dsx_folder_and_creates_profile(tmp_path):
    mod_dir = tmp_path / "MiModDSX"
    (mod_dir / "DSX").mkdir(parents=True)
    (mod_dir / "DSX.asi").write_bytes(b"fake")
    (mod_dir / "DSX" / "Settings.ini").write_text("Port=6970\n", encoding="utf-8")

    pm = ProfileManager(tmp_path / "profiles")
    portal = ModPortalManager(tmp_path / "profiles", pm)
    entry = portal.import_mod(mod_dir)

    assert entry.mod_type == "dsx_udp"
    assert entry.udp_port == 6970
    assert entry.profile_name in pm.list_profiles()
