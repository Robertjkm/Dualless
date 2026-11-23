"""Detector de conflictos HID en vivo para Windows (v1.3.0).

Escanea los procesos activos en Windows buscando aplicaciones que suelen competir
por el acceso exclusivo al Sony DualSense o provocar Double Input (DSX, DS4Windows,
reWASD, Steam Input, PlayStation Accessories, x360ce). Nunca cierra procesos ni
modifica el sistema sin permiso del usuario: solo informa con recomendaciones claras.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, List, Tuple


@dataclass(frozen=True)
class ConflictEntry:
    process_name: str
    app_name: str
    severity: str       # "alta" | "media"
    recommendation: str


KNOWN_CONFLICTS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "dsx.exe",
        "DSX (DualSenseX)",
        "alta",
        "Cierra DSX antes de usar Dualless para evitar bloqueos HID, LEDs parpadeando o doble mando virtual.",
    ),
    (
        "dualsensex.exe",
        "DualSenseX",
        "alta",
        "Cierra DualSenseX mientras Dualless esté abierto para evitar conflictos de escritura HID.",
    ),
    (
        "ds4windows.exe",
        "DS4Windows",
        "alta",
        "Cierra DS4Windows: compite directamente por el mando físico y crea un segundo dispositivo ViGEmBus.",
    ),
    (
        "rewasd.exe",
        "reWASD",
        "alta",
        "Pausa el remapeo en reWASD o ciérralo para evitar interferencias de driver con el DualSense.",
    ),
    (
        "rewasdengine.exe",
        "reWASD Engine",
        "alta",
        "El servicio de reWASD está activo en segundo plano; desactiva la ranura del mando si notas entradas duplicadas.",
    ),
    (
        "steam.exe",
        "Steam (Steam Input)",
        "media",
        "Steam está abierto. Si usas emulación Xbox/DS4 o notas doble entrada, desactiva 'Steam Input' en las propiedades del juego.",
    ),
    (
        "playstationaccessories.exe",
        "PlayStation Accessories",
        "media",
        "La app oficial de Sony puede retener el acceso HID durante actualizaciones; ciérrala si los gatillos no responden.",
    ),
    (
        "x360ce.exe",
        "x360ce",
        "media",
        "Cierra x360ce para evitar mandos virtuales XInput duplicados.",
    ),
)


def list_running_windows_processes() -> List[str]:
    """Devuelve los nombres de procesos activos en Windows usando tasklist (sin ventana)."""
    if sys.platform != "win32":
        return []
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=creationflags,
        )
        if proc.returncode != 0:
            return []
        names: List[str] = []
        reader = csv.reader(io.StringIO(proc.stdout))
        for row in reader:
            if row and row[0].strip():
                names.append(row[0].strip())
        return names
    except Exception:
        return []


def detect_conflicts(process_names: Iterable[str]) -> List[ConflictEntry]:
    """Compara una lista de nombres de proceso contra los conflictos HID conocidos."""
    lowered = {str(p).strip().lower() for p in process_names if p}
    found: List[ConflictEntry] = []
    seen_apps = set()
    for proc_key, app_name, severity, rec in KNOWN_CONFLICTS:
        if proc_key in lowered and app_name not in seen_apps:
            seen_apps.add(app_name)
            found.append(
                ConflictEntry(
                    process_name=proc_key,
                    app_name=app_name,
                    severity=severity,
                    recommendation=rec,
                )
            )
    return found


def scan_live_conflicts(
    process_lister: Callable[[], Iterable[str]] = list_running_windows_processes,
) -> List[ConflictEntry]:
    return detect_conflicts(process_lister())


def format_conflicts_report(conflicts: List[ConflictEntry]) -> str:
    if not conflicts:
        return "✅ Sin conflictos HID detectados (no hay DSX, DS4Windows, reWASD ni Steam compitiendo)."
    lines = []
    for c in conflicts:
        icon = "🔴" if c.severity == "alta" else "🟡"
        lines.append(f"{icon} {c.app_name} ({c.process_name}): {c.recommendation}")
    return "\n".join(lines)
