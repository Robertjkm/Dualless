from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.services.profile_manager import ProfileError
from dualcontrol.ui.widgets import Card


class ProfilesPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Profiles")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        card = Card("Perfiles guardados")
        self.list_widget = QListWidget()
        card.add(self.list_widget)

        form_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nombre del perfil")
        self.game_edit = QLineEdit()
        self.game_edit.setPlaceholderText("Juego (opcional)")
        form_row.addWidget(self.name_edit)
        form_row.addWidget(self.game_edit)
        card.add_layout(form_row)

        btn_row1 = QHBoxLayout()
        save_btn = QPushButton("Guardar actual como…")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_current)
        load_btn = QPushButton("Cargar seleccionado")
        load_btn.setObjectName("secondary")
        load_btn.clicked.connect(self._load_selected)
        btn_row1.addWidget(save_btn)
        btn_row1.addWidget(load_btn)
        card.add_layout(btn_row1)

        btn_row2 = QHBoxLayout()
        dup_btn = QPushButton("Duplicar")
        dup_btn.setObjectName("secondary")
        dup_btn.clicked.connect(self._duplicate_selected)
        del_btn = QPushButton("Eliminar")
        del_btn.setObjectName("secondary")
        del_btn.clicked.connect(self._delete_selected)
        export_btn = QPushButton("Exportar…")
        export_btn.setObjectName("secondary")
        export_btn.clicked.connect(self._export_selected)
        import_btn = QPushButton("Importar…")
        import_btn.setObjectName("secondary")
        import_btn.clicked.connect(self._import)
        for b in (dup_btn, del_btn, export_btn, import_btn):
            btn_row2.addWidget(b)
        card.add_layout(btn_row2)

        root.addWidget(card)
        root.addStretch(1)

        self._refresh_list()

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        self.list_widget.addItems(self.ctx.profile_manager.list_profiles())

    def _selected_name(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.text() if item else None

    def _save_current(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Falta el nombre", "Escribe un nombre para el perfil.")
            return
        profile = self.ctx.build_profile(name, self.game_edit.text().strip())
        try:
            self.ctx.profile_manager.save(profile)
        except ProfileError as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))
            return
        self._refresh_list()

    def _load_selected(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            profile = self.ctx.profile_manager.load(name)
        except ProfileError as exc:
            QMessageBox.critical(self, "Error al cargar", str(exc))
            return
        self.ctx.apply_profile(profile)
        self.name_edit.setText(profile.name)
        self.game_edit.setText(profile.game or "")

    def _duplicate_selected(self) -> None:
        name = self._selected_name()
        if not name:
            return
        new_name, ok = self._ask_name(f"{name} (copia)")
        if not ok:
            return
        try:
            self.ctx.profile_manager.duplicate(name, new_name)
        except ProfileError as exc:
            QMessageBox.critical(self, "Error al duplicar", str(exc))
            return
        self._refresh_list()

    def _delete_selected(self) -> None:
        name = self._selected_name()
        if not name:
            return
        confirm = QMessageBox.question(self, "Eliminar perfil", f"¿Eliminar '{name}'?")
        if confirm != QMessageBox.Yes:
            return
        try:
            self.ctx.profile_manager.delete(name)
        except ProfileError as exc:
            QMessageBox.critical(self, "Error al eliminar", str(exc))
            return
        self._refresh_list()

    def _export_selected(self) -> None:
        name = self._selected_name()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar perfil", f"{name}.json", "JSON (*.json)")
        if not path:
            return
        self.ctx.profile_manager.export_to(name, path)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar perfil", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.ctx.profile_manager.import_from(path)
        except ProfileError as exc:
            QMessageBox.critical(self, "Error al importar", str(exc))
            return
        self._refresh_list()

    def _ask_name(self, default: str) -> tuple[str, bool]:
        from PySide6.QtWidgets import QInputDialog

        return QInputDialog.getText(self, "Nuevo nombre", "Nombre del perfil:", text=default)
