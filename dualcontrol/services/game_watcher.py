"""Detector automático de perfil por juego activo en Windows (v0.8.0)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from dualcontrol.models import Profile
from dualcontrol.services.windows_integration import get_foreground_process_name


def match_profile_for_process(process_name: str, profiles: list[Profile]) -> Optional[Profile]:
    """Busca un perfil cuyo campo ``game`` coincida con el ejecutable activo."""
    proc = (process_name or "").strip().lower()
    if not proc:
        return None
    proc_stem = proc[:-4] if proc.endswith(".exe") else proc
    for prof in profiles:
        game_tag = (prof.game or "").strip().lower()
        if not game_tag:
            continue
        tag_stem = game_tag[:-4] if game_tag.endswith(".exe") else game_tag
        if game_tag == proc or tag_stem == proc_stem or (len(tag_stem) >= 3 and tag_stem in proc_stem):
            return prof
    return None


class GameProfileWatcher(QObject):
    profile_auto_switched = Signal(str, str)  # profile_name, process_name

    POLL_INTERVAL_MS = 2500

    def __init__(
        self,
        profile_manager,
        apply_profile_cb: Callable[[Profile], None],
        process_getter: Callable[[], str] = get_foreground_process_name,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._profile_manager = profile_manager
        self._apply_profile_cb = apply_profile_cb
        self._process_getter = process_getter
        self._enabled = True
        self._active_game_profile: Optional[str] = None
        self._fallback_profile: Optional[Profile] = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_once)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if self._enabled:
            if not self._timer.isActive():
                self._timer.start(self.POLL_INTERVAL_MS)
        else:
            self._timer.stop()

    def start(self) -> None:
        if self._enabled and not self._timer.isActive():
            self._timer.start(self.POLL_INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()

    def set_fallback_profile(self, profile: Profile) -> None:
        self._fallback_profile = profile

    def check_once(self) -> Optional[str]:
        if not self._enabled:
            return None
        proc = self._process_getter()
        if not proc:
            return None
        try:
            raw_list = self._profile_manager.list_profiles()
            profiles = [
                self._profile_manager.load(item) if isinstance(item, str) else item
                for item in raw_list
            ]
        except Exception:
            return None

        matched = match_profile_for_process(proc, profiles)
        if matched is not None:
            if self._active_game_profile != matched.name:
                self._active_game_profile = matched.name
                self._apply_profile_cb(matched)
                self.profile_auto_switched.emit(matched.name, proc)
            return matched.name

        # Si salimos del juego y tenemos perfil previo/default, restaurarlo
        if self._active_game_profile is not None:
            self._active_game_profile = None
            if self._fallback_profile is not None:
                self._apply_profile_cb(self._fallback_profile)
                self.profile_auto_switched.emit(self._fallback_profile.name, "Desktop")
        return None
