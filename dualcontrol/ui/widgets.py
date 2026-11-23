from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(16, 16, 16, 16)
        self.layout_.setSpacing(10)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("cardTitle")
            self.layout_.addWidget(title_label)

    def add(self, widget: QWidget) -> None:
        self.layout_.addWidget(widget)

    def add_layout(self, layout) -> None:
        self.layout_.addLayout(layout)


class LabeledSlider(QWidget):
    """Slider horizontal con etiqueta y valor numérico, 0..max_value."""

    valueChanged = Signal(int)

    def __init__(self, label: str, *, minimum: int = 0, maximum: int = 255, value: int = 0,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        row = QHBoxLayout()
        self._label = QLabel(label)
        self._value_label = QLabel(str(value))
        self._value_label.setAlignment(Qt.AlignRight)
        row.addWidget(self._label)
        row.addStretch(1)
        row.addWidget(self._value_label)
        outer.addLayout(row)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(minimum)
        self._slider.setMaximum(maximum)
        self._slider.setValue(value)
        self._slider.valueChanged.connect(self._on_change)
        outer.addWidget(self._slider)

    def _on_change(self, value: int) -> None:
        self._value_label.setText(str(value))
        self.valueChanged.emit(value)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value: int) -> None:
        self._slider.setValue(value)


class StickVisualizer(QWidget):
    """Representación visual simple de un stick analógico (sección 8)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(90, 90)
        self._x = 128
        self._y = 128
        self._pressed = False

    def set_position(self, x: int, y: int, pressed: bool = False) -> None:
        self._x, self._y, self._pressed = x, y, pressed
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = min(self.width(), self.height())
        radius = size / 2 - 6
        cx, cy = self.width() / 2, self.height() / 2

        painter.setPen(QPen(QColor("#2A2F3D"), 2))
        painter.setBrush(QColor("#181B22"))
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

        nx = (self._x - 128) / 128.0
        ny = (self._y - 128) / 128.0
        dot_x = cx + nx * radius
        dot_y = cy + ny * radius

        dot_color = QColor("#35D07F") if self._pressed else QColor("#2E6BFF")
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)
        painter.drawEllipse(int(dot_x - 8), int(dot_y - 8), 16, 16)


class TriggerBar(QWidget):
    """Barra vertical simple para el valor analógico de L2/R2."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(26, 90)
        self._value = 0

    def set_value(self, value: int) -> None:
        self._value = max(0, min(255, value))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#2A2F3D"), 1))
        painter.setBrush(QColor("#181B22"))
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 6, 6)

        fill_h = int((self._value / 255.0) * (self.height() - 4))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2E6BFF"))
        painter.drawRoundedRect(2, self.height() - 2 - fill_h, self.width() - 4, fill_h, 4, 4)
