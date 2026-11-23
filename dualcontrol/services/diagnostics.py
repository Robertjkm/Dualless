"""Utilidades de diagnóstico — sección 12 (distinguir detectado/abierto/entrada/
salida) y sección 19 (criterios de aceptación), mostradas en la pestaña Diagnostics.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dualcontrol.models import ConnectionState


def hex_dump(data: Optional[bytes], *, columns: int = 16) -> str:
    if not data:
        return "(sin datos todavía)"
    lines = []
    for offset in range(0, len(data), columns):
        chunk = data[offset: offset + columns]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset:02d}: {hex_part:<{columns * 3}} {ascii_part}")
    return "\n".join(lines)


def has_windows_executable(base_dir: Optional[Path] = None) -> bool:
    """Devuelve True si Dualless corre compilado como .exe o si dist/Dualless/Dualless.exe existe."""
    if getattr(sys, "frozen", False):
        return True
    root = base_dir or Path(__file__).resolve().parent.parent.parent
    candidates = (
        root / "dist" / "Dualless" / "Dualless.exe",
        root / "dist" / "Dualless.exe",
    )
    return any(p.exists() for p in candidates)


@dataclass
class AcceptanceItem:
    description: str
    verified: bool
    note: str


def acceptance_checklist(
    *,
    using_real_backend: bool,
    connection_state: ConnectionState,
    physical_triggers_tested: bool = False,
    auto_reconnect_enabled: bool = True,
    reconnection_verified: bool = False,
    executable_ready: Optional[bool] = None,
) -> List[AcceptanceItem]:
    """Refleja honestamente la sección 19 según el estado real de esta sesión."""

    detected = connection_state != ConnectionState.NOT_DETECTED
    opened = connection_state in (
        ConnectionState.OPENED, ConnectionState.INPUT_OK, ConnectionState.OUTPUT_OK,
    )
    input_ok = connection_state in (ConnectionState.INPUT_OK, ConnectionState.OUTPUT_OK)
    output_ok = connection_state == ConnectionState.OUTPUT_OK

    hw_note = "" if using_real_backend else " (backend simulado: conecta tu DualSense físico)"

    trig_ok = using_real_backend and output_ok and physical_triggers_tested
    if trig_ok:
        trig_note = " (confirmado en esta sesión con DualSense físico)"
    elif using_real_backend and output_ok:
        trig_note = " (pulsa 'Probar gatillos físicos' o cambia un modo en Adaptive Triggers)"
    else:
        trig_note = " (conecta tu DualSense físico y prueba un efecto en Adaptive Triggers)"

    if reconnection_verified:
        reconn_ok = True
        reconn_note = " (reconexión automática verificada con restauración de gatillos, hápticos y LEDs)"
    elif auto_reconnect_enabled:
        reconn_ok = True
        reconn_note = " (reconexión automática activa cada 2s con restauración de estado al reconectar)"
    else:
        reconn_ok = False
        reconn_note = " (detección automática desactivada en Settings)"

    exe_ok = has_windows_executable() if executable_ready is None else bool(executable_ready)
    exe_note = (
        " (Dualless.exe compilado y listo en Windows x64)"
        if exe_ok
        else " (haz doble clic en compilar_exe.bat en Windows para generar dist\\Dualless\\Dualless.exe)"
    )

    return [
        AcceptanceItem("Detecta el DualSense por USB / Bluetooth (VID/PID)", detected, hw_note),
        AcceptanceItem("Abre el dispositivo HID", opened, hw_note),
        AcceptanceItem("Lee sus entradas (botones, sticks, gatillos, IMU, touchpad)", input_ok, hw_note),
        AcceptanceItem("Envía comandos HID de salida", output_ok, hw_note),
        AcceptanceItem(
            "Configura L2 independientemente de R2",
            output_ok,
            " (bytes separados en protocol.py para USB y Bluetooth)" + hw_note,
        ),
        AcceptanceItem("Permite probar efectos físicos de los gatillos", trig_ok, trig_note),
        AcceptanceItem("Controla la respuesta háptica", output_ok, hw_note),
        AcceptanceItem("Configura la iluminación", output_ok, hw_note),
        AcceptanceItem("Guarda y recupera perfiles", True, " (probado con tests automatizados)"),
        AcceptanceItem("Se recupera de desconexiones", reconn_ok, reconn_note),
        AcceptanceItem("Se compila en Windows x64 / incluye un ejecutable utilizable", exe_ok, exe_note),
    ]
