import array

from dualcontrol.models import ControllerState, Profile, TouchPoint
from dualcontrol.services.audio_rumble import compute_rumble_from_pcm16
from dualcontrol.services.game_watcher import match_profile_for_process


def test_match_profile_for_process_exact_and_substring():
    profiles = [
        Profile(name="RDR2", game="RDR2.exe"),
        Profile(name="Dead Space", game="Dead Space"),
    ]
    assert match_profile_for_process("RDR2.exe", profiles).name == "RDR2"
    assert match_profile_for_process("Dead Space.exe", profiles).name == "Dead Space"
    assert match_profile_for_process("notepad.exe", profiles) is None


def test_compute_rumble_from_pcm16_silence_and_loud():
    silence = array.array("h", [0] * 512).tobytes()
    assert compute_rumble_from_pcm16(silence) == (0, 0)

    loud = array.array("h", [20000, -20000] * 256).tobytes()
    left, right = compute_rumble_from_pcm16(loud)
    assert left > 100 and right > 100
