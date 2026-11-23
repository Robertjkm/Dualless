from __future__ import annotations

from typing import Dict

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dualcontrol.app_context import AppContext
from dualcontrol.models import ControllerState, MappingSettings
from dualcontrol.services.macro_service import MACRO_ACTION_LABELS, MACRO_COMBO_LABELS
from dualcontrol.services.windows_integration import KEY_BINDING_OPTIONS
from dualcontrol.ui.widgets import Card, LabeledSlider
from dualcontrol.virtualcontroller.mapper import (
    DEFAULT_BUTTON_MAP,
    GYRO_ACTIVATION_LABELS,
    GYRO_AXIS_LABELS,
    PHYSICAL_BUTTON_LABELS,
    XINPUT_TARGET_LABELS,
    XInputSnapshot,
    map_dualsense_to_xinput,
)

# (shell_top, shell_bottom, trim_color, touchpad_color, outline_color, btn_fill, btn_symbol)
_SKINS = {
    "Classic White": ("#F5F6FA", "#E2E5EE", "#2A2D37", "#ECEEF5", "#13121A", "#E9ECF4", "#2B2E3B"),
    "Midnight Black": ("#2C2F3A", "#1C1E26", "#121319", "#242731", "#0B0B0F", "#252834", "#D8DCE8"),
    "Cosmic Red": ("#C81E51", "#8E1439", "#1E1924", "#B91B4B", "#140E16", "#2B1B27", "#F7DCE5"),
    "Starlight Blue": ("#38BDF8", "#0284C7", "#1B2230", "#2EA8E6", "#0F172A", "#1E293B", "#E0F2FE"),
    "Galactic Purple": ("#9333EA", "#6B21A8", "#1C1628", "#832CD4", "#120D1C", "#261B38", "#F3E8FF"),
}


