"""Persistencia automática de configuración de Dualless en settings.json (v1.1.0)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict


DEFAULT_MACROS: Dict[str, str] = {
    "ps+l1": "volume_down",
    "ps+r1": "volume_up",
    "mute": "volume_mute",
    "create+options": "screenshot",
    "ps+triangle": "next_profile",
}


@dataclass
class AppSettings:
    auto_detect_enabled: bool = True
    auto_hidhide: bool = True
    minimize_to_tray: bool = True
    low_battery_alerts: bool = True
    game_watcher_enabled: bool = True
    last_virtual_mode: str = "nativo"
    last_profile_name: str = ""
    touchpad_mouse_enabled: bool = False
    touchpad_sensitivity: float = 0.45
    gyro_mouse_enabled: bool = False
    gyro_only_when_l2: bool = True
    gyro_activation: str = "l2"
    gyro_horizontal_axis: str = "yaw"
    gyro_deadzone: int = 45
    gyro_smoothing: float = 0.35
    gyro_sensitivity: float = 0.008
    macros_enabled: bool = True
    macros: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MACROS))
    speaker_volume: int = 80
    headphone_volume: int = 100
    mic_volume: int = 80
    speaker_enabled: bool = True
    sync_windows_mute: bool = True
    rumble_to_triggers: bool = False
    rumble_to_triggers_strength: float = 1.0
    ds4_led_passthrough: bool = True


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return AppSettings()
            valid = {k: v for k, v in raw.items() if k in AppSettings.__dataclass_fields__}
            cfg = AppSettings(**valid)
            if not isinstance(cfg.macros, dict) or not cfg.macros:
                cfg.macros = dict(DEFAULT_MACROS)
            return cfg
        except (OSError, json.JSONDecodeError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(asdict(settings), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
