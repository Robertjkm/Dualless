from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from dualcontrol import constants
from dualcontrol.app_context import AppContext
from dualcontrol.ui.pages.edit_controller_page import EditControllerPage
from dualcontrol.ui.pages.home_page import HomePage
from dualcontrol.ui.pages.mods_page import ModsPage
from dualcontrol.ui.pages.profiles_page import ProfilesPage
from dualcontrol.ui.pages.settings_page import SettingsPage
from dualcontrol.virtualcontroller.base import VirtualControllerMode

_NAV_ITEMS = [
    ("Home", "  Home", "nav_home.png", HomePage),
    ("Edit Controller", "  Edit Controller", "nav_controller.png", EditControllerPage),
    ("Profiles", "  Profiles", "nav_profiles.png", ProfilesPage),
    ("Mods", "  Mods", "nav_mods.png", ModsPage),
    ("Settings", "  Settings", "nav_settings.png", SettingsPage),
]


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "dualcontrol" / "ui" / "assets"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent / "assets"


class MainWindow(QMainWindow):
    def __init__(self, profiles_dir: Path) -> None:
        super().__init__()
        self.setWindowTitle(f"{constants.APP_NAME} — v1.4.0")
        logo_path = _assets_dir() / "app_logo.png"
        self._app_icon = QIcon(str(logo_path)) if logo_path.exists() else QIcon()
        if not self._app_icon.isNull():
            self.setWindowIcon(self._app_icon)
        self.resize(1240, 780)

        self.ctx = AppContext(profiles_dir)
        self._nav_index: Dict[str, int] = {}
        self._force_quit = False
        self._low_battery_notified = False
        self._tray: QSystemTrayIcon | None = None

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 18, 12, 16)
        side_layout.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 6, 14)
        brand_row.setSpacing(10)
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(34, 34)
        if logo_path.exists():
            pm = QPixmap(str(logo_path)).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_lbl.setPixmap(pm)
        brand = QLabel(constants.APP_NAME)
        brand.setStyleSheet("font-size: 19px; font-weight: 800; color: white;")
        brand_row.addWidget(logo_lbl)
        brand_row.addWidget(brand, 1)
        side_layout.addLayout(brand_row)

        self.stack = QStackedWidget()
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        assets = _assets_dir()
        for index, (key, label, icon_file, page_cls) in enumerate(_NAV_ITEMS):
            page = self._build_page(page_cls)
            self.stack.addWidget(page)
            self._nav_index[key] = index

            if isinstance(page, HomePage):
                page.navigate_requested.connect(self.navigate_to)

            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            icon_path = assets / icon_file
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(19, 19))
            btn.clicked.connect(lambda _checked, i=index: self.stack.setCurrentIndex(i))
            self.nav_group.addButton(btn, index)
            side_layout.addWidget(btn)

        self.nav_group.button(0).setChecked(True)
        side_layout.addStretch(1)

        ver_footer = QLabel("v1.4.0")
        ver_footer.setAlignment(Qt.AlignCenter)
        ver_footer.setStyleSheet(
            "color: #A78BFA; background-color: #211C30; border: 1px solid #352D4D; "
            "border-radius: 6px; padding: 3px 8px; font-size: 11px; font-weight: 700;"
        )
        side_layout.addWidget(ver_footer)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self._setup_system_tray()
        self.ctx.controller_service.state_changed.connect(self._check_low_battery)
        self.ctx.game_watcher.profile_auto_switched.connect(self._on_profile_auto_switched)
        self.ctx.start_auto_detect()

    def _setup_system_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self._app_icon, self)
        tray.setToolTip(f"{constants.APP_NAME} — DualSense Controller Manager")

        menu = QMenu(self)
        act_open = QAction(f"Abrir {constants.APP_NAME}", self)
        act_open.triggered.connect(self._restore_from_tray)
        menu.addAction(act_open)

        mode_menu = menu.addMenu("Virtual Device")
        for label, mode in (
            ("Native Mode", VirtualControllerMode.NATIVE),
            ("Xbox 360 Emulation", VirtualControllerMode.XINPUT),
            ("DualShock 4 Emulation", VirtualControllerMode.DUALSHOCK4),
        ):
            act_m = QAction(label, self)
            act_m.triggered.connect(lambda _c=False, m=mode: self.ctx.virtual_controller_service.set_mode(m))
            mode_menu.addAction(act_m)

        act_reset = QAction("Restaurar valores por defecto", self)
        act_reset.triggered.connect(self.ctx.controller_service.restore_defaults)
        menu.addAction(act_reset)
        menu.addSeparator()

        act_quit = QAction("Salir completamente", self)
        act_quit.triggered.connect(self._quit_from_tray)
        menu.addAction(act_quit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray = tray

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._force_quit = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _check_low_battery(self, state) -> None:
        if not self.ctx.low_battery_alerts or not self.ctx.using_real_backend:
            return
        lvl = int(state.battery_level)
        charging = bool(state.battery_charging)
        if charging or lvl > 20:
            self._low_battery_notified = False
            return
        if 0 < lvl <= 15 and not self._low_battery_notified:
            self._low_battery_notified = True
            if self._tray is not None:
                self._tray.showMessage(
                    f"{constants.APP_NAME} — Batería baja",
                    f"Tu DualSense está al {lvl}%. Conéctalo por USB para cargarlo.",
                    QSystemTrayIcon.Warning,
                    5000,
                )

    def _on_profile_auto_switched(self, profile_name: str, process_name: str) -> None:
        if self._tray is not None:
            self._tray.showMessage(
                f"{constants.APP_NAME} — Perfil automático",
                f"Perfil '{profile_name}' activado para {process_name}.",
                QSystemTrayIcon.Information,
                3000,
            )

    def navigate_to(self, section: str, sub_tab: str = "") -> None:
        idx = self._nav_index.get(section)
        if idx is None:
            return
        self.stack.setCurrentIndex(idx)
        btn = self.nav_group.button(idx)
        if btn is not None:
            btn.setChecked(True)
        if section == "Edit Controller" and sub_tab:
            edit_page = self.stack.widget(idx)
            if isinstance(edit_page, EditControllerPage) and sub_tab in edit_page.pages:
                sub_idx = list(edit_page.pages.keys()).index(sub_tab)
                edit_page.select_tab(sub_idx)

    def _build_page(self, page_cls) -> QWidget:
        return page_cls(self.ctx)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._force_quit and self.ctx.minimize_to_tray and self._tray is not None and self._tray.isVisible():
            event.ignore()
            self.hide()
            self._tray.showMessage(
                constants.APP_NAME,
                "Dualless sigue activo en segundo plano. Haz clic derecho en el icono para salir.",
                QSystemTrayIcon.Information,
                2500,
            )
            return
        if self._tray is not None:
            self._tray.hide()
        self.ctx.shutdown()
        super().closeEvent(event)