class LiveDualSenseWidget(QWidget):
    """Vista técnica frontal interactiva del Sony DualSense (v0.6.1) con feedback
    en tiempo real de botones, sticks, D-pad, L1/R1, L2/R2, LED RGB, skins y Green Screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(380, 285)
        self._state = ControllerState()
        self._virtual_mode = False
        self._virtual_snap = XInputSnapshot()
        self._skin_name = "Classic White"
        self._green_screen = False
        self._led_color = QColor(59, 130, 246)

    def set_state(self, state: ControllerState, virtual_snap: XInputSnapshot) -> None:
        self._state = state
        self._virtual_snap = virtual_snap
        self.update()

    def set_virtual_mode(self, virtual: bool) -> None:
        self._virtual_mode = bool(virtual)
        self.update()

    def set_skin(self, skin_name: str) -> None:
        if skin_name in _SKINS:
            self._skin_name = skin_name
            self.update()

    def set_green_screen(self, enabled: bool) -> None:
        self._green_screen = bool(enabled)
        self.update()

    def set_led_color(self, r: int, g: int, b: int) -> None:
        self._led_color = QColor(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
        self.update()

    @staticmethod
    def _draw_ps_logo(p: QPainter, cx: float, cy: float, color: QColor) -> None:
        p.save()
        p.translate(cx - 10.0, cy - 9.0)
        p.scale(0.85, 0.85)
        p.setPen(Qt.NoPen)
        p.setBrush(color)

        p_stem = QPainterPath()
        p_stem.moveTo(9.8, 3.0)
        p_stem.lineTo(13.0, 4.1)
        p_stem.cubicTo(16.8, 5.4, 17.0, 10.2, 13.3, 11.4)
        p_stem.lineTo(12.2, 11.7)
        p_stem.lineTo(12.2, 19.8)
        p_stem.lineTo(9.8, 19.0)
        p_stem.closeSubpath()
        p.drawPath(p_stem)

        s_left = QPainterPath()
        s_left.moveTo(9.0, 14.5)
        s_left.cubicTo(4.0, 15.6, 2.2, 18.0, 5.4, 19.4)
        s_left.cubicTo(7.2, 20.1, 8.8, 19.5, 9.0, 18.9)
        s_left.lineTo(9.0, 17.0)
        s_left.cubicTo(7.5, 17.6, 6.2, 17.3, 6.8, 16.6)
        s_left.cubicTo(7.3, 16.1, 8.2, 15.8, 9.0, 15.6)
        s_left.closeSubpath()
        p.drawPath(s_left)

        s_right = QPainterPath()
        s_right.moveTo(13.0, 14.6)
        s_right.cubicTo(15.2, 13.8, 19.2, 13.9, 20.8, 15.5)
        s_right.cubicTo(22.2, 16.9, 20.5, 19.0, 16.4, 19.7)
        s_right.lineTo(13.0, 18.6)
        s_right.lineTo(13.0, 17.1)
        s_right.cubicTo(15.5, 17.8, 18.2, 17.3, 18.0, 16.4)
        s_right.cubicTo(17.8, 15.7, 15.2, 15.5, 13.0, 16.2)
        s_right.closeSubpath()
        p.drawPath(s_right)
        p.restore()

    @staticmethod
    def _draw_dpad_key(
        p: QPainter,
        cx: float,
        cy: float,
        direction: str,
        fill: QColor,
        outline: QColor,
        arrow_color: QColor,
    ) -> None:
        """Dibuja una tecla esculpida del D-pad del DualSense apuntando al centro."""
        p.save()
        p.translate(cx, cy)
        angle_map = {"up": 0, "right": 90, "down": 180, "left": 270}
        p.rotate(angle_map[direction])

        # Forma pentagonal redondeada apuntando hacia abajo (hacia el centro del D-pad)
        key = QPainterPath()
        key.moveTo(-6.5, -18.5)
        key.quadTo(-6.5, -21.5, -3.5, -21.5)
        key.lineTo(3.5, -21.5)
        key.quadTo(6.5, -21.5, 6.5, -18.5)
        key.lineTo(6.5, -9.5)
        key.lineTo(0.0, -3.5)
        key.lineTo(-6.5, -9.5)
        key.closeSubpath()

        p.setPen(QPen(outline, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(fill)
        p.drawPath(key)

        # Flecha direccional sutil
        tri = QPainterPath()
        tri.moveTo(0.0, -16.8)
        tri.lineTo(2.4, -13.2)
        tri.lineTo(-2.4, -13.2)
        tri.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(arrow_color)
        p.drawPath(tri)
        p.restore()

    @staticmethod
    def _draw_face_symbol(p: QPainter, fx: float, fy: float, kind: str, color: QColor) -> None:
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if kind == "triangle":
            tri = QPainterPath()
            tri.moveTo(fx, fy - 4.8)
            tri.lineTo(fx + 4.8, fy + 3.6)
            tri.lineTo(fx - 4.8, fy + 3.6)
            tri.closeSubpath()
            p.drawPath(tri)
        elif kind == "circle":
            p.drawEllipse(QPointF(fx, fy), 4.6, 4.6)
        elif kind == "cross":
            p.drawLine(QPointF(fx - 4.0, fy - 4.0), QPointF(fx + 4.0, fy + 4.0))
            p.drawLine(QPointF(fx + 4.0, fy - 4.0), QPointF(fx - 4.0, fy + 4.0))
        elif kind == "square":
            p.drawRect(QRectF(fx - 4.0, fy - 4.0, 8.0, 8.0))

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Fondo oscuro o Green Screen (Chroma Key)
        bg = QColor("#00B140") if self._green_screen else QColor("#1A1726")
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(self.rect(), 12, 12)

        vw, vh = 420.0, 290.0
        scale = min(self.width() / vw, self.height() / vh)
        ox = (self.width() - vw * scale) / 2.0
        oy = (self.height() - vh * scale) / 2.0
        p.translate(ox, oy)
        p.scale(scale, scale)

        s = self._state
        v = self._virtual_snap
        virt = self._virtual_mode

        l2_val = v.left_trigger if virt else s.l2_value
        r2_val = v.right_trigger if virt else s.r2_value
        l1_on = v.lb if virt else s.l1
        r1_on = v.rb if virt else s.r1
        cross_on = v.a if virt else s.cross
        circle_on = v.b if virt else s.circle
        square_on = v.x if virt else s.square
        tri_on = v.y if virt else s.triangle
        l3_on = v.left_thumb if virt else s.l3
        r3_on = v.right_thumb if virt else s.r3
        create_on = v.back if virt else s.create
        options_on = v.start if virt else s.options
        ps_on = v.guide if virt else s.ps
        mute_on = bool(s.mute)

        d_up = v.dpad_up if virt else (s.dpad in ("N", "NE", "NW"))
        d_dn = v.dpad_down if virt else (s.dpad in ("S", "SE", "SW"))
        d_lf = v.dpad_left if virt else (s.dpad in ("W", "NW", "SW"))
        d_rt = v.dpad_right if virt else (s.dpad in ("E", "NE", "SE"))

        if virt:
            lx = v.left_x / 32768.0
            ly = -v.left_y / 32768.0
            rx = v.right_x / 32768.0
            ry = -v.right_y / 32768.0
        else:
            lx = (s.left_stick.x - 128) / 128.0
            ly = (s.left_stick.y - 128) / 128.0
            rx = (s.right_stick.x - 128) / 128.0
            ry = (s.right_stick.y - 128) / 128.0

        active_col = QColor("#22C55E") if virt else QColor("#8B5CF6")
        active_trigger_col = QColor("#22C55E") if virt else QColor("#3B82F6")
        shell_top, shell_bot, trim_hex, tp_hex, outline_hex, btn_fill_hex, btn_sym_hex = _SKINS[self._skin_name]
        outline_col = QColor(outline_hex)
        trim_col = QColor(trim_hex)
        btn_fill = QColor(btn_fill_hex)
        btn_sym = QColor(btn_sym_hex)

        # --- 1. Indicadores sutiles de L1/R1 (arriba), L2/R2 (lados) y agarres ---
        # Indicadores superiores L1 / R1
        for rx_ind, on in ((114.0, l1_on), (258.0, r1_on)):
            p.setPen(QPen(active_col if on else QColor("#38324D"), 1.3))
            p.setBrush(active_col if on else QColor(34, 29, 48, 120))
            p.drawRoundedRect(QRectF(rx_ind, 22, 48, 11), 5.5, 5.5)

        # Barras verticales L2 / R2
        for bx, val in ((38.0, l2_val), (370.0, r2_val)):
            p.setPen(QPen(QColor("#38324D"), 1.3))
            p.setBrush(QColor(22, 19, 32, 180))
            p.drawRoundedRect(QRectF(bx, 62, 12, 68), 6, 6)
            fill_h = (max(0, min(255, val)) / 255.0) * 64.0
            if fill_h > 0:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#EF4444") if val > 215 else active_trigger_col)
                p.drawRoundedRect(QRectF(bx + 2, 62 + 66 - fill_h, 8, fill_h), 4, 4)

        # Indicadores inferiores de agarre (decorativos / responden a L2/R2 a fondo)
        for gx, pressed in ((32.0, l2_val > 180), (378.0, r2_val > 180)):
            p.setPen(QPen(active_trigger_col if pressed else QColor("#332D47"), 1.2))
            p.setBrush(QColor(59, 130, 246, 80) if pressed else QColor(24, 20, 35, 110))
            p.drawRoundedRect(QRectF(gx, 156, 10, 40), 5, 5)

        # --- 2. Bumpers físicos L1 / R1 pegados a los hombros ---
        l1_path = QPainterPath()
        l1_path.moveTo(96, 62)
        l1_path.cubicTo(106, 51, 126, 48, 142, 51)
        l1_path.lineTo(139, 59)
        l1_path.lineTo(99, 67)
        l1_path.closeSubpath()

        r1_path = QPainterPath()
        r1_path.moveTo(324, 62)
        r1_path.cubicTo(314, 51, 294, 48, 278, 51)
        r1_path.lineTo(281, 59)
        r1_path.lineTo(321, 67)
        r1_path.closeSubpath()

        for path_b, on in ((l1_path, l1_on), (r1_path, r1_on)):
            p.setPen(QPen(outline_col, 1.4))
            p.setBrush(active_col if on else QColor("#4A4C58"))
            p.drawPath(path_b)

        # --- 3. Carcasa exterior completa del DualSense (blueprint frontal) ---
        body = QPainterPath()
        body.moveTo(152, 54)
        body.cubicTo(175, 50, 245, 50, 268, 54)
        body.cubicTo(298, 55, 322, 62, 332, 82)
        body.cubicTo(346, 112, 358, 166, 360, 212)
        body.cubicTo(361, 236, 348, 250, 331, 250)
        body.lineTo(321, 250)
        body.cubicTo(308, 224, 294, 192, 276, 180)
        body.cubicTo(266, 174, 252, 174, 238, 174)
        body.lineTo(182, 174)
        body.cubicTo(168, 174, 154, 174, 144, 180)
        body.cubicTo(126, 192, 112, 224, 99, 250)
        body.lineTo(89, 250)
        body.cubicTo(72, 250, 59, 236, 60, 212)
        body.cubicTo(62, 166, 74, 112, 88, 82)
        body.cubicTo(98, 62, 122, 55, 152, 54)
        body.closeSubpath()

        shell_grad = QLinearGradient(0, 50, 0, 252)
        shell_grad.setColorAt(0.0, QColor(shell_top))
        shell_grad.setColorAt(1.0, QColor(shell_bot))
        p.setPen(QPen(outline_col, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(shell_grad)
        p.drawPath(body)

        # --- 4. Panel central oscuro bicolor (incluye tiras interiores de las asas) ---
        trim = QPainterPath()
        trim.moveTo(151, 55)
        trim.lineTo(159, 108)
        trim.cubicTo(161, 116, 167, 118, 176, 118)
        trim.lineTo(244, 118)
        trim.cubicTo(253, 118, 259, 116, 261, 108)
        trim.lineTo(269, 55)
        # Curva hacia el stick derecho y asa derecha
        trim.cubicTo(271, 78, 268, 106, 276, 126)
        trim.cubicTo(292, 154, 314, 204, 333, 249)
        trim.lineTo(321, 250)
        trim.cubicTo(308, 224, 294, 192, 276, 180)
        trim.cubicTo(266, 174, 252, 174, 238, 174)
        trim.lineTo(182, 174)
        trim.cubicTo(168, 174, 154, 174, 144, 180)
        trim.cubicTo(126, 192, 112, 224, 99, 250)
        trim.lineTo(87, 249)
        trim.cubicTo(106, 204, 128, 154, 144, 126)
        trim.cubicTo(152, 106, 149, 78, 151, 55)
        trim.closeSubpath()

        trim_grad = QLinearGradient(0, 100, 0, 248)
        trim_grad.setColorAt(0.0, trim_col.lighter(118))
        trim_grad.setColorAt(1.0, trim_col.darker(115))
        p.setPen(QPen(outline_col, 1.5))
        p.setBrush(trim_grad)
        p.drawPath(trim)

        # --- 5. Touchpad central + resplandor LED RGB lateral ---
        tp = QPainterPath()
        tp.moveTo(154, 54)
        tp.cubicTo(176, 50, 244, 50, 266, 54)
        tp.lineTo(259, 104)
        tp.cubicTo(258, 112, 252, 115, 243, 115)
        tp.lineTo(177, 115)
        tp.cubicTo(168, 115, 162, 112, 161, 104)
        tp.closeSubpath()

        p.setPen(QPen(outline_col, 1.4))
        p.setBrush(active_col if s.touchpad_button else QColor(tp_hex))
        p.drawPath(tp)

        # Halo suave de las tiras LED RGB
        led_glow_col = QColor(self._led_color)
        led_glow_col.setAlpha(90)
        p.setPen(QPen(led_glow_col, 5.2, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        left_led = QPainterPath()
        left_led.moveTo(152.5, 57)
        left_led.lineTo(159.5, 105)
        left_led.quadTo(161.5, 115, 171, 116.5)

        right_led = QPainterPath()
        right_led.moveTo(267.5, 57)
        right_led.lineTo(260.5, 105)
        right_led.quadTo(258.5, 115, 249, 116.5)

        p.drawPath(left_led)
        p.drawPath(right_led)

        # Núcleo brillante de la tira LED
        p.setPen(QPen(self._led_color, 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(left_led)
        p.drawPath(right_led)

        # Luz indicadora de jugador centrada bajo el touchpad
        ind_glow = QRadialGradient(210.0, 118.0, 12.0)
        c_ind = QColor(self._led_color)
        c_ind.setAlpha(150)
        ind_glow.setColorAt(0.0, c_ind)
        ind_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(ind_glow)
        p.drawEllipse(QPointF(210.0, 118.0), 12.0, 5.0)
        p.setBrush(QColor("#E0F2FE"))
        p.drawEllipse(QPointF(210.0, 117.5), 1.8, 1.8)

        # --- 6. Altavoz central (puntos), Logo PS, Botón Mute y Micrófono ---
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#111017"))
        for dx in (-8, -4, 0, 4, 8):
            p.drawEllipse(QPointF(210.0 + dx, 123.5), 1.2, 1.2)
        for dx in (-6, -2, 2, 6):
            p.drawEllipse(QPointF(210.0 + dx, 128.0), 1.2, 1.2)

        self._draw_ps_logo(p, 210.0, 144.0, active_col if ps_on else QColor("#A6AAB8"))

        # Botón Mute horizontal
        p.setPen(QPen(outline_col, 1.0))
        p.setBrush(QColor("#F59E0B") if mute_on else QColor("#4B4F5E"))
        p.drawRoundedRect(QRectF(202.5, 160.0, 15.0, 4.2), 2.1, 2.1)

        # Pinhole del micrófono
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#111017"))
        p.drawRoundedRect(QRectF(208.0, 168.5, 4.0, 1.8), 0.9, 0.9)

        # --- 7. Botones Create (izq) y Options (der) ---
        for bx, tilt, on, is_create in ((139.0, -14.0, create_on, True), (281.0, 14.0, options_on, False)):
            p.save()
            p.translate(bx, 76.0)
            p.rotate(tilt)
            p.setPen(QPen(outline_col, 1.2))
            p.setBrush(active_col if on else btn_fill)
            p.drawRoundedRect(QRectF(-3.2, -7.2, 6.4, 14.4), 3.2, 3.2)
            p.restore()
            # Pequeñas marcas indicadoras arriba de Create / Options
            p.setPen(QPen(btn_sym, 1.0, Qt.SolidLine, Qt.RoundCap))
            if is_create:
                p.drawLine(QPointF(bx - 3.0, 64.5), QPointF(bx - 4.0, 62.5))
                p.drawLine(QPointF(bx, 63.8), QPointF(bx, 61.6))
                p.drawLine(QPointF(bx + 3.0, 64.5), QPointF(bx + 4.0, 62.5))
            else:
                for ly_m in (62.0, 63.8, 65.6):
                    p.drawLine(QPointF(bx - 2.6, ly_m), QPointF(bx + 2.6, ly_m))

        # --- 8. D-Pad esculpido (centro en 114, 110) ---
        dpad_cx, dpad_cy = 114.0, 110.0
        for direction, on in (("up", d_up), ("down", d_dn), ("left", d_lf), ("right", d_rt)):
            self._draw_dpad_key(
                p,
                dpad_cx,
                dpad_cy,
                direction,
                active_col if on else btn_fill,
                outline_col,
                QColor("#FFFFFF") if on else btn_sym,
            )

        # --- 9. Botones de cara (centro en 306, 110) ---
        face_cx, face_cy, offset = 306.0, 110.0, 21.0
        face_defs = [
            (face_cx, face_cy - offset, "triangle", "Y", tri_on),
            (face_cx + offset, face_cy, "circle", "B", circle_on),
            (face_cx, face_cy + offset, "cross", "A", cross_on),
            (face_cx - offset, face_cy, "square", "X", square_on),
        ]
        for fx, fy, sym_kind, xbox_lbl, on in face_defs:
            p.setPen(QPen(QColor("#FFFFFF") if on else outline_col, 1.4))
            p.setBrush(active_col if on else btn_fill)
            p.drawEllipse(QPointF(fx, fy), 10.2, 10.2)
            if virt:
                p.setPen(QColor("#0B0F14") if on else btn_sym)
                f = p.font()
                f.setPointSize(9)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRectF(fx - 10, fy - 10, 20, 20), Qt.AlignCenter, xbox_lbl)
            else:
                self._draw_face_symbol(p, fx, fy, sym_kind, QColor("#FFFFFF") if on else btn_sym)

        # --- 10. Sticks analógicos con movimiento en vivo ---
        for sx, sy, dx, dy, pressed in (
            (163.0, 148.0, lx, ly, l3_on),
            (257.0, 148.0, rx, ry, r3_on),
        ):
            # Hueco exterior del stick
            p.setPen(QPen(outline_col, 1.6))
            p.setBrush(QColor("#1A1C24"))
            p.drawEllipse(QPointF(sx, sy), 21.5, 21.5)

            # Anillo interior del hueco
            p.setPen(QPen(QColor("#3E4252"), 1.0))
            p.setBrush(QColor("#232632"))
            p.drawEllipse(QPointF(sx, sy), 17.5, 17.5)

            # Cabezal móvil del stick
            kx = sx + dx * 9.5
            ky = sy + dy * 9.5
            p.setPen(QPen(QColor("#FFFFFF") if pressed else outline_col, 1.5))
            p.setBrush(active_col if pressed else QColor("#363A48"))
            p.drawEllipse(QPointF(kx, ky), 13.5, 13.5)

            # Borde cóncavo del cabezal
            p.setPen(QPen(QColor("#E0F2FE") if pressed else QColor("#52576B"), 1.1))
            p.setBrush(QColor(255, 255, 255, 40) if pressed else QColor("#2B2E3B"))
            p.drawEllipse(QPointF(kx, ky), 9.2, 9.2)


class _AccordionSection(QFrame):
    """Tarjeta desplegable de la columna derecha (Actions, Deadzones, Motion, Sticks, Touchpad, Gamepad Skin)."""

    toggled_open = Signal(str)

    def __init__(self, key: str, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._open = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = QFrame()
        self._header.setCursor(Qt.PointingHandCursor)
        h_row = QHBoxLayout(self._header)
        h_row.setContentsMargins(14, 11, 14, 11)
        h_row.setSpacing(10)

        t_col = QVBoxLayout()
        t_col.setSpacing(2)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        s_lbl = QLabel(subtitle)
        s_lbl.setWordWrap(True)
        s_lbl.setStyleSheet("font-size: 12px; color: #A6A0B8; background: transparent; border: none;")
        t_col.addWidget(t_lbl)
        t_col.addWidget(s_lbl)
        h_row.addLayout(t_col, 1)

        self._chevron = QLabel("›")
        self._chevron.setStyleSheet("color: #A6A0B8; font-size: 18px; background: transparent; border: none;")
        h_row.addWidget(self._chevron)

        self._header.mousePressEvent = lambda _e: self.toggled_open.emit(self.key)  # type: ignore[assignment]
        outer.addWidget(self._header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(14, 4, 14, 14)
        self.body_layout.setSpacing(10)
        self.body.setVisible(False)
        outer.addWidget(self.body)

        self._apply_style()

    def set_open(self, opened: bool) -> None:
        self._open = bool(opened)
        self.body.setVisible(self._open)
        self._chevron.setText("⌄" if self._open else "›")
        self._apply_style()

    def _apply_style(self) -> None:
        if self._open:
            self.setStyleSheet(
                "QFrame { background-color: #251F34; border: 1.5px solid #8B5CF6; border-radius: 10px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background-color: #1D1A27; border: 1px solid #2F2940; border-radius: 10px; }"
            )


class ControllerMappingsPage(QWidget):
    """Sección unificada 'Controller Mappings' (combina Controller + Button Mapping)."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._combos: Dict[str, QComboBox] = {}
        self._kb_combos: Dict[str, QComboBox] = {}
        self._turbo_checks: Dict[str, QCheckBox] = {}
        self._macro_combos: Dict[str, QComboBox] = {}
        self._last_raw_state = ControllerState()
        self._offset_lx = 0
        self._offset_ly = 0
        self._offset_rx = 0
        self._offset_ry = 0
        self._sections: Dict[str, _AccordionSection] = {}
        self._virtual_preview = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        root = QHBoxLayout(container)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(16)

        # ==================== COLUMNA IZQUIERDA: INPUT FEEDBACK ====================
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        fb_card = Card("")
        fb_top = QHBoxLayout()
        fb_titles = QVBoxLayout()
        fb_t = QLabel("Input Feedback")
        fb_t.setObjectName("cardTitle")
        fb_s = QLabel("View physical (real) input or virtual (emulated) input.")
        fb_s.setObjectName("pageSubtitle")
        fb_titles.addWidget(fb_t)
        fb_titles.addWidget(fb_s)
        fb_top.addLayout(fb_titles, 1)

        self._fb_group = QButtonGroup(self)
        self._fb_group.setExclusive(True)
        self.btn_physical = QPushButton("PHYSICAL")
        self.btn_physical.setObjectName("subNavButton")
        self.btn_physical.setCheckable(True)
        self.btn_physical.setChecked(True)
        self.btn_physical.clicked.connect(lambda: self._set_feedback_mode(False))

        self.btn_virtual = QPushButton("VIRTUAL")
        self.btn_virtual.setObjectName("subNavButton")
        self.btn_virtual.setCheckable(True)
        self.btn_virtual.clicked.connect(lambda: self._set_feedback_mode(True))

        self._fb_group.addButton(self.btn_physical, 0)
        self._fb_group.addButton(self.btn_virtual, 1)
        fb_top.addWidget(self.btn_physical)
        fb_top.addWidget(self.btn_virtual)
        fb_card.add_layout(fb_top)

        self.live_controller = LiveDualSenseWidget()
        fb_card.add(self.live_controller)

        # Input Extended (desplegable)
        self.ext_btn = QPushButton("Input Extended  ⌄")
        self.ext_btn.setObjectName("secondary")
        self.ext_btn.setCheckable(True)
        self.ext_btn.setChecked(True)
        self.ext_btn.toggled.connect(self._toggle_extended)
        fb_card.add(self.ext_btn)

        self.ext_panel = QFrame()
        self.ext_panel.setStyleSheet(
            "QFrame { background-color: #16131F; border: 1px solid #2C263D; border-radius: 8px; }"
        )
        ext_lay = QVBoxLayout(self.ext_panel)
        ext_lay.setContentsMargins(10, 8, 10, 8)
        ext_lay.setSpacing(4)
        self.buttons_label = QLabel("D-pad: NONE · Pulsados: (ninguno)")
        self.buttons_label.setWordWrap(True)
        self.sticks_label = QLabel("L: (128, 128) · R: (128, 128) · L2: 0 · R2: 0")
        self.sticks_label.setObjectName("pageSubtitle")
        ext_lay.addWidget(self.buttons_label)
        ext_lay.addWidget(self.sticks_label)
        fb_card.add(self.ext_panel)

        left_col.addWidget(fb_card)
        left_col.addStretch(1)
        root.addLayout(left_col, 5)

        # ==================== COLUMNA DERECHA: MAPPINGS & SETTINGS ====================
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        hdr_row = QHBoxLayout()
        badge = QLabel("DualSense™ Wireless Controller")
        badge.setStyleSheet(
            "background-color: #241F32; border: 1px solid #38304D; border-radius: 8px; "
            "padding: 6px 14px; font-weight: 700; color: #FFFFFF;"
        )
        hdr_row.addWidget(badge)
        hdr_row.addStretch(1)

        apply_btn = QPushButton("Aplicar mapeo")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._apply_mapping)
        reset_btn = QPushButton("Restaurar")
        reset_btn.setObjectName("secondary")
        reset_btn.clicked.connect(self._reset_defaults)
        hdr_row.addWidget(apply_btn)
        hdr_row.addWidget(reset_btn)
        right_col.addLayout(hdr_row)

        # 1. Actions (Button Mapping)
        sec_actions = _AccordionSection(
            "actions",
            "Actions",
            "Create an action for button mapping, reasignación DualSense → Xbox XInput y desactivación.",
        )
        btn_grid = QGridLayout()
        btn_grid.setSpacing(6)
        hdr_b = QLabel("Botón DualSense / Edge")
        hdr_x = QLabel("Mando Virtual (XInput)")
        hdr_k = QLabel("Teclado / Ratón libre")
        hdr_t = QLabel("Turbo")
        for col_i, h_lbl in enumerate((hdr_b, hdr_x, hdr_k, hdr_t)):
            h_lbl.setStyleSheet("font-weight: 700; color: #38BDF8; font-size: 11px;")
            btn_grid.addWidget(h_lbl, 0, col_i)

        for row_idx, (phys_key, phys_label) in enumerate(PHYSICAL_BUTTON_LABELS, start=1):
            btn_grid.addWidget(QLabel(phys_label), row_idx, 0)

            combo = QComboBox()
            for target_key, target_label in XINPUT_TARGET_LABELS:
                combo.addItem(target_label, target_key)
            self._combos[phys_key] = combo
            btn_grid.addWidget(combo, row_idx, 1)

            kb_combo = QComboBox()
            for kb_key, kb_label in KEY_BINDING_OPTIONS:
                kb_combo.addItem(kb_label, kb_key)
            self._kb_combos[phys_key] = kb_combo
            btn_grid.addWidget(kb_combo, row_idx, 2)

            t_chk = QCheckBox("")
            self._turbo_checks[phys_key] = t_chk
            btn_grid.addWidget(t_chk, row_idx, 3, Qt.AlignCenter)

        sec_actions.body_layout.addLayout(btn_grid)

        self.turbo_rate_slider = LabeledSlider("Velocidad de Turbo / Rapid Fire (Hz)", minimum=2, maximum=25, value=12)
        sec_actions.body_layout.addWidget(self.turbo_rate_slider)

        # --- Macros y Atajos de Windows (v1.0.0) ---
        m_sep = QLabel("Macros y Atajos de Windows (combos de botones)")
        m_sep.setStyleSheet("font-weight: 700; color: #38BDF8; margin-top: 8px;")
        sec_actions.body_layout.addWidget(m_sep)

        self.macros_enable_check = QCheckBox("Activar combos de botones (volumen, captura, Alt+Tab, cambio de perfil)")
        self.macros_enable_check.setChecked(self.ctx.macro_service.enabled)
        self.macros_enable_check.toggled.connect(self._on_macros_toggled)
        sec_actions.body_layout.addWidget(self.macros_enable_check)

        macro_grid = QGridLayout()
        macro_grid.setSpacing(6)
        for m_idx, (combo_key, combo_lbl) in enumerate(MACRO_COMBO_LABELS):
            macro_grid.addWidget(QLabel(combo_lbl), m_idx, 0)
            m_combo = QComboBox()
            for act_key, act_lbl in MACRO_ACTION_LABELS:
                m_combo.addItem(act_lbl, act_key)
            cur_act = self.ctx.macro_service.macros.get(combo_key, "none")
            ci = m_combo.findData(cur_act)
            if ci >= 0:
                m_combo.setCurrentIndex(ci)
            m_combo.currentIndexChanged.connect(
                lambda _i, ck=combo_key, cb=m_combo: self._on_macro_changed(ck, cb.currentData())
            )
            self._macro_combos[combo_key] = m_combo
            macro_grid.addWidget(m_combo, m_idx, 1)
        sec_actions.body_layout.addLayout(macro_grid)
        self._register_section(sec_actions, right_col)

        # 2. Deadzones
        sec_deadzones = _AccordionSection(
            "deadzones",
            "Deadzones",
            "Adjust the joystick deadzone to improve your accuracy.",
        )
        self.dz_left = LabeledSlider("Stick Izquierdo — Zona muerta (%)", minimum=0, maximum=50, value=5)
        self.dz_right = LabeledSlider("Stick Derecho — Zona muerta (%)", minimum=0, maximum=50, value=5)
        sec_deadzones.body_layout.addWidget(self.dz_left)
        sec_deadzones.body_layout.addWidget(self.dz_right)
        self._register_section(sec_deadzones, right_col)

        # 2b. Triggers (Hair Trigger, Deadzone & Dual Stage)
        sec_triggers_map = _AccordionSection(
            "triggers_map",
            "Triggers (Hair Trigger & Dual Stage)",
            "Recorta el recorrido de L2/R2 para disparar al instante o asigna una acción extra al presionar a fondo.",
        )
        self.trig_dz_l2 = LabeledSlider("L2 — Zona muerta (%)", minimum=0, maximum=50, value=0)
        self.hair_l2_check = QCheckBox("Activar Hair Trigger en L2 (disparo instantáneo al mínimo toque)")
        ds_l2_row = QHBoxLayout()
        ds_l2_row.addWidget(QLabel("L2 Dual Stage (al presionar a fondo):"))
        self.ds_l2_combo = QComboBox()
        for kb_key, kb_label in KEY_BINDING_OPTIONS:
            self.ds_l2_combo.addItem(kb_label, kb_key)
        ds_l2_row.addWidget(self.ds_l2_combo, 1)

        self.trig_dz_r2 = LabeledSlider("R2 — Zona muerta (%)", minimum=0, maximum=50, value=0)
        self.hair_r2_check = QCheckBox("Activar Hair Trigger en R2 (disparo instantáneo al mínimo toque)")
        ds_r2_row = QHBoxLayout()
        ds_r2_row.addWidget(QLabel("R2 Dual Stage (al presionar a fondo):"))
        self.ds_r2_combo = QComboBox()
        for kb_key, kb_label in KEY_BINDING_OPTIONS:
            self.ds_r2_combo.addItem(kb_label, kb_key)
        ds_r2_row.addWidget(self.ds_r2_combo, 1)

        self.hair_thr_slider = LabeledSlider("Umbral de Hair Trigger (%)", minimum=2, maximum=35, value=5)
        self.rapid_l2_check = QCheckBox("Activar Rapid Trigger en L2 (libera apenas retrocedes el dedo)")
        self.rapid_r2_check = QCheckBox("Activar Rapid Trigger en R2 (libera apenas retrocedes el dedo)")
        self.rapid_rel_slider = LabeledSlider("Margen de liberación Rapid Trigger (%)", minimum=3, maximum=25, value=8)
        self.ds_thr_slider = LabeledSlider("Umbral Dual Stage (%)", minimum=70, maximum=98, value=92)

        tactile_btn = QPushButton("Aplicar tope táctil Dual Stage en L2 y R2")
        tactile_btn.setObjectName("secondary")
        tactile_btn.clicked.connect(self._apply_dual_stage_stop)

        sec_triggers_map.body_layout.addWidget(self.trig_dz_l2)
        sec_triggers_map.body_layout.addWidget(self.hair_l2_check)
        sec_triggers_map.body_layout.addWidget(self.rapid_l2_check)
        sec_triggers_map.body_layout.addLayout(ds_l2_row)
        sec_triggers_map.body_layout.addWidget(self.trig_dz_r2)
        sec_triggers_map.body_layout.addWidget(self.hair_r2_check)
        sec_triggers_map.body_layout.addWidget(self.rapid_r2_check)
        sec_triggers_map.body_layout.addLayout(ds_r2_row)
        sec_triggers_map.body_layout.addWidget(self.hair_thr_slider)
        sec_triggers_map.body_layout.addWidget(self.rapid_rel_slider)
        sec_triggers_map.body_layout.addWidget(self.ds_thr_slider)
        sec_triggers_map.body_layout.addWidget(tactile_btn)
        self._register_section(sec_triggers_map, right_col)

        # 3. Motion (Gyro & Accel)
        sec_motion = _AccordionSection(
            "motion",
            "Motion",
            "Utilize the gyroscope and accelerometer to enhance your gaming needs.",
        )
        self.gyro_mouse_check = QCheckBox("Activar Gyro Aim / Gyro Mouse (mueve el cursor con el giroscopio)")
        self.gyro_mouse_check.setChecked(self.ctx.touchpad_mouse.gyro_mouse_enabled)
        self.gyro_mouse_check.toggled.connect(lambda c: setattr(self.ctx.touchpad_mouse, "gyro_mouse_enabled", bool(c)))
        self.gyro_sens = LabeledSlider(
            "Sensibilidad Gyro Mouse",
            minimum=1,
            maximum=35,
            value=max(1, min(35, int(round(self.ctx.touchpad_mouse.gyro_sensitivity * 1000)))),
        )
        self.gyro_sens.valueChanged.connect(lambda v: setattr(self.ctx.touchpad_mouse, "gyro_sensitivity", v / 1000.0))

        # Ajustes compartidos Gyro Pro (v1.4.0)
        act_row = QHBoxLayout()
        act_row.addWidget(QLabel("Botón de activación del Gyro:"))
        self.gyro_act_combo = QComboBox()
        for ak, al in GYRO_ACTIVATION_LABELS:
            self.gyro_act_combo.addItem(al, ak)
        self.gyro_act_combo.currentIndexChanged.connect(self._on_gyro_pro_changed)
        act_row.addWidget(self.gyro_act_combo, 1)

        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Eje horizontal (Yaw / Roll):"))
        self.gyro_axis_combo = QComboBox()
        for axk, axl in GYRO_AXIS_LABELS:
            self.gyro_axis_combo.addItem(axl, axk)
        self.gyro_axis_combo.currentIndexChanged.connect(self._on_gyro_pro_changed)
        axis_row.addWidget(self.gyro_axis_combo, 1)

        self.gyro_dz_slider = LabeledSlider("Zona muerta anti-temblor del Gyro", minimum=0, maximum=200, value=45)
        self.gyro_dz_slider.valueChanged.connect(self._on_gyro_pro_changed)
        self.gyro_smooth_slider = LabeledSlider("Suavizado EMA del Gyro (%)", minimum=0, maximum=85, value=35)
        self.gyro_smooth_slider.valueChanged.connect(self._on_gyro_pro_changed)

        gs_hdr = QLabel("Gyro-to-Stick (Giroscopio → Stick Derecho virtual — sin conflicto con ratón)")
        gs_hdr.setStyleSheet("font-weight: 700; color: #38BDF8; margin-top: 8px;")
        self.gyro_stick_check = QCheckBox("Activar Gyro-to-Stick (ideal para shooters con mando Xbox/DS4)")
        self.gyro_stick_sens = LabeledSlider("Sensibilidad Gyro-to-Stick (%)", minimum=25, maximum=400, value=100)
        self.gyro_stick_inv_x = QCheckBox("Invertir Gyro-to-Stick eje X")
        self.gyro_stick_inv_y = QCheckBox("Invertir Gyro-to-Stick eje Y")

        self.motion_label = QLabel("Giro (x,y,z): 0, 0, 0\nAccel (x,y,z): 0, 0, 0")
        self.motion_label.setObjectName("pageSubtitle")

        sec_motion.body_layout.addWidget(self.gyro_mouse_check)
        sec_motion.body_layout.addWidget(self.gyro_sens)
        sec_motion.body_layout.addLayout(act_row)
        sec_motion.body_layout.addLayout(axis_row)
        sec_motion.body_layout.addWidget(self.gyro_dz_slider)
        sec_motion.body_layout.addWidget(self.gyro_smooth_slider)
        for w in (
            gs_hdr,
            self.gyro_stick_check,
            self.gyro_stick_sens,
            self.gyro_stick_inv_x,
            self.gyro_stick_inv_y,
            self.motion_label,
        ):
            sec_motion.body_layout.addWidget(w)
        self._register_section(sec_motion, right_col)

        # 4. Sticks (Sensitivity & Axis Inversion)
        sec_sticks = _AccordionSection(
            "sticks",
            "Sticks",
            "Configure sensitivity and axis inversion for Left and Right sticks.",
        )
        self.sens_left = LabeledSlider("Stick Izquierdo — Sensibilidad (%)", minimum=25, maximum=200, value=100)
        self.inv_left_x = QCheckBox("Invertir eje X izquierdo")
        self.inv_left_y = QCheckBox("Invertir eje Y izquierdo")
        self.sens_right = LabeledSlider("Stick Derecho — Sensibilidad (%)", minimum=25, maximum=200, value=100)
        self.inv_right_x = QCheckBox("Invertir eje X derecho")
        self.inv_right_y = QCheckBox("Invertir eje Y derecho")
        curve_row_l = QHBoxLayout()
        curve_row_l.addWidget(QLabel("Curva Stick Izquierdo:"))
        self.curve_left_combo = QComboBox()
        for ck, cl in (("linear", "Lineal (Estándar)"), ("precision", "Precisión (Apuntado fino)"), ("fast", "Rápida (Respuesta agresiva)")):
            self.curve_left_combo.addItem(cl, ck)
        curve_row_l.addWidget(self.curve_left_combo, 1)

        curve_row_r = QHBoxLayout()
        curve_row_r.addWidget(QLabel("Curva Stick Derecho:"))
        self.curve_right_combo = QComboBox()
        for ck, cl in (("linear", "Lineal (Estándar)"), ("precision", "Precisión (Apuntado fino)"), ("fast", "Rápida (Respuesta agresiva)")):
            self.curve_right_combo.addItem(cl, ck)
        curve_row_r.addWidget(self.curve_right_combo, 1)

        for w in (self.sens_left, self.inv_left_x, self.inv_left_y):
            sec_sticks.body_layout.addWidget(w)
        sec_sticks.body_layout.addLayout(curve_row_l)
        for w in (self.sens_right, self.inv_right_x, self.inv_right_y):
            sec_sticks.body_layout.addWidget(w)
        sec_sticks.body_layout.addLayout(curve_row_r)

        # Calibración Anti-Drift
        drift_row = QHBoxLayout()
        cal_btn = QPushButton("Calibrar centro (Anti-Drift)")
        cal_btn.setObjectName("primary")
        cal_btn.clicked.connect(self._calibrate_center)
        clr_btn = QPushButton("Limpiar calibración")
        clr_btn.setObjectName("secondary")
        clr_btn.clicked.connect(self._clear_calibration)
        drift_row.addWidget(cal_btn)
        drift_row.addWidget(clr_btn)
        sec_sticks.body_layout.addLayout(drift_row)

        self.drift_status_lbl = QLabel("Calibración anti-drift: (0, 0) / (0, 0)")
        self.drift_status_lbl.setObjectName("pageSubtitle")
        sec_sticks.body_layout.addWidget(self.drift_status_lbl)
        self._register_section(sec_sticks, right_col)

        # 5. Touchpad
        sec_touchpad = _AccordionSection(
            "touchpad",
            "Touchpad",
            "Utilize the full range of the touchpad to create various inputs with the touch of a finger.",
        )
        self.tp_mouse_check = QCheckBox("Usar Touchpad como ratón de Windows (1 dedo mover, clic = izq, 2 dedos = der)")
        self.tp_mouse_check.toggled.connect(lambda c: setattr(self.ctx.touchpad_mouse, "touchpad_mouse_enabled", bool(c)))
        self.tp_sens = LabeledSlider("Sensibilidad del Touchpad (%)", minimum=10, maximum=150, value=45)
        self.tp_sens.valueChanged.connect(lambda v: setattr(self.ctx.touchpad_mouse, "touchpad_sensitivity", v / 100.0))
        self.touchpad_label = QLabel("Touch 1: inactivo (0, 0) · Touch 2: inactivo (0, 0)")
        self.touchpad_label.setObjectName("pageSubtitle")
        for w in (self.tp_mouse_check, self.tp_sens, self.touchpad_label):
            sec_touchpad.body_layout.addWidget(w)
        self._register_section(sec_touchpad, right_col)

        # 6. Gamepad Skin + Green Screen Effect
        sec_skin = _AccordionSection(
            "skin",
            "Gamepad Skin",
            "Choose which gamepad skin you want visible for feedback on the left.",
        )
        skin_row = QHBoxLayout()
        skin_row.addWidget(QLabel("Skin:"))
        self.skin_combo = QComboBox()
        self.skin_combo.addItems(list(_SKINS.keys()))
        self.skin_combo.currentTextChanged.connect(self.live_controller.set_skin)
        skin_row.addWidget(self.skin_combo, 1)
        sec_skin.body_layout.addLayout(skin_row)

        self.green_screen_check = QCheckBox("Green Screen Effect (For Streamers)")
        self.green_screen_check.setStyleSheet("color: #22C55E; font-weight: 600;")
        self.green_screen_check.toggled.connect(self.live_controller.set_green_screen)
        sec_skin.body_layout.addWidget(self.green_screen_check)
        self._register_section(sec_skin, right_col)

        right_col.addStretch(1)
        root.addLayout(right_col, 6)

        # Abrir "Actions" por defecto
        self._open_section("actions")

        # Señales
        self.ctx.active_state_changed.connect(self._on_state_changed)
        self.ctx.profile_applied.connect(lambda p: self._load_from_settings(p.mapping))
        if self.ctx.lighting_engine is not None:
            self.ctx.lighting_engine.live_color_changed.connect(self.live_controller.set_led_color)

        self._load_from_settings(self.ctx.mapping)

    def _register_section(self, sec: _AccordionSection, layout: QVBoxLayout) -> None:
        sec.toggled_open.connect(self._open_section)
        self._sections[sec.key] = sec
        layout.addWidget(sec)

    def _open_section(self, key: str) -> None:
        for k, sec in self._sections.items():
            sec.set_open(k == key)

    def _set_feedback_mode(self, virtual: bool) -> None:
        self._virtual_preview = virtual
        self.live_controller.set_virtual_mode(virtual)

    def _toggle_extended(self, checked: bool) -> None:
        self.ext_panel.setVisible(checked)
        self.ext_btn.setText("Input Extended  ⌃" if checked else "Input Extended  ⌄")

    def _on_state_changed(self, state: ControllerState) -> None:
        self._last_raw_state = state
        vsnap = map_dualsense_to_xinput(state, mapping=self.ctx.mapping)
        self.live_controller.set_state(state, vsnap)

        if self._virtual_preview:
            pressed_v = ", ".join(vsnap.pressed_labels()) or "(ninguno)"
            self.buttons_label.setText(f"[VIRTUAL XINPUT] Botones: {pressed_v}")
            self.sticks_label.setText(
                f"L: ({vsnap.left_x}, {vsnap.left_y}) · R: ({vsnap.right_x}, {vsnap.right_y}) · "
                f"LT: {vsnap.left_trigger} · RT: {vsnap.right_trigger}"
            )
        else:
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
            self.sticks_label.setText(
                f"L: ({state.left_stick.x}, {state.left_stick.y}) · "
                f"R: ({state.right_stick.x}, {state.right_stick.y}) · "
                f"L2: {state.l2_value} · R2: {state.r2_value}"
            )

        self.motion_label.setText(
            f"Giro (x,y,z): {state.gyro_x}, {state.gyro_y}, {state.gyro_z}\n"
            f"Accel (x,y,z): {state.accel_x}, {state.accel_y}, {state.accel_z}"
        )
        self.touchpad_label.setText(
            f"Touch 1: {'activo' if state.touch1.active else 'inactivo'} ({state.touch1.x}, {state.touch1.y}) · "
            f"Touch 2: {'activo' if state.touch2.active else 'inactivo'} ({state.touch2.x}, {state.touch2.y}) · "
            f"Clic: {'Sí' if state.touchpad_button else 'No'}"
        )

    def _load_from_settings(self, settings: MappingSettings) -> None:
        cfg = settings.clamp()
        remap = cfg.remap or {}
        for phys_key, combo in self._combos.items():
            target = remap.get(phys_key, DEFAULT_BUTTON_MAP[phys_key])
            idx = combo.findData(target)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        self.dz_left.set_value(int(round(cfg.deadzone_left * 100)))
        self.dz_right.set_value(int(round(cfg.deadzone_right * 100)))
        self.sens_left.set_value(int(round(cfg.sensitivity_left * 100)))
        self.sens_right.set_value(int(round(cfg.sensitivity_right * 100)))
        self.inv_left_x.setChecked(cfg.invert_left_x)
        self.inv_left_y.setChecked(cfg.invert_left_y)
        self.inv_right_x.setChecked(cfg.invert_right_x)
        self.inv_right_y.setChecked(cfg.invert_right_y)
        il = self.curve_left_combo.findData(cfg.curve_left)
        if il >= 0:
            self.curve_left_combo.setCurrentIndex(il)
        ir = self.curve_right_combo.findData(cfg.curve_right)
        if ir >= 0:
            self.curve_right_combo.setCurrentIndex(ir)
        self._offset_lx = cfg.offset_left_x
        self._offset_ly = cfg.offset_left_y
        self._offset_rx = cfg.offset_right_x
        self._offset_ry = cfg.offset_right_y
        self.drift_status_lbl.setText(
            f"Calibración anti-drift: L({self._offset_lx:+d}, {self._offset_ly:+d}) · R({self._offset_rx:+d}, {self._offset_ry:+d})"
        )
        kb_map = cfg.key_bindings or {}
        turbo_set = set(cfg.turbo_buttons or [])
        for phys_key, kb_combo in self._kb_combos.items():
            ki = kb_combo.findData(kb_map.get(phys_key, "none"))
            if ki >= 0:
                kb_combo.setCurrentIndex(ki)
        for phys_key, t_chk in self._turbo_checks.items():
            t_chk.setChecked(phys_key in turbo_set)
        self.turbo_rate_slider.set_value(int(round(cfg.turbo_rate_hz)))

        self.trig_dz_l2.set_value(int(round(cfg.trigger_deadzone_l2 * 100)))
        self.trig_dz_r2.set_value(int(round(cfg.trigger_deadzone_r2 * 100)))
        self.hair_l2_check.setChecked(cfg.hair_trigger_l2)
        self.hair_r2_check.setChecked(cfg.hair_trigger_r2)
        self.hair_thr_slider.set_value(int(round(cfg.hair_trigger_threshold * 100)))
        self.rapid_l2_check.setChecked(cfg.rapid_trigger_l2)
        self.rapid_r2_check.setChecked(cfg.rapid_trigger_r2)
        self.rapid_rel_slider.set_value(int(round(cfg.rapid_trigger_release * 100)))
        self.ds_thr_slider.set_value(int(round(cfg.dual_stage_threshold * 100)))
        i_dl2 = self.ds_l2_combo.findData(cfg.dual_stage_l2_action)
        if i_dl2 >= 0:
            self.ds_l2_combo.setCurrentIndex(i_dl2)
        i_dr2 = self.ds_r2_combo.findData(cfg.dual_stage_r2_action)
        if i_dr2 >= 0:
            self.ds_r2_combo.setCurrentIndex(i_dr2)

        self.gyro_stick_check.setChecked(cfg.gyro_to_stick_enabled)
        ia = self.gyro_act_combo.findData(cfg.gyro_activation)
        if ia >= 0:
            self.gyro_act_combo.setCurrentIndex(ia)
        iax = self.gyro_axis_combo.findData(cfg.gyro_horizontal_axis)
        if iax >= 0:
            self.gyro_axis_combo.setCurrentIndex(iax)
        self.gyro_dz_slider.set_value(cfg.gyro_deadzone)
        self.gyro_smooth_slider.set_value(int(round(cfg.gyro_smoothing * 100)))
        self.gyro_stick_sens.set_value(int(round(cfg.gyro_to_stick_sensitivity * 100)))
        self.gyro_stick_inv_x.setChecked(cfg.gyro_to_stick_invert_x)
        self.gyro_stick_inv_y.setChecked(cfg.gyro_to_stick_invert_y)

    def _read_from_ui(self) -> MappingSettings:
        remap = {}
        for phys_key, combo in self._combos.items():
            target = combo.currentData()
            if target != DEFAULT_BUTTON_MAP[phys_key]:
                remap[phys_key] = target

        return MappingSettings(
            remap=remap,
            deadzone_left=self.dz_left.value() / 100.0,
            deadzone_right=self.dz_right.value() / 100.0,
            sensitivity_left=self.sens_left.value() / 100.0,
            sensitivity_right=self.sens_right.value() / 100.0,
            invert_left_x=self.inv_left_x.isChecked(),
            invert_left_y=self.inv_left_y.isChecked(),
            invert_right_x=self.inv_right_x.isChecked(),
            invert_right_y=self.inv_right_y.isChecked(),
            curve_left=str(self.curve_left_combo.currentData() or "linear"),
            curve_right=str(self.curve_right_combo.currentData() or "linear"),
            offset_left_x=self._offset_lx,
            offset_left_y=self._offset_ly,
            offset_right_x=self._offset_rx,
            offset_right_y=self._offset_ry,
            gyro_to_stick_enabled=self.gyro_stick_check.isChecked(),
            gyro_to_stick_only_when_l2=(str(self.gyro_act_combo.currentData() or "l2") == "l2"),
            gyro_activation=str(self.gyro_act_combo.currentData() or "l2"),
            gyro_horizontal_axis=str(self.gyro_axis_combo.currentData() or "yaw"),
            gyro_deadzone=int(self.gyro_dz_slider.value()),
            gyro_smoothing=self.gyro_smooth_slider.value() / 100.0,
            gyro_to_stick_sensitivity=self.gyro_stick_sens.value() / 100.0,
            gyro_to_stick_invert_x=self.gyro_stick_inv_x.isChecked(),
            gyro_to_stick_invert_y=self.gyro_stick_inv_y.isChecked(),
            trigger_deadzone_l2=self.trig_dz_l2.value() / 100.0,
            trigger_deadzone_r2=self.trig_dz_r2.value() / 100.0,
            hair_trigger_l2=self.hair_l2_check.isChecked(),
            hair_trigger_r2=self.hair_r2_check.isChecked(),
            hair_trigger_threshold=self.hair_thr_slider.value() / 100.0,
            rapid_trigger_l2=self.rapid_l2_check.isChecked(),
            rapid_trigger_r2=self.rapid_r2_check.isChecked(),
            rapid_trigger_release=self.rapid_rel_slider.value() / 100.0,
            dual_stage_threshold=self.ds_thr_slider.value() / 100.0,
            dual_stage_l2_action=str(self.ds_l2_combo.currentData() or "none"),
            dual_stage_r2_action=str(self.ds_r2_combo.currentData() or "none"),
            turbo_buttons=[k for k, chk in self._turbo_checks.items() if chk.isChecked()],
            turbo_rate_hz=float(self.turbo_rate_slider.value()),
            key_bindings={k: str(cb.currentData()) for k, cb in self._kb_combos.items() if cb.currentData() and cb.currentData() != "none"},
        ).clamp()

    def _apply_mapping(self) -> None:
        settings = self._read_from_ui()
        self.ctx.apply_mapping(settings)
        QMessageBox.information(
            self,
            "Controller Mappings aplicado",
            "Configuración aplicada correctamente. Recuerda guardarla en Profiles si deseas conservarla por juego.",
        )

    def _reset_defaults(self) -> None:
        default_cfg = MappingSettings()
        self._load_from_settings(default_cfg)
        self.ctx.apply_mapping(default_cfg)

    def _on_macros_toggled(self, checked: bool) -> None:
        self.ctx.macro_service.enabled = bool(checked)
        self.ctx.save_settings()

    def _on_macro_changed(self, combo_key: str, action_key: str) -> None:
        self.ctx.macro_service.macros[combo_key] = str(action_key or "none")
        self.ctx.save_settings()

    def _calibrate_center(self) -> None:
        s = self._last_raw_state
        self._offset_lx = max(-40, min(40, 128 - int(s.left_stick.x)))
        self._offset_ly = max(-40, min(40, 128 - int(s.left_stick.y)))
        self._offset_rx = max(-40, min(40, 128 - int(s.right_stick.x)))
        self._offset_ry = max(-40, min(40, 128 - int(s.right_stick.y)))
        self.drift_status_lbl.setText(
            f"Calibración anti-drift: L({self._offset_lx:+d}, {self._offset_ly:+d}) · R({self._offset_rx:+d}, {self._offset_ry:+d})"
        )
        self.ctx.apply_mapping(self._read_from_ui())
        QMessageBox.information(
            self,
            "Calibración Anti-Drift aplicada",
            f"Centro calibrado con compensación L({self._offset_lx:+d}, {self._offset_ly:+d}) y "
            f"R({self._offset_rx:+d}, {self._offset_ry:+d}).",
        )

    def _clear_calibration(self) -> None:
        self._offset_lx = self._offset_ly = self._offset_rx = self._offset_ry = 0
        self.drift_status_lbl.setText("Calibración anti-drift: L(+0, +0) · R(+0, +0)")
        self.ctx.apply_mapping(self._read_from_ui())

    def _on_gyro_pro_changed(self, *_args) -> None:
        act = str(self.gyro_act_combo.currentData() or "l2")
        axis = str(self.gyro_axis_combo.currentData() or "yaw")
        self.ctx.touchpad_mouse.gyro_activation = act
        self.ctx.touchpad_mouse.gyro_only_when_l2 = (act == "l2")
        self.ctx.touchpad_mouse.gyro_horizontal_axis = axis
        self.ctx.touchpad_mouse.gyro_deadzone = int(self.gyro_dz_slider.value())
        self.ctx.touchpad_mouse.gyro_smoothing = self.gyro_smooth_slider.value() / 100.0

    def _apply_dual_stage_stop(self) -> None:
        self.ctx.apply_mapping(self._read_from_ui())
        self.ctx.apply_dual_stage_tactile_stop("BOTH")
        QMessageBox.information(
            self,
            "Tope táctil Dual Stage aplicado",
            "Se configuró un clic táctil físico en L2 y R2 justo antes del umbral Dual Stage.",
        )
