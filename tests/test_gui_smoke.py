"""Prueba de humo de la interfaz gráfica completa, sin pantalla real (QT_QPA_PLATFORM
=offscreen, fijado en conftest.py). No sustituye a probar la app con un monitor y un
mando físico delante, pero sí garantiza que el menú principal y las sub-pestañas de
Edit Controller se construyen sin excepciones."""

import pytest

PySide6 = pytest.importorskip("PySide6", reason="PySide6 no instalado")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dualcontrol.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_builds_all_pages(qapp, tmp_path):
    window = MainWindow(tmp_path / "profiles")
    assert window.stack.count() == 5
    edit_page = window.stack.widget(1)
    assert edit_page.sub_stack.count() == 6


def test_simulated_backend_feeds_controller_page(qapp, tmp_path):
    window = MainWindow(tmp_path / "profiles")
    from dualcontrol.models import ControllerState

    edit_page = window.stack.widget(1)
    controller_page = edit_page.pages["Controller Mappings"]
    fake_state = ControllerState(cross=True, l2_value=123)
    window.ctx.controller_service.backend.inject_state(fake_state)
    window.ctx.controller_service._poll()

    assert "✕" in controller_page.buttons_label.text()


def test_trigger_preset_button_updates_sliders(qapp, tmp_path):
    window = MainWindow(tmp_path / "profiles")
    edit_page = window.stack.widget(1)
    triggers_page = edit_page.pages["Adaptive Triggers"]
    triggers_page.l2_editor._apply_preset("weapon")
    assert triggers_page.l2_editor.sliders[1].value() > 0
