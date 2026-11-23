"""Servicio de Touchpad como ratón y Gyro Aim / Gyro Mouse Pro (v1.4.0)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject

from dualcontrol.models import ControllerState
from dualcontrol.services.windows_integration import mouse_button_event, move_mouse_relative
from dualcontrol.virtualcontroller.mapper import is_gyro_activation_active


class TouchpadGyroMouseService(QObject):
    """Traduce gestos del Touchpad del DualSense y movimiento del Giroscopio en
    movimiento de ratón nativo de Windows con filtro de suavizado EMA, zona muerta,
    selector de eje (Yaw/Roll) y botón de activación configurable."""

    def __init__(
        self,
        controller_service=None,
        move_fn: Callable[[int, int], None] = move_mouse_relative,
        button_fn: Callable[[str, bool], None] = mouse_button_event,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._controller_service = controller_service
        self._move_fn = move_fn
        self._button_fn = button_fn

        self.touchpad_mouse_enabled: bool = False
        self.touchpad_sensitivity: float = 0.45

        self.gyro_mouse_enabled: bool = False
        self.gyro_only_when_l2: bool = True
        self.gyro_activation: str = "l2"
        self.gyro_horizontal_axis: str = "yaw"
        self.gyro_deadzone: int = 45
        self.gyro_smoothing: float = 0.35
        self.gyro_sensitivity: float = 0.008

        self._ema_gh: float = 0.0
        self._ema_gx: float = 0.0
        self._prev_touch_active = False
        self._prev_tx = 0
        self._prev_ty = 0
        self._left_down = False
        self._right_down = False

        if self._controller_service is not None:
            self._controller_service.state_changed.connect(self.process_state)

    def process_state(self, state: ControllerState) -> None:
        dx_total = 0.0
        dy_total = 0.0

        # --- Touchpad como ratón ---
        if self.touchpad_mouse_enabled:
            t1 = state.touch1
            if t1.active:
                if self._prev_touch_active:
                    raw_dx = t1.x - self._prev_tx
                    raw_dy = t1.y - self._prev_ty
                    if abs(raw_dx) < 350 and abs(raw_dy) < 250:
                        dx_total += raw_dx * self.touchpad_sensitivity
                        dy_total += raw_dy * self.touchpad_sensitivity
                self._prev_tx = t1.x
                self._prev_ty = t1.y
                self._prev_touch_active = True
            else:
                self._prev_touch_active = False

            want_right = bool(state.touchpad_button and state.touch2.active)
            want_left = bool(state.touchpad_button and not want_right)

            if want_left != self._left_down:
                self._left_down = want_left
                self._button_fn("left", want_left)
            if want_right != self._right_down:
                self._right_down = want_right
                self._button_fn("right", want_right)
        else:
            self._prev_touch_active = False
            if self._left_down:
                self._left_down = False
                self._button_fn("left", False)
            if self._right_down:
                self._right_down = False
                self._button_fn("right", False)

        # --- Gyro Aim / Gyro Mouse Pro ---
        if self.gyro_mouse_enabled:
            act_mode = self.gyro_activation
            if act_mode == "l2" and not self.gyro_only_when_l2:
                act_mode = "always"
            active_gyro = is_gyro_activation_active(state, act_mode, fallback_only_l2=self.gyro_only_when_l2)
            if active_gyro:
                raw_h = float(state.gyro_z if self.gyro_horizontal_axis == "roll" else state.gyro_y)
                raw_x = float(state.gyro_x)
                dz = float(max(0, self.gyro_deadzone))
                gh = raw_h if abs(raw_h) > dz else 0.0
                gx = raw_x if abs(raw_x) > dz else 0.0

                smooth = max(0.0, min(0.85, float(self.gyro_smoothing)))
                if smooth > 0.0:
                    alpha = 1.0 - smooth
                    self._ema_gh += alpha * (gh - self._ema_gh)
                    self._ema_gx += alpha * (gx - self._ema_gx)
                    gh = self._ema_gh
                    gx = self._ema_gx

                dx_total += -gh * self.gyro_sensitivity
                dy_total += -gx * self.gyro_sensitivity
            else:
                self._ema_gh = 0.0
                self._ema_gx = 0.0

        ix = int(round(dx_total))
        iy = int(round(dy_total))
        if ix != 0 or iy != 0:
            self._move_fn(ix, iy)
