"""Integración oficial con HidHide (Nefarius) para eliminar Double Input en Windows (v1.1.0).

Nunca instala drivers en silencio (sección 14): detecta si HidHide está instalado
en el sistema, permite registrar Dualless en la lista blanca (--app-reg) y ocultar
los dispositivos físicos DualSense (--dev-hide + --cloak-on) mientras se usa emulación
Xbox 360 o DualShock 4, restaurándolos automáticamente al volver a Native Mode o salir.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from PySide6.QtCore import QObject, Signal

HIDHIDE_DOWNLOAD_URL = "https://github.com/nefarius/HidHide/releases"


def hid_path_to_instance_id(hid_path: str) -> str:
    """Convierte una ruta de interfaz HID de Windows:
      \\\\?\\hid#vid_054c&pid_0ce6#7&123456&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}
    en el Device Instance ID que espera HidHideCLI.exe:
      HID\\VID_054C&PID_0CE6\\7&123456&0&0000
    """
    raw = (hid_path or "").strip()
    if not raw:
        return ""
    # Si ya viene como HID\... devolverlo normalizado
    if raw.upper().startswith("HID\\"):
        return raw.upper()
    cleaned = re.sub(r"^\\\\\?\\", "", raw)
    # Quitar el sufijo #{GUID}
    cleaned = re.sub(r"#\{[0-9a-fA-F\-]+\}$", "", cleaned)
    parts = cleaned.split("#")
    if len(parts) >= 3:
        return f"{parts[0].upper()}\\{parts[1].upper()}\\{parts[2].upper()}"
    return cleaned.replace("#", "\\").upper()


@dataclass
class HidHideStatus:
    installed: bool
    cli_path: str
    driver_service_present: bool
    cloak_active: bool
    hidden_devices: List[str]
    summary: str


def find_hidhide_cli() -> Optional[Path]:
    if sys.platform != "win32":
        return None
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Nefarius Software Solutions"
        / "HidHide"
        / "x64"
        / "HidHideCLI.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Nefarius Software Solutions"
        / "HidHide"
        / "HidHideCLI.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Nefarius Software Solutions"
        / "HidHide"
        / "HidHideCLI.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    which = shutil.which("HidHideCLI.exe")
    return Path(which) if which else None


def _detect_hidhide_service() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\HidHide",
            0,
            winreg.KEY_READ,
        ):
            return True
    except OSError:
        return False


class HidHideService(QObject):
    status_changed = Signal(object)  # HidHideStatus

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._cloak_active = False
        self._hidden_ids: List[str] = []
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def is_cloak_active(self) -> bool:
        return self._cloak_active

    def check_status(self) -> HidHideStatus:
        cli = find_hidhide_cli()
        drv = _detect_hidhide_service()
        installed = cli is not None or drv
        if cli is not None:
            if self._cloak_active and self._hidden_ids:
                summary = f"HidHide activo — {len(self._hidden_ids)} mando(s) físico(s) oculto(s) a los juegos."
            else:
                summary = "HidHide detectado y listo para evitar Double Input."
        elif drv:
            summary = "Driver HidHide detectado en el sistema, pero no se encontró HidHideCLI.exe."
        else:
            summary = (
                "HidHide no está instalado (opcional). Instálalo si algún juego detecta doble mando "
                "al usar emulación Xbox 360 o DualShock 4."
            )
        return HidHideStatus(
            installed=installed,
            cli_path=str(cli) if cli else "",
            driver_service_present=drv,
            cloak_active=self._cloak_active,
            hidden_devices=list(self._hidden_ids),
            summary=summary,
        )

    def _run_cli(self, args: List[str]) -> bool:
        self._last_error = ""
        cli = find_hidhide_cli()
        if cli is None:
            self._last_error = "HidHideCLI.exe no está instalado en este equipo."
            return False
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                [str(cli), *args],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=creationflags,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                self._last_error = err or f"HidHideCLI devolvió código {proc.returncode}"
                return False
            return True
        except Exception as exc:
            self._last_error = str(exc)
            return False

    def whitelist_dualless(self) -> bool:
        """Registra el ejecutable actual (Dualless.exe o python.exe) en HidHide para que siga viendo el mando."""
        exe_path = str(Path(sys.executable).resolve())
        return self._run_cli(["--app-reg", exe_path])

    def hide_controllers(self, hid_paths: Iterable[str]) -> bool:
        """Oculta los mandos físicos indicados y activa el ocultamiento de HidHide."""
        instance_ids = []
        for p in hid_paths:
            inst = hid_path_to_instance_id(p)
            if inst and inst not in instance_ids:
                instance_ids.append(inst)

        if not instance_ids:
            self._last_error = "No hay ningún DualSense físico conectado para ocultar."
            return False

        if not self.whitelist_dualless():
            return False

        for inst in instance_ids:
            if not self._run_cli(["--dev-hide", inst]):
                return False

        if not self._run_cli(["--cloak-on"]):
            return False

        self._hidden_ids = instance_ids
        self._cloak_active = True
        self.status_changed.emit(self.check_status())
        return True

    def unhide_all(self) -> bool:
        """Desactiva el ocultamiento y vuelve a mostrar todos los mandos físicos ocultados."""
        cli = find_hidhide_cli()
        if cli is None:
            self._cloak_active = False
            self._hidden_ids.clear()
            return False

        self._run_cli(["--cloak-off"])
        for inst in list(self._hidden_ids):
            self._run_cli(["--dev-unhide", inst])

        self._hidden_ids.clear()
        self._cloak_active = False
        self.status_changed.emit(self.check_status())
        return True
