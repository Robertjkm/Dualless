import pytest

from dualcontrol.models import LightingSettings, Profile, TriggerMode, TriggerSettings
from dualcontrol.services.profile_manager import ProfileError, ProfileManager


@pytest.fixture
def manager(tmp_path):
    return ProfileManager(tmp_path / "profiles")


def _sample_profile(name="Shooter"):
    return Profile(
        name=name,
        game="Returnal",
        trigger_l2=TriggerSettings(enabled=True, mode=TriggerMode.PULSE, forces=[2, 255, 0, 0, 0, 0, 0]),
        lighting=LightingSettings(red=255, green=0, blue=0),
    )


def test_save_and_load_roundtrip(manager):
    profile = _sample_profile()
    manager.save(profile)

    loaded = manager.load("Shooter")
    assert loaded.name == "Shooter"
    assert loaded.game == "Returnal"
    assert loaded.trigger_l2.mode == TriggerMode.PULSE
    assert loaded.trigger_l2.forces[1] == 255
    assert loaded.lighting.red == 255


def test_list_profiles(manager):
    manager.save(_sample_profile("A"))
    manager.save(_sample_profile("B"))
    assert manager.list_profiles() == ["A", "B"]


def test_duplicate_profile(manager):
    manager.save(_sample_profile("Original"))
    manager.duplicate("Original", "Copia")
    assert set(manager.list_profiles()) == {"Original", "Copia"}
    copy = manager.load("Copia")
    assert copy.game == "Returnal"


def test_delete_profile(manager):
    manager.save(_sample_profile("Temporal"))
    manager.delete("Temporal")
    assert manager.list_profiles() == []


def test_load_missing_profile_raises(manager):
    with pytest.raises(ProfileError):
        manager.load("NoExiste")


def test_export_and_import_roundtrip(manager, tmp_path):
    manager.save(_sample_profile("Exportable"))
    export_path = tmp_path / "exported.json"
    manager.export_to("Exportable", export_path)
    assert export_path.exists()

    manager.delete("Exportable")
    assert manager.list_profiles() == []

    manager.import_from(export_path)
    assert manager.list_profiles() == ["Exportable"]


def test_profiles_survive_in_their_own_directory(tmp_path):
    """Sección 11: las actualizaciones de la app no deben destruir los perfiles.
    Lo comprobamos indirectamente: los perfiles no viven dentro del paquete de
    código, sino en un directorio independiente que el usuario controla."""
    profiles_dir = tmp_path / "profiles"
    manager = ProfileManager(profiles_dir)
    manager.save(_sample_profile())

    # Un "update" simulado: se crea un ProfileManager nuevo (como si fuera otra
    # versión de la app) apuntando al mismo directorio de perfiles.
    manager2 = ProfileManager(profiles_dir)
    assert manager2.list_profiles() == ["Shooter"]
