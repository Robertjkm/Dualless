"""Gestor de perfiles — sección 11 de las instrucciones del proyecto.

Guarda cada perfil como un archivo JSON independiente dentro de ``profiles_dir``.
Esto cumple explícitamente el requisito de la sección 11 ("las actualizaciones de la
aplicación no deben destruir los perfiles del usuario"): los perfiles viven en una
carpeta separada del código y nunca se sobrescriben al actualizar Dualless.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from dualcontrol.models import (
    HapticSettings,
    LightingSettings,
    MappingSettings,
    Profile,
    TriggerMode,
    TriggerSettings,
)


class ProfileError(Exception):
    pass


def _safe_filename(name: str) -> str:
    keep = "-_. "
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip()
    if not cleaned:
        raise ProfileError("El nombre del perfil queda vacío tras limpiarlo")
    return cleaned


def _trigger_to_dict(t: TriggerSettings) -> dict:
    d = asdict(t)
    d["mode"] = t.mode.value
    return d


def _trigger_from_dict(d: dict) -> TriggerSettings:
    d = dict(d)
    d["mode"] = TriggerMode(d.get("mode", "off"))
    d.pop("start_position", None)
    d.pop("force_at_start", None)
    return TriggerSettings(**d).clamp()


def profile_to_dict(p: Profile) -> dict:
    return {
        "name": p.name,
        "game": p.game,
        "schema_version": p.schema_version,
        "trigger_l2": _trigger_to_dict(p.trigger_l2),
        "trigger_r2": _trigger_to_dict(p.trigger_r2),
        "haptics": asdict(p.haptics),
        "lighting": asdict(p.lighting),
        "mapping": asdict(p.mapping),
    }


def profile_from_dict(d: dict) -> Profile:
    return Profile(
        name=d["name"],
        game=d.get("game"),
        schema_version=d.get("schema_version", 1),
        trigger_l2=_trigger_from_dict(d.get("trigger_l2", {})),
        trigger_r2=_trigger_from_dict(d.get("trigger_r2", {})),
        haptics=HapticSettings(**{k: v for k, v in d.get("haptics", {}).items() if k in HapticSettings.__dataclass_fields__}).clamp(),
        lighting=LightingSettings(**{k: v for k, v in d.get("lighting", {}).items() if k in LightingSettings.__dataclass_fields__}).clamp(),
        mapping=MappingSettings(**{k: v for k, v in d.get("mapping", {}).items() if k in MappingSettings.__dataclass_fields__}).clamp(),
    )


class ProfileManager:
    def __init__(self, profiles_dir: Path) -> None:
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        return self.profiles_dir / f"{_safe_filename(name)}.json"

    def list_profiles(self) -> List[str]:
        return sorted(p.stem for p in self.profiles_dir.glob("*.json"))

    def save(self, profile: Profile, *, overwrite: bool = True) -> Path:
        path = self._path_for(profile.name)
        if path.exists() and not overwrite:
            raise ProfileError(f"El perfil '{profile.name}' ya existe")
        path.write_text(
            json.dumps(profile_to_dict(profile), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def load(self, name: str) -> Profile:
        path = self._path_for(name)
        if not path.exists():
            raise ProfileError(f"No existe el perfil '{name}'")
        data = json.loads(path.read_text(encoding="utf-8"))
        return profile_from_dict(data)

    def delete(self, name: str) -> None:
        path = self._path_for(name)
        if not path.exists():
            raise ProfileError(f"No existe el perfil '{name}'")
        path.unlink()

    def duplicate(self, name: str, new_name: str) -> Profile:
        profile = self.load(name)
        profile.name = new_name
        self.save(profile, overwrite=False)
        return profile

    def export_to(self, name: str, destination: Path) -> Path:
        src = self._path_for(name)
        if not src.exists():
            raise ProfileError(f"No existe el perfil '{name}'")
        destination = Path(destination)
        shutil.copyfile(src, destination)
        return destination

    def import_from(self, source: Path, *, new_name: Optional[str] = None) -> Profile:
        source = Path(source)
        if not source.exists():
            raise ProfileError(f"No se encuentra el archivo a importar: {source}")
        data = json.loads(source.read_text(encoding="utf-8"))
        profile = profile_from_dict(data)
        if new_name:
            profile.name = new_name
        self.save(profile, overwrite=True)
        return profile
