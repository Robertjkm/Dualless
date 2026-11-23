import array

from dualcontrol.services.audio_rumble import process_pcm16_to_usb_haptics_4ch
from dualcontrol.services.hidhide_service import hid_path_to_instance_id


def test_hid_path_to_instance_id_conversion():
    win_path = r"\\?\hid#vid_054c&pid_0ce6#7&1234abcd&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
    assert hid_path_to_instance_id(win_path) == r"HID\VID_054C&PID_0CE6\7&1234ABCD&0&0000"


def test_process_pcm16_to_usb_haptics_4ch_routes_only_channels_3_and_4():
    # 64 frames estéreo con señal fuerte
    stereo = array.array("h", [18000, -18000] * 64).tobytes()
    out_bytes = process_pcm16_to_usb_haptics_4ch(stereo, gain=1.5, alpha=0.2)
    out = array.array("h")
    out.frombytes(out_bytes)
    assert len(out) == 64 * 4
    # Canales 0 y 1 (auriculares) deben permanecer en silencio (0)
    assert all(out[i * 4] == 0 and out[i * 4 + 1] == 0 for i in range(64))
    # Canales 2 y 3 (actuadores VCM) deben llevar la onda táctil
    assert any(out[i * 4 + 2] != 0 and out[i * 4 + 3] != 0 for i in range(64))
