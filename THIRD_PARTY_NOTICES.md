# Third-Party Notices

Dualless is an independent open-source project. Below is the list of third-party
libraries and optional Windows tools used or detected by Dualless, along with
their respective licenses.

## Runtime & Optional Dependencies

### PySide6 (Qt for Python)
- Website: https://doc.qt.io/qtforpython/
- License: LGPL-3.0 (also available under Qt commercial license)
- Usage: Desktop user interface (`dualcontrol/ui/`).

### vgamepad
- Repository: https://github.com/yannbouteiller/vgamepad
- License: MIT
- Usage: Python bindings for optional virtual Xbox 360 and DualShock 4 emulation.

### ViGEmBus (optional external driver)
- Repository: https://github.com/nefarius/ViGEmBus
- License: BSD-3-Clause
- Usage: Optional Windows kernel driver for virtual Xbox 360 / DualShock 4 devices.
  Dualless only detects whether ViGEmBus is installed and links to its official
  releases page; it never downloads or installs drivers silently.

### HidHide (optional external driver/CLI)
- Repository: https://github.com/nefarius/HidHide
- License: MIT
- Usage: Optional device-hiding tool to prevent double input when virtual
  controller emulation is active. Dualless detects `HidHideCLI.exe` if already
  installed by the user and never installs it automatically.

### PyAudioWPatch (optional, Windows)
- Repository: https://github.com/s0d3s/PyAudioWPatch
- License: MIT
- Usage: Optional WASAPI Loopback audio capture for Audio-to-Rumble and 4-channel
  USB HD haptics.

### PyInstaller (build tool)
- Website: https://pyinstaller.org/
- License: GPL-2.0 with bootloader exception
- Usage: Packaging Dualless into standalone Windows executables.

### hidapi (optional fallback on Linux/macOS)
- Repository: https://github.com/libusb/hidapi
- License: BSD-3-Clause / GPLv3 / original HIDAPI license
- Usage: Optional fallback on non-Windows platforms. On Windows, Dualless uses
  its own pure-`ctypes` HID layer (`dualcontrol/backend/win32_hid.py`) built
  directly on system `hid.dll` and `setupapi.dll`.

### pydualsense (optional test cross-validation only)
- Repository: https://github.com/flok/pydualsense
- License: MIT
- Usage: Not a runtime dependency. Optionally used in
  `tests/test_cross_validate_pydualsense.py` to cross-check HID byte offsets.

## Trademarks & Independence

- PlayStation, DualSense, DualSense Edge, and DualShock are registered trademarks
  of Sony Interactive Entertainment Inc.
- Xbox and Windows are registered trademarks of Microsoft Corporation.
- Dualless is an independent open-source project and is not affiliated with,
  endorsed by, or sponsored by Sony Interactive Entertainment, Microsoft, or
  the developers of DSX (DualSenseX). All source code and vector artwork in this
  repository are original implementations.
