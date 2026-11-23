from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.services.mod_portal import ModEntry
from dualcontrol.ui.widgets import Card

_TYPE_LABELS = {
    "dsx_udp": "DSX / UDP (tiempo real)",
    "hid_direct": "HID directo (USB)",
    "unknown": "Genérico",
}


class ModDropZone(QFrame):
    """Zona de arrastrar y soltar archivos (.zip, .rar, .asi) o carpetas de mods."""

    path_dropped = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(74)
        self._set_idle_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel("Arrastra y suelta aquí tu mod (.zip, .rar, .asi o carpeta descomprimida)")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #AEB4C2; font-weight: 600; border: none;")
        layout.addWidget(lbl)

    def _set_idle_style(self) -> None:
        self.setStyleSheet(
            "QFrame { background-color: #181B22; border: 2px dashed #2E6BFF; border-radius: 10px; }"
        )

    def _set_hover_style(self) -> None:
        self.setStyleSheet(
            "QFrame { background-color: #1F2638; border: 2px dashed #5C92FF; border-radius: 10px; }"
        )

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover_style()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_idle_style()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_idle_style()
        urls = event.mimeData().urls()
        if not urls:
            return
        local_path = urls[0].toLocalFile()
        if local_path:
            self.path_dropped.emit(local_path)


