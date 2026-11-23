from pathlib import Path

from dualcontrol.app_context import AppContext
from dualcontrol.models import Profile
from dualcontrol.services.game_watcher import GameProfileWatcher
from dualcontrol.services.profile_manager import ProfileManager


def test_game_watcher_loads_profiles_from_manager(tmp_path: Path):
    mgr = ProfileManager(tmp_path / "profiles")
    mgr.save(Profile(name="Dead Space", game="Dead Space.exe"))
    applied = []
    watcher = GameProfileWatcher(
        mgr,
        apply_profile_cb=lambda p: applied.append(p.name),
        process_getter=lambda: "Dead Space.exe",
    )
    matched = watcher.check_once()
    assert matched == "Dead Space"
    assert applied == ["Dead Space"]


def test_app_context_cycle_next_profile_and_restore(tmp_path: Path):
    ctx = AppContext(tmp_path / "profiles")
    ctx.profile_manager.save(Profile(name="Alpha", game="alpha.exe"))
    ctx.profile_manager.save(Profile(name="Beta", game="beta.exe"))
    ctx.cycle_next_profile()
    assert ctx.current_profile_name == "Alpha"
    ctx.cycle_next_profile()
    assert ctx.current_profile_name == "Beta"
    ctx.shutdown()

    ctx2 = AppContext(tmp_path / "profiles")
    ctx2.restore_saved_session()
    assert ctx2.current_profile_name == "Beta"
    ctx2.shutdown()
