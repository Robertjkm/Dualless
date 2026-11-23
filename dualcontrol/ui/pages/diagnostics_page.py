from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from dualcontrol.app_context import AppContext
from dualcontrol.models import ConnectionState
from dualcontrol.services.diagnostics import acceptance_checklist, hex_dump
from dualcontrol.ui.widgets import Card


class DiagnosticsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Diagnostics")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        state_card = Card("Estado de la conexión (sección 12)")
        self.state_label = QLabel("—")
        state_card.add(self.state_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #FF5C7A;")
        self.error_label.hide()
        state_card.add(self.error_label)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Re-detectar y conectar")
        refresh_btn.setObjectName("secondary")
        refresh_btn.clicked.connect(self._redetect)

        trig_test_btn = QPushButton("Probar gatillos físicos (L2/R2)")
        trig_test_btn.setObjectName("primary")
        trig_test_btn.clicked.connect(self._test_triggers)

        reconn_test_btn = QPushButton("Probar recuperación de desconexión")
        reconn_test_btn.setObjectName("secondary")
        reconn_test_btn.clicked.connect(self._test_reconnection)

        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(trig_test_btn)
        btn_row.addWidget(reconn_test_btn)
        btn_row.addStretch(1)
        state_card.add_layout(btn_row)
        root.addWidget(state_card)

        checklist_card = Card("Criterios de aceptación (sección 19) — honestos, no decorativos")
        self.checklist_label = QLabel()
        self.checklist_label.setWordWrap(True)
        self.checklist_label.setTextFormat(Qt.RichText)
        checklist_card.add(self.checklist_label)
        root.addWidget(checklist_card)

        report_card = Card("Último informe HID de salida enviado")
        self.report_view = QPlainTextEdit()
        self.report_view.setObjectName("hexDump")
        self.report_view.setReadOnly(True)
        report_card.add(self.report_view)
        root.addWidget(report_card)

        self.ctx.active_connection_changed.connect(self._refresh)
        self.ctx.active_state_changed.connect(lambda _s: self._refresh())
        self.ctx.slot_changed.connect(lambda _a, _t: self._refresh())
        self.ctx.controller_service.error_occurred.connect(self._on_error)
        self.ctx.diagnostics_updated.connect(self._refresh)
        self._refresh()

    def _redetect(self) -> None:
        self.error_label.hide()
        self.ctx.try_auto_connect_real()
        self._refresh()

    def _test_triggers(self) -> None:
        ok = self.ctx.test_physical_triggers_pulse()
        self._refresh()
        if ok:
            QMessageBox.information(
                self,
                "Prueba de gatillos físicos",
                "Se aplicó el efecto Weapon a L2 y R2 en tu DualSense. "
                "Presiona ambos gatillos para sentir el tope mecánico.",
            )
        else:
            QMessageBox.warning(
                self,
                "Sin DualSense físico activo",
                "Conecta tu DualSense por USB o Bluetooth (modo Real) para confirmar los efectos físicos.",
            )

    def _test_reconnection(self) -> None:
        ok = self.ctx.test_reconnection_recovery()
        self._refresh()
        if ok:
            QMessageBox.information(
                self,
                "Recuperación verificada",
                "Dualless cerró y reconectó el mando limpiamente restaurando gatillos, hápticos e iluminación.",
            )

    def _on_error(self, message: str) -> None:
        self.error_label.setText(f"Error: {message}")
        self.error_label.show()

    def _refresh(self, *_args) -> None:
        state: ConnectionState = self.ctx.controller_service.backend.connection_state
        self.state_label.setText(f"Estado actual: <b>{state.value}</b>")

        if state in (ConnectionState.OPENED, ConnectionState.INPUT_OK, ConnectionState.OUTPUT_OK):
            self.error_label.hide()
        elif self.ctx.controller_service.last_error:
            self.error_label.setText(f"Error: {self.ctx.controller_service.last_error}")
            self.error_label.show()

        items = acceptance_checklist(
            using_real_backend=self.ctx.using_real_backend,
            connection_state=state,
            physical_triggers_tested=self.ctx.physical_triggers_tested,
            auto_reconnect_enabled=self.ctx.auto_detect_enabled,
            reconnection_verified=self.ctx.reconnection_verified,
        )
        html_lines = []
        for item in items:
            mark = "✅" if item.verified else "⬜"
            html_lines.append(f"{mark} {item.description}<span style='color:#9CA0BA;'>{item.note}</span>")
        self.checklist_label.setText("<br>".join(html_lines))

        self.report_view.setPlainText(hex_dump(self.ctx.controller_service.last_output_report()))
