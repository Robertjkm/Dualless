r"""Utilidades nativas de Windows (sin dependencias externas):
- Inicio automático con Windows (HKCU\...\Run vía winreg)
- Detección del ejecutable (.exe) de la ventana activa (user32 + kernel32)
- Inyección nativa de movimiento y clics de ratón (SendInput)
En Linux/macOS todas las funciones degradan de forma segura sin lanzar errores.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_NAME = "Dualless"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    root = Path(__file__).resolve().parent.parent.parent
    run_py = root / "run.py"
    return f'"{sys.executable}" "{run_py}"'


def is_start_with_windows_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _RUN_VALUE_NAME)
            return True
    except OSError:
        return False


def set_start_with_windows(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def get_foreground_process_name() -> str:
    """Devuelve el nombre del proceso activo en primer plano (ej. 'RDR2.exe') en Windows."""
    if sys.platform != "win32":
        return ""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""
        try:
            buf_size = ctypes.c_ulong(512)
            buf = ctypes.create_unicode_buffer(512)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_size)):
                return Path(buf.value).name
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""
    return ""


# --- Inyección nativa de ratón con SendInput (Windows) -----------------------------
_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]


def _send_mouse(dx: int = 0, dy: int = 0, flags: int = 0) -> None:
    if sys.platform != "win32":
        return
    try:
        extra = ctypes.c_ulong(0)
        inp = _INPUT(
            type=_INPUT_MOUSE,
            union=_INPUT_UNION(
                mi=_MOUSEINPUT(
                    dx=int(dx),
                    dy=int(dy),
                    mouseData=0,
                    dwFlags=int(flags),
                    time=0,
                    dwExtraInfo=ctypes.pointer(extra),
                )
            ),
        )
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    except Exception:
        pass


def move_mouse_relative(dx: int, dy: int) -> None:
    if dx == 0 and dy == 0:
        return
    _send_mouse(dx=dx, dy=dy, flags=_MOUSEEVENTF_MOVE)


def mouse_button_event(button: str, pressed: bool) -> None:
    if button == "left":
        flag = _MOUSEEVENTF_LEFTDOWN if pressed else _MOUSEEVENTF_LEFTUP
    elif button == "right":
        flag = _MOUSEEVENTF_RIGHTDOWN if pressed else _MOUSEEVENTF_RIGHTUP
    else:
        return
    _send_mouse(flags=flag)


# --- Inyección nativa de atajos de teclado con SendInput (Windows) -----------------
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_LWIN = 0x5B
VK_SNAPSHOT = 0x2C
VK_MENU = 0x12  # Alt
VK_TAB = 0x09


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KBD_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _KBD_INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _KBD_UNION)]


def send_key_combo(vk_codes: list[int]) -> None:
    """Envía una pulsación combinada de teclas virtuales de Windows (ej. [VK_LWIN, VK_SNAPSHOT])."""
    if sys.platform != "win32" or not vk_codes:
        return
    try:
        extra = ctypes.c_ulong(0)
        events = []
        for vk in vk_codes:
            events.append(
                _KBD_INPUT(
                    type=_INPUT_KEYBOARD,
                    union=_KBD_UNION(ki=_KEYBDINPUT(wVk=int(vk), wScan=0, dwFlags=0, time=0, dwExtraInfo=ctypes.pointer(extra))),
                )
            )
        for vk in reversed(vk_codes):
            events.append(
                _KBD_INPUT(
                    type=_INPUT_KEYBOARD,
                    union=_KBD_UNION(ki=_KEYBDINPUT(wVk=int(vk), wScan=0, dwFlags=_KEYEVENTF_KEYUP, time=0, dwExtraInfo=ctypes.pointer(extra))),
                )
            )
        arr = (_KBD_INPUT * len(events))(*events)
        ctypes.windll.user32.SendInput(len(events), arr, ctypes.sizeof(_KBD_INPUT))
    except Exception:
        pass


# --- Nivel 2: Teclas individuales (down/up) y silencio de micrófono Windows --------
KEY_VK_MAP: dict[str, int] = {
    "space": 0x20,
    "enter": 0x0D,
    "esc": 0x1B,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "tab": 0x09,
    "w": 0x57,
    "a": 0x41,
    "s": 0x53,
    "d": 0x44,
    "e": 0x45,
    "f": 0x46,
    "r": 0x52,
    "q": 0x51,
    "g": 0x47,
    "c": 0x43,
    "v": 0x56,
    "m": 0x4D,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "f5": 0x74,
    "f9": 0x78,
    "f12": 0x7B,
}

KEY_BINDING_OPTIONS: tuple[tuple[str, str], ...] = (
    ("none", "Sin tecla asignada"),
    ("space", "Tecla Espacio (Space)"),
    ("shift", "Tecla Shift (Correr / Agachar)"),
    ("ctrl", "Tecla Ctrl"),
    ("alt", "Tecla Alt"),
    ("tab", "Tecla Tab"),
    ("enter", "Tecla Enter"),
    ("esc", "Tecla Esc"),
    ("e", "Tecla E (Interactuar)"),
    ("f", "Tecla F"),
    ("r", "Tecla R (Recargar)"),
    ("q", "Tecla Q"),
    ("g", "Tecla G (Granada)"),
    ("c", "Tecla C"),
    ("v", "Tecla V"),
    ("m", "Tecla M (Mapa)"),
    ("1", "Tecla 1"),
    ("2", "Tecla 2"),
    ("3", "Tecla 3"),
    ("4", "Tecla 4"),
    ("w", "Tecla W"),
    ("a", "Tecla A"),
    ("s", "Tecla S"),
    ("d", "Tecla D"),
    ("f5", "Tecla F5 (Guardado rápido)"),
    ("f9", "Tecla F9 (Carga rápida)"),
    ("f12", "Tecla F12 (Captura Steam)"),
    ("mouse_left", "Ratón — Clic Izquierdo"),
    ("mouse_right", "Ratón — Clic Derecho"),
    ("volume_up", "Windows — Subir volumen"),
    ("volume_down", "Windows — Bajar volumen"),
    ("screenshot", "Windows — Captura (Win+ImprPant)"),
)


def send_vk_event(vk_code: int, pressed: bool) -> None:
    """Envía pulsación o liberación individual de una tecla virtual de Windows."""
    if sys.platform != "win32":
        return
    try:
        extra = ctypes.c_ulong(0)
        flags = 0 if pressed else _KEYEVENTF_KEYUP
        inp = _KBD_INPUT(
            type=_INPUT_KEYBOARD,
            union=_KBD_UNION(
                ki=_KEYBDINPUT(
                    wVk=int(vk_code),
                    wScan=0,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=ctypes.pointer(extra),
                )
            ),
        )
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_KBD_INPUT))
    except Exception:
        pass


def toggle_windows_mic_mute() -> bool:
    """Alterna el silencio del micrófono predeterminado de Windows vía WM_APPCOMMAND."""
    if sys.platform != "win32":
        return False
    try:
        WM_APPCOMMAND = 0x0319
        APPCOMMAND_MICROPHONE_VOLUME_MUTE = 24
        hwnd = ctypes.windll.user32.GetForegroundWindow() or 0xFFFF
        ctypes.windll.user32.SendMessageW(
            hwnd,
            WM_APPCOMMAND,
            0,
            APPCOMMAND_MICROPHONE_VOLUME_MUTE << 16,
        )
        return True
    except Exception:
        return False
