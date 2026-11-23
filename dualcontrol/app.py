from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from dualcontrol import constants
from dualcontrol.ui.main_window import MainWindow
from dualcontrol.ui.theme import DARK_QSS


def _default_profiles_dir() -> Path:
    # Junto al ejecutable/código, NO dentro de él, para sobrevivir a actualizaciones
    # (sección 11: "las actualizaciones de la aplicación no deben destruir los
    # perfiles del usuario").
    base = Path(sys.argv[0]).resolve().parent
    return base / constants.PROFILES_DIR_NAME


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(constants.APP_NAME)
    app.setStyleSheet(DARK_QSS)

    window = MainWindow(_default_profiles_dir())
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