class ModsPage(QWidget):
    """Sección Mods: Servidor UDP estilo DSX en tiempo real + Portal de Mods."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Mods — Servidor UDP (DSX) y Portal")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Activa el servidor UDP para que mods como DSX.asi controlen tus gatillos adaptativos "
            "e iluminación en tiempo real directamente desde Dualless."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        # --- Tarjeta 1: Servidor UDP (protocolo DSX) -----------------------------
        udp_card = Card("Servidor UDP (compatible con DSX.asi y mods UDP)")

        status_row = QHBoxLayout()
        self.udp_dot = QLabel("●")
        self.udp_dot.setStyleSheet("color: #FF5C7A; font-size: 16px;")
        self.udp_status_label = QLabel("Detenido")
        self.packet_counter_label = QLabel("Paquetes recibidos: 0")
        self.packet_counter_label.setObjectName("pageSubtitle")
        status_row.addWidget(self.udp_dot)
        status_row.addWidget(self.udp_status_label)
        status_row.addStretch(1)
        status_row.addWidget(self.packet_counter_label)
        udp_card.add_layout(status_row)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Puerto UDP:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(6969)
        self.port_spin.setFixedWidth(96)
        ctrl_row.addWidget(self.port_spin)

        self.toggle_udp_btn = QPushButton("Iniciar servidor UDP")
        self.toggle_udp_btn.setObjectName("primary")
        self.toggle_udp_btn.clicked.connect(self._toggle_udp)
        ctrl_row.addWidget(self.toggle_udp_btn)

        self.test_udp_btn = QPushButton("Probar paquete UDP (Arma R2)")
        self.test_udp_btn.setObjectName("secondary")
        self.test_udp_btn.setEnabled(False)
        self.test_udp_btn.clicked.connect(self._send_test_udp)
        ctrl_row.addWidget(self.test_udp_btn)

        clear_btn = QPushButton("Limpiar registro")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(lambda: self.udp_log.clear())
        ctrl_row.addWidget(clear_btn)
        ctrl_row.addStretch(1)
        udp_card.add_layout(ctrl_row)

        self.udp_log = QPlainTextEdit()
        self.udp_log.setObjectName("hexDump")
        self.udp_log.setReadOnly(True)
        self.udp_log.setMaximumHeight(135)
        self.udp_log.setPlaceholderText(
            "Aquí aparecerán en vivo los comandos que envíe DSX.asi (gatillos L2/R2, RGB, LEDs)..."
        )
        udp_card.add(self.udp_log)
        root.addWidget(udp_card)

        # --- Tarjeta 2: Portal de Mods (arrastrar y soltar) ----------------------
        portal_card = Card("Portal de Mods (importación y creación automática de perfil)")

        self.drop_zone = ModDropZone()
        self.drop_zone.path_dropped.connect(self._import_mod_path)
        portal_card.add(self.drop_zone)

        btn_row = QHBoxLayout()
        add_file_btn = QPushButton("Agregar archivo (.zip / .rar / .asi)")
        add_file_btn.setObjectName("secondary")
        add_file_btn.clicked.connect(self._browse_mod_file)
        add_dir_btn = QPushButton("Agregar carpeta de mod")
        add_dir_btn.setObjectName("secondary")
        add_dir_btn.clicked.connect(self._browse_mod_folder)
        btn_row.addWidget(add_file_btn)
        btn_row.addWidget(add_dir_btn)
        btn_row.addStretch(1)
        portal_card.add_layout(btn_row)

        self.mods_list = QListWidget()
        self.mods_list.setMinimumHeight(110)
        self.mods_list.currentItemChanged.connect(self._on_mod_selected)
        portal_card.add(self.mods_list)

        self.mod_detail_label = QLabel("Selecciona o arrastra un mod para ver sus detalles.")
        self.mod_detail_label.setObjectName("pageSubtitle")
        self.mod_detail_label.setWordWrap(True)
        portal_card.add(self.mod_detail_label)

        action_row = QHBoxLayout()
        self.activate_mod_btn = QPushButton("Activar perfil y servidor UDP")
        self.activate_mod_btn.setObjectName("primary")
        self.activate_mod_btn.clicked.connect(self._activate_selected_mod)
        self.remove_mod_btn = QPushButton("Quitar de la lista")
        self.remove_mod_btn.setObjectName("secondary")
        self.remove_mod_btn.clicked.connect(self._remove_selected_mod)
        action_row.addWidget(self.activate_mod_btn)
        action_row.addWidget(self.remove_mod_btn)
        action_row.addStretch(1)
        portal_card.add_layout(action_row)

        root.addWidget(portal_card, 1)

        # Conectar señales del servidor UDP
        if self.ctx.udp_server is not None:
            self.ctx.udp_server.status_changed.connect(self._on_udp_status)
            self.ctx.udp_server.packet_logged.connect(self._append_log)
            self.ctx.udp_server.packet_count_changed.connect(
                lambda n: self.packet_counter_label.setText(f"Paquetes recibidos: {n}")
            )
            self.ctx.udp_server.error_occurred.connect(
                lambda msg: self._append_log(f"[ERROR] {msg}")
            )

        self._refresh_mods_list()

    # --- acciones UDP ----------------------------------------------------------
    def _toggle_udp(self) -> None:
        server = self.ctx.udp_server
        if server is None:
            return
        if server.is_running:
            server.stop()
        else:
            server.start(port=self.port_spin.value())

    def _on_udp_status(self, running: bool, message: str) -> None:
        color = "#35D07F" if running else "#FF5C7A"
        self.udp_dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        self.udp_status_label.setText(message)
        self.toggle_udp_btn.setText("Detener servidor UDP" if running else "Iniciar servidor UDP")
        self.port_spin.setEnabled(not running)
        self.test_udp_btn.setEnabled(running)

    def _send_test_udp(self) -> None:
        if self.ctx.udp_server is not None:
            self.ctx.udp_server.send_self_test("R2")

    def _append_log(self, line: str) -> None:
        self.udp_log.appendPlainText(line)

    # --- acciones Portal de Mods -----------------------------------------------
    def _browse_mod_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar mod de juego",
            "",
            "Mods (*.zip *.rar *.asi);;Todos los archivos (*.*)",
        )
        if file_path:
            self._import_mod_path(file_path)

    def _browse_mod_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta del mod")
        if folder:
            self._import_mod_path(folder)

    def _import_mod_path(self, raw_path: str) -> None:
        entry = self.ctx.mod_portal.import_mod(Path(raw_path))
        self._refresh_mods_list(select_name=entry.name)
        QMessageBox.information(
            self,
            "Mod importado",
            f"Mod registrado: {entry.name}\n"
            f"Tipo detectado: {_TYPE_LABELS.get(entry.mod_type, entry.mod_type)}\n"
            f"Perfil creado automáticamente: {entry.profile_name}\n\n"
            f"{entry.notes}",
        )

    def _refresh_mods_list(self, select_name: str | None = None) -> None:
        self.mods_list.clear()
        mods = self.ctx.mod_portal.list_mods()
        target_row = -1
        for i, entry in enumerate(mods):
            badge = _TYPE_LABELS.get(entry.mod_type, entry.mod_type)
            item = QListWidgetItem(f"{entry.name}  —  [{badge}]  (Puerto UDP {entry.udp_port})")
            item.setData(Qt.UserRole, entry)
            self.mods_list.addItem(item)
            if select_name and entry.name == select_name:
                target_row = i
        if target_row >= 0:
            self.mods_list.setCurrentRow(target_row)
        elif self.mods_list.count() > 0:
            self.mods_list.setCurrentRow(0)
        else:
            self.mod_detail_label.setText("Todavía no hay mods agregados. Arrastra un .zip, .rar o carpeta arriba.")

    def _current_mod(self) -> ModEntry | None:
        item = self.mods_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_mod_selected(self, current, _previous) -> None:
        if current is None:
            return
        entry: ModEntry = current.data(Qt.UserRole)
        self.mod_detail_label.setText(
            f"Perfil: {entry.profile_name} · Origen: {entry.source_path}\n{entry.notes}"
        )

    def _activate_selected_mod(self) -> None:
        entry = self._current_mod()
        if entry is None:
            return
        try:
            profile = self.ctx.profile_manager.load(entry.profile_name)
            self.ctx.apply_profile(profile)
        except Exception:
            pass

        if entry.mod_type == "dsx_udp" and self.ctx.udp_server is not None:
            self.port_spin.setValue(entry.udp_port)
            self.ctx.udp_server.start(port=entry.udp_port)
        elif entry.mod_type == "hid_direct":
            QMessageBox.information(
                self,
                "Mod HID directo",
                "Este mod se comunica directo con el DualSense por USB. "
                "Desconecta el mando en Dashboard antes de abrir el juego para evitar conflictos.",
            )

    def _remove_selected_mod(self) -> None:
        entry = self._current_mod()
        if entry is None:
            return
        self.ctx.mod_portal.remove_mod(entry.name)
        self._refresh_mods_list()
