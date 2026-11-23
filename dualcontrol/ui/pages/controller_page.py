from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from dualcontrol.app_context import AppContext
from dualcontrol.ui.widgets import Card, StickVisualizer, TriggerBar


class ControllerPage(QWidget):
    """Monitor de entradas en tiempo real (sección 8)."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Controller — Monitor de entradas")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(16)
        root.addLayout(grid)

        sticks_card = Card("Sticks analógicos")
        sticks_row = QHBoxLayout()
        self.left_stick_view = StickVisualizer()
        self.right_stick_view = StickVisualizer()
        for label, view in (("Izquierdo (L3)", self.left_stick_view), ("Derecho (R3)", self.right_stick_view)):
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            col.addWidget(view)
            sticks_row.addLayout(col)
        sticks_card.add_layout(sticks_row)
        grid.addWidget(sticks_card, 0, 0)

        triggers_card = Card("Gatillos analógicos")
        trig_row = QHBoxLayout()
        self.l2_bar = TriggerBar()
        self.r2_bar = TriggerBar()
        for label, bar in (("L2", self.l2_bar), ("R2", self.r2_bar)):
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            col.addWidget(bar)
            trig_row.addLayout(col)
        triggers_card.add_layout(trig_row)
        grid.addWidget(triggers_card, 0, 1)

        buttons_card = Card("Botones")
        self.buttons_label = QLabel("—")
        self.buttons_label.setWordWrap(True)
        buttons_card.add(self.buttons_label)
        grid.addWidget(buttons_card, 1, 0)

        sensors_card = Card("Giroscopio / Acelerómetro / Panel táctil")
        self.sensors_label = QLabel("—")
        self.sensors_label.setWordWrap(True)
        sensors_card.add(self.sensors_label)
        grid.addWidget(sensors_card, 1, 1)

        root.addStretch(1)

        self.ctx.active_state_changed.connect(self._on_state_changed)

    def _on_state_changed(self, state) -> None:
        self.left_stick_view.set_position(state.left_stick.x, state.left_stick.y, state.l3)
        self.right_stick_view.set_position(state.right_stick.x, state.right_stick.y, state.r3)
        self.l2_bar.set_value(state.l2_value)
        self.r2_bar.set_value(state.r2_value)

        pressed = [
            name for name, val in (
                ("□", state.square), ("✕", state.cross), ("○", state.circle), ("△", state.triangle),
                ("L1", state.l1), ("R1", state.r1), ("L2", state.l2_button), ("R2", state.r2_button),
                ("L3", state.l3), ("R3", state.r3), ("Create", state.create), ("Options", state.options),
                ("PS", state.ps), ("Touchpad", state.touchpad_button), ("Mute", state.mute),
                ("Edge FN-L", state.fn_left), ("Edge FN-R", state.fn_right),
                ("Edge Paddle-L", state.paddle_left), ("Edge Paddle-R", state.paddle_right),
            ) if val
        ]
        self.buttons_label.setText(
            f"D-pad: {state.dpad} · Pulsados: {', '.join(pressed) if pressed else '(ninguno)'}"
        )

        self.sensors_label.setText(
            "Giro (x,y,z): "
            f"{state.gyro_x}, {state.gyro_y}, {state.gyro_z}\n"
            "Accel (x,y,z): "
            f"{state.accel_x}, {state.accel_y}, {state.accel_z}\n"
            f"Touch 1: {'activo' if state.touch1.active else 'inactivo'} "
            f"({state.touch1.x}, {state.touch1.y}) · "
            f"Touch 2: {'activo' if state.touch2.active else 'inactivo'} "
            f"({state.touch2.x}, {state.touch2.y})"
        )
