from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.ui.pages.compatibility_page import CompatibilityPage
from dualcontrol.ui.pages.controller_mappings_page import ControllerMappingsPage
from dualcontrol.ui.pages.diagnostics_page import DiagnosticsPage
from dualcontrol.ui.pages.haptics_page import HapticsPage
from dualcontrol.ui.pages.lighting_page import LightingPage
from dualcontrol.ui.pages.triggers_page import TriggersPage

_SUB_TABS = [
    ("Controller Mappings", ControllerMappingsPage),
    ("Adaptive Triggers", TriggersPage),
    ("Haptic Feedback", HapticsPage),
    ("Lighting", LightingPage),
    ("Game Compatibility", CompatibilityPage),
    ("Diagnostics", DiagnosticsPage),
]


class EditControllerPage(QWidget):
    """Agrupa todas las herramientas de edición, monitoreo, compatibilidad y
    diagnóstico del mando bajo una sola entrada del menú lateral."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.pages: Dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sub_bar = QWidget()
        sub_bar.setObjectName("subNavBar")
        bar_layout = QVBoxLayout(sub_bar)
        bar_layout.setContentsMargins(24, 14, 24, 12)
        bar_layout.setSpacing(10)

        header = QLabel("Edit Controller")
        header.setObjectName("pageTitle")
        bar_layout.addWidget(header)

        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(6)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.sub_stack = QStackedWidget()

        for index, (label, page_cls) in enumerate(_SUB_TABS):
            page = page_cls(self.ctx)
            self.sub_stack.addWidget(page)
            self.pages[label] = page

            btn = QPushButton(label)
            btn.setObjectName("subNavButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, i=index: self.sub_stack.setCurrentIndex(i))
            self.tab_group.addButton(btn, index)
            tabs_row.addWidget(btn)

        tabs_row.addStretch(1)
        bar_layout.addLayout(tabs_row)

        self.tab_group.button(0).setChecked(True)

        root.addWidget(sub_bar)
        root.addWidget(self.sub_stack, 1)

    def select_tab(self, index: int) -> None:
        if 0 <= index < self.sub_stack.count():
            self.sub_stack.setCurrentIndex(index)
            btn = self.tab_group.button(index)
            if btn is not None:
                btn.setChecked(True)
