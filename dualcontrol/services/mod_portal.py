"""Portal de Mods de Dualless — inspección, clasificación y registro de mods.

Permite arrastrar y soltar (o seleccionar) archivos ``.zip``, ``.rar``, ``.asi`` o
carpetas descomprimidas de mods de juegos. Clasifica automáticamente el mod:

- ``dsx_udp``: Mods que envían instrucciones al servidor UDP estilo DSX
  (por ejemplo ``DSX.asi`` + ``DSX/Settings.ini``).
- ``hid_direct``: Mods que hablan directamente con el DualSense por USB HID
  (por ejemplo ``DualSenseRDR2.asi`` + ``weapons.json``).
- ``unknown``: Otros archivos o carpetas sin firma reconocida.

Guarda el registro en ``profiles/mods_registry.json`` para sobrevivir actualizaciones.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from dualcontrol.models import LightingSettings, Profile, TriggerMode, TriggerSettings


@dataclass
class ModEntry:
    name: str
    source_path: str
    mod_type: str  # "dsx_udp" | "hid_direct" | "unknown"
    udp_port: int = 6969
    profile_name: str = ""
    notes: str = ""


def _extract_port_from_text(text: str, default: int = 6969) -> int:
    for pattern in (
        r"(?i)port\s*[=:]\s*(\d{2,5})",
        r"(?i)udp_?port\s*[=:]\s*(\d{2,5})",
        r"(?i)server_?port\s*[=:]\s*(\d{2,5})",
    ):
        m = re.search(pattern, text)
        if m:
            port = int(m.group(1))
            if 1024 <= port <= 65535:
                return port
    return default


def _inspect_entries(names: List[str], ini_texts: List[str], fallback_name: str) -> ModEntry:
    lower_names = [n.replace("\\", "/").lower() for n in names]
    joined = "\n".join(lower_names)

    port = 6969
    for txt in ini_texts:
        detected = _extract_port_from_text(txt, default=0)
        if detected:
            port = detected
            break

    is_dsx = any(
        n.endswith("dsx.asi") or "/dsx/" in f"/{n}" or "dsx/settings.ini" in n
        for n in lower_names
    )
    is_hid_direct = any(
        "dualsenserdr2" in n or "dualsensehaptics" in n or n.endswith("weapons.json")
        for n in lower_names
    )

    if is_dsx:
        return ModEntry(
            name=fallback_name,
            source_path="",
            mod_type="dsx_udp",
            udp_port=port,
            profile_name=f"Mod_{fallback_name}",
            notes=(
                f"Mod compatible con servidor UDP (estilo DSX, puerto {port}). "
                "Enciende el Servidor UDP arriba y ejecuta el juego con el mod instalado."
            ),
        )

    if is_hid_direct:
        return ModEntry(
            name=fallback_name,
            source_path="",
            mod_type="hid_direct",
            udp_port=port,
            profile_name=f"Mod_{fallback_name}",
            notes=(
                "Mod de acceso USB HID directo (habla directo con el DualSense). "
                "Recuerda desconectar el mando en Dashboard antes de abrir el juego para evitar conflictos."
            ),
        )

    if ".asi" in joined:
        return ModEntry(
            name=fallback_name,
            source_path="",
            mod_type="dsx_udp",
            udp_port=port,
            profile_name=f"Mod_{fallback_name}",
            notes=(
                f"Plugin .asi detectado. Si utiliza protocolo UDP estilo DSX, "
                f"activa el Servidor UDP en el puerto {port}."
            ),
        )

    return ModEntry(
        name=fallback_name,
        source_path="",
        mod_type="unknown",
        udp_port=port,
        profile_name=f"Mod_{fallback_name}",
        notes="Archivo registrado. Puedes activar el servidor UDP o ajustar el perfil manualmente.",
    )


def inspect_mod_source(path: Path) -> ModEntry:
    """Analiza un .zip, .rar, .asi o carpeta y devuelve un ModEntry clasificado."""
    path = Path(path)
    raw_name = path.stem if path.is_file() else path.name
    clean_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_name).strip("_") or "Mod"
    names: List[str] = []
    ini_texts: List[str] = []

    if path.is_dir():
        for p in path.rglob("*"):
            rel = str(p.relative_to(path)).replace("\\", "/")
            names.append(rel)
            if p.is_file() and p.suffix.lower() in (".ini", ".cfg", ".txt", ".json"):
                if p.stat().st_size <= 128 * 1024:
                    try:
                        ini_texts.append(p.read_text(encoding="utf-8", errors="ignore"))
                    except OSError:
                        pass
    elif path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".zip":
            try:
                with zipfile.ZipFile(path, "r") as z:
                    names = z.namelist()
                    for n in names:
                        if n.lower().endswith((".ini", ".cfg", ".txt")) and not n.endswith("/"):
                            info = z.getinfo(n)
                            if info.file_size <= 128 * 1024:
                                ini_texts.append(z.read(n).decode("utf-8", errors="ignore"))
            except zipfile.BadZipFile:
                names = [path.name]
        elif suffix == ".rar":
            # Inspección ligera de nombres ASCII embebidos en cabeceras RAR (sin requerir unrar.exe)
            try:
                raw = path.read_bytes()
                found_tokens = re.findall(rb"[A-Za-z0-9_./\\-]{3,80}\.(?:asi|ini|json|dll|txt)", raw)
                names = [t.decode("ascii", errors="ignore") for t in found_tokens]
                if not names:
                    names = [path.name]
            except OSError:
                names = [path.name]
        else:
            names = [path.name]
            if suffix in (".ini", ".cfg", ".txt"):
                try:
                    ini_texts.append(path.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    pass

    entry = _inspect_entries(names, ini_texts, clean_name)
    entry.source_path = str(path)
    return entry


class ModPortalManager:
    """Gestiona los mods importados y crea automáticamente perfiles asociados."""

    def __init__(self, profiles_dir: Path, profile_manager) -> None:
        self._dir = Path(profiles_dir).parent / "mods"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._registry_file = self._dir / "registry.json"
        self._profile_manager = profile_manager

    def list_mods(self) -> List[ModEntry]:
        if not self._registry_file.exists():
            return []
        try:
            raw = json.loads(self._registry_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        result: List[ModEntry] = []
        for item in raw:
            if isinstance(item, dict) and "name" in item:
                result.append(
                    ModEntry(
                        name=str(item.get("name", "")),
                        source_path=str(item.get("source_path", "")),
                        mod_type=str(item.get("mod_type", "unknown")),
                        udp_port=int(item.get("udp_port", 6969)),
                        profile_name=str(item.get("profile_name", "")),
                        notes=str(item.get("notes", "")),
                    )
                )
        return result

    def _save_all(self, mods: List[ModEntry]) -> None:
        data = [asdict(m) for m in mods]
        self._registry_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_mod(self, path: Path) -> ModEntry:
        entry = inspect_mod_source(path)
        mods = [m for m in self.list_mods() if m.name != entry.name]
        mods.append(entry)
        self._save_all(mods)

        # Crear perfil asociado automáticamente en ProfileManager si no existe
        if self._profile_manager is not None and entry.profile_name:
            existing = self._profile_manager.list_profiles()
            if entry.profile_name not in existing:
                profile = Profile(
                    name=entry.profile_name,
                    game=entry.name,
                    trigger_l2=TriggerSettings(enabled=False, mode=TriggerMode.OFF),
                    trigger_r2=TriggerSettings(enabled=False, mode=TriggerMode.OFF),
                    lighting=LightingSettings(red=46, green=107, blue=255, brightness=1, player_led=1),
                )
                self._profile_manager.save(profile)

        return entry

    def remove_mod(self, name: str) -> None:
        mods = [m for m in self.list_mods() if m.name != name]
        self._save_all(mods)
