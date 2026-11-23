"""Servidor UDP compatible con el protocolo de mods DSX (puerto 6969 por defecto).

Permite que mods de juegos de PC diseñados para comunicarse vía UDP (como ``DSX.asi``,
mods de Cyberpunk 2077, GTA V, etc.) envíen instrucciones JSON a Dualless en tiempo
real para controlar los gatillos adaptativos (L2/R2), la barra LED RGB y los LEDs de
jugador del Sony DualSense.

Implementación 100% original usando únicamente la biblioteca estándar de Python
(``socket``, ``json``, ``threading``) + señales Qt para aplicar cambios de forma segura
en el hilo principal.
"""

from __future__ import annotations

import datetime
import json
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from dualcontrol.models import (
    ConnectionState,
    LightingSettings,
    TriggerMode,
    TriggerSettings,
)


def _clamp(val: Any, lo: int = 0, hi: int = 255) -> int:
    try:
        return max(lo, min(hi, int(val)))
    except (TypeError, ValueError):
        return lo


def _scale_0_8(val: Any) -> int:
    """Escala un valor típico de DSX (0..8) al rango de byte (0..255).
    Si el mod ya envía un valor > 8, se asume que viene en rango 0..255."""
    v = _clamp(val, 0, 255)
    if v <= 8:
        return int(round((v / 8.0) * 255))
    return v


def _parse_trigger_side(raw: Any) -> Optional[str]:
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("1", "left", "l2"):
            return "L2"
        if s in ("2", "right", "r2"):
            return "R2"
        return None
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return None
    if idx == 1:
        return "L2"
    if idx == 2:
        return "R2"
    return None


_DSX_TRIGGER_MODE_BY_NAME = {
    "normal": 0,
    "off": 0,
    "gamecube": 1,
    "verysoft": 2,
    "soft": 3,
    "hard": 4,
    "veryhard": 5,
    "hardest": 6,
    "rigid": 7,
    "vibratetrigger": 8,
    "choppy": 9,
    "medium": 10,
    "vibratetriggerpulse": 11,
    "customtriggervalue": 12,
    "resistance": 13,
    "bow": 14,
    "galloping": 15,
    "semiautomaticgun": 16,
    "automaticgun": 17,
    "machine": 18,
}

_CUSTOM_MODE_MAP = {
    0: TriggerMode.OFF,
    1: TriggerMode.RIGID,
    2: TriggerMode.RIGID_A,
    3: TriggerMode.RIGID_B,
    4: TriggerMode.RIGID_AB,
    5: TriggerMode.PULSE,
    6: TriggerMode.PULSE_A,
    7: TriggerMode.PULSE_B,
    8: TriggerMode.PULSE_AB,
    # Modos extendidos de vibración -> mapeados a PULSE_AB / RIGID_AB
    9: TriggerMode.RIGID_AB,
    10: TriggerMode.RIGID_B,
    11: TriggerMode.RIGID_AB,
    12: TriggerMode.PULSE_AB,
    13: TriggerMode.PULSE_A,
    14: TriggerMode.PULSE_B,
    15: TriggerMode.PULSE_AB,
}


def _dsx_trigger_to_settings(mode_raw: Any, extra: List[Any]) -> Tuple[TriggerSettings, str]:
    """Traduce un modo de gatillo DSX + parámetros extra a TriggerSettings."""
    if isinstance(mode_raw, str):
        mode_id = _DSX_TRIGGER_MODE_BY_NAME.get(mode_raw.strip().lower(), 0)
    else:
        mode_id = _clamp(mode_raw, 0, 32)

    p = [_clamp(x, 0, 255) for x in extra]

    def g(idx: int, default: int = 0) -> int:
        return p[idx] if idx < len(p) else default

    if mode_id == 0:  # Normal / Off
        return TriggerSettings(enabled=False, mode=TriggerMode.OFF, forces=[0] * 7, preset_name="dsx_normal"), "Normal"

    if mode_id == 1:  # GameCube
        return TriggerSettings(enabled=True, mode=TriggerMode.PULSE, forces=[144, 160, 255, 0, 0, 0, 0], preset_name="dsx_gamecube"), "GameCube"

    if mode_id == 2:  # VerySoft
        return TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[0, 40, 0, 0, 0, 0, 0], preset_name="dsx_verysoft"), "VerySoft"

    if mode_id == 3:  # Soft
        return TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[0, 80, 0, 0, 0, 0, 0], preset_name="dsx_soft"), "Soft"

    if mode_id == 4:  # Hard
        return TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[0, 185, 0, 0, 0, 0, 0], preset_name="dsx_hard"), "Hard"

    if mode_id == 5:  # VeryHard
        return TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[0, 225, 0, 0, 0, 0, 0], preset_name="dsx_veryhard"), "VeryHard"

    if mode_id == 6:  # Hardest
        return TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[0, 255, 0, 0, 0, 0, 0], preset_name="dsx_hardest"), "Hardest"

    if mode_id == 7:  # Rigid
        forces = [g(0, 0), g(1, 255), g(2, 0), g(3, 0), g(4, 0), g(5, 0), g(6, 0)]
        return TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=forces, preset_name="dsx_rigid"), "Rigid"

    if mode_id == 8:  # VibrateTrigger
        freq = g(0, 10)
        amp = g(1, 180)
        start = g(2, 0)
        return TriggerSettings(
            enabled=True, mode=TriggerMode.PULSE_AB,
            forces=[freq, amp, start, 0, 0, 0, 0], preset_name="dsx_vibrate",
        ), f"VibrateTrigger(freq={freq}, amp={amp})"

    if mode_id == 9:  # Choppy
        return TriggerSettings(
            enabled=True, mode=TriggerMode.RIGID_AB,
            forces=[2, 200, 4, 200, 6, 200, 0], preset_name="dsx_choppy",
        ), "Choppy"

    if mode_id == 10:  # Medium
        return TriggerSettings(enabled=True, mode=TriggerMode.RIGID, forces=[0, 130, 0, 0, 0, 0, 0], preset_name="dsx_medium"), "Medium"

    if mode_id == 11:  # VibrateTriggerPulse
        return TriggerSettings(
            enabled=True, mode=TriggerMode.PULSE_AB,
            forces=[2, 220, 30, 0, 0, 0, 0], preset_name="dsx_vibrate_pulse",
        ), "VibrateTriggerPulse"

    if mode_id == 12:  # CustomTriggerValue
        custom_mode_id = g(0, 0)
        t_mode = _CUSTOM_MODE_MAP.get(custom_mode_id, TriggerMode.RIGID)
        forces = [g(i + 1, 0) for i in range(7)]
        return TriggerSettings(
            enabled=t_mode != TriggerMode.OFF, mode=t_mode, forces=forces, preset_name="dsx_custom",
        ), f"Custom(mode={t_mode.value})"

    if mode_id == 13:  # Resistance (start 0-8, force 0-8)
        start = g(0, 0)
        force = _scale_0_8(g(1, 4))
        return TriggerSettings(
            enabled=force > 0, mode=TriggerMode.RIGID,
            forces=[start, force, 0, 0, 0, 0, 0], preset_name="dsx_resistance",
        ), f"Resistance(start={start}, force={g(1, 4)})"

    if mode_id == 14:  # Bow (start, end, force, snapForce)
        start = g(0, 1)
        end = g(1, 6)
        force = _scale_0_8(g(2, 4))
        snap = _scale_0_8(g(3, 6))
        return TriggerSettings(
            enabled=True, mode=TriggerMode.PULSE_A,
            forces=[start, force, end, snap, 0, 0, 0], preset_name="dsx_bow",
        ), f"Bow(start={start}, end={end})"

    if mode_id == 15:  # Galloping (start, end, firstFoot, secondFoot, freq)
        start = g(0, 0)
        end = g(1, 8)
        f1 = g(2, 2)
        f2 = g(3, 6)
        freq = g(4, 10)
        return TriggerSettings(
            enabled=True, mode=TriggerMode.PULSE_AB,
            forces=[start, end, f1, f2, freq, 0, 0], preset_name="dsx_galloping",
        ), f"Galloping(freq={freq})"

    if mode_id == 16:  # SemiAutomaticGun / Weapon (start, end, force)
        start = g(0, 2)
        end = g(1, 6)
        force = _scale_0_8(g(2, 8))
        return TriggerSettings(
            enabled=True, mode=TriggerMode.PULSE,
            forces=[start, force, end, 0, 0, 0, 0], preset_name="dsx_weapon",
        ), f"SemiAutomaticGun(start={start}, end={end}, force={g(2, 8)})"

    if mode_id == 17:  # AutomaticGun (start, strength, frequency)
        start = g(0, 1)
        strength = _scale_0_8(g(1, 6))
        freq = g(2, 25)
        return TriggerSettings(
            enabled=True, mode=TriggerMode.PULSE_AB,
            forces=[freq, strength, start, 0, 0, 0, 0], preset_name="dsx_autogun",
        ), f"AutomaticGun(start={start}, strength={g(1, 6)}, freq={freq})"

    if mode_id == 18:  # Machine (start, end, strengthA, strengthB, freq, period)
        start = g(0, 1)
        end = g(1, 8)
        str_a = _scale_0_8(g(2, 5))
        str_b = _scale_0_8(g(3, 7))
        freq = g(4, 30)
        period = g(5, 1)
        return TriggerSettings(
            enabled=True, mode=TriggerMode.PULSE_AB,
            forces=[freq, str_a, start, end, str_b, period, 0], preset_name="dsx_machine",
        ), f"Machine(freq={freq})"

    return TriggerSettings(enabled=False, mode=TriggerMode.OFF, forces=[0] * 7), f"Mode({mode_id})"


@dataclass
class DsxCommand:
    kind: str  # "trigger", "rgb", "player_led", "reset"
    summary: str
    side: Optional[str] = None
    trigger: Optional[TriggerSettings] = None
    rgb: Optional[Tuple[int, int, int]] = None
    player_led: Optional[int] = None


def parse_dsx_packet(raw: bytes | str) -> List[DsxCommand]:
    """Decodifica un paquete JSON enviado por un mod compatible con DSX UDP."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else raw
    text = text.strip().rstrip("\x00")
    if not text:
        return []

    payload = json.loads(text)
    if not isinstance(payload, dict):
        return []

    # Aceptar "instructions" o "Instructions"
    instructions = payload.get("instructions")
    if instructions is None:
        instructions = payload.get("Instructions")
    if not isinstance(instructions, list):
        return []

    commands: List[DsxCommand] = []
    for item in instructions:
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        if itype is None:
            itype = item.get("Type")
        params = item.get("parameters")
        if params is None:
            params = item.get("Parameters")
        if not isinstance(params, list):
            params = []

        try:
            itype_int = int(itype)
        except (TypeError, ValueError):
            continue

        if itype_int == 1 and len(params) >= 3:
            side = _parse_trigger_side(params[1])
            if side is None:
                continue
            settings, desc = _dsx_trigger_to_settings(params[2], params[3:])
            commands.append(
                DsxCommand(kind="trigger", side=side, trigger=settings, summary=f"{side} -> {desc}")
            )
        elif itype_int == 2 and len(params) >= 4:
            r, g_c, b = _clamp(params[1]), _clamp(params[2]), _clamp(params[3])
            commands.append(
                DsxCommand(kind="rgb", rgb=(r, g_c, b), summary=f"RGB -> ({r}, {g_c}, {b})")
            )
        elif itype_int == 3 and len(params) >= 6:
            count = sum(1 for v in params[1:6] if bool(v))
            commands.append(
                DsxCommand(kind="player_led", player_led=count, summary=f"PlayerLED -> {count}")
            )
        elif itype_int == 6 and len(params) >= 2:
            count = _clamp(params[1], 0, 5)
            commands.append(
                DsxCommand(kind="player_led", player_led=count, summary=f"PlayerLED -> {count}")
            )
        elif itype_int == 7:
            commands.append(DsxCommand(kind="reset", summary="ResetToUserSettings"))

    return commands


def build_test_weapon_packet(side: str = "R2") -> bytes:
    """Genera un paquete JSON de prueba en formato DSX (SemiAutomaticGun)."""
    trig = 2 if side == "R2" else 1
    payload = {
        "instructions": [
            {"type": 1, "parameters": [0, trig, 16, 2, 6, 8]},
            {"type": 2, "parameters": [0, 46, 107, 255]},
        ]
    }
    return json.dumps(payload).encode("utf-8")


# --- Servicio Qt (solo se importa PySide6 si se instancia DsxUdpServer) --------
try:
    from PySide6.QtCore import QObject, Signal

    class DsxUdpServer(QObject):
        """Escucha paquetes UDP de mods DSX en segundo plano y los aplica en Qt."""

        _commands_ready = Signal(object, str)  # list[DsxCommand], source_addr
        packet_logged = Signal(str)
        status_changed = Signal(bool, str)
        error_occurred = Signal(str)
        packet_count_changed = Signal(int)

        def __init__(self, controller_service, lighting_getter=None, parent: Optional[QObject] = None) -> None:
            super().__init__(parent)
            self._controller_service = controller_service
            self._lighting_getter = lighting_getter
            self._lighting = LightingSettings()
            self._port = 6969
            self._host = "127.0.0.1"
            self._running = False
            self._sock: Optional[socket.socket] = None
            self._thread: Optional[threading.Thread] = None
            self._stop_event = threading.Event()
            self._packet_count = 0

            self._commands_ready.connect(self._apply_commands_main_thread)

        @property
        def is_running(self) -> bool:
            return self._running

        @property
        def port(self) -> int:
            return self._port

        @property
        def packet_count(self) -> int:
            return self._packet_count

        def start(self, port: int = 6969, host: str = "127.0.0.1") -> bool:
            if self._running:
                self.stop()

            self._port = int(port)
            self._host = host
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(0.25)
            try:
                sock.bind((self._host, self._port))
            except OSError as exc:
                sock.close()
                msg = f"No se pudo abrir el puerto UDP {self._port}: {exc}"
                self.error_occurred.emit(msg)
                self.status_changed.emit(False, msg)
                return False

            self._sock = sock
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._listen_loop,
                name=f"Dualless-UDP-{self._port}",
                daemon=True,
            )
            self._thread.start()
            self.status_changed.emit(True, f"Escuchando en {self._host}:{self._port}")
            return True

        def stop(self) -> None:
            self._stop_event.set()
            self._running = False
            sock = self._sock
            self._sock = None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=0.5)
            self._thread = None
            self.status_changed.emit(False, "Detenido")

        def send_self_test(self, side: str = "R2") -> bool:
            """Envía un paquete UDP de prueba al propio servidor local."""
            if not self._running:
                return False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                    client.sendto(build_test_weapon_packet(side), (self._host, self._port))
                return True
            except OSError as exc:
                self.error_occurred.emit(f"Error en prueba UDP: {exc}")
                return False

        def _listen_loop(self) -> None:
            while not self._stop_event.is_set():
                sock = self._sock
                if sock is None:
                    break
                try:
                    data, addr = sock.recvfrom(8192)
                except socket.timeout:
                    continue
                except OSError:
                    break

                try:
                    commands = parse_dsx_packet(data)
                except Exception as exc:
                    self.packet_logged.emit(f"[ERROR JSON desde {addr[0]}:{addr[1]}] {exc}")
                    continue

                if commands:
                    self._commands_ready.emit(commands, f"{addr[0]}:{addr[1]}")

                # Responder ACK compatible con DSX para que mods como DSX.asi confirmen conexión
                try:
                    conn_state = self._controller_service.backend.connection_state
                    connected = conn_state in (
                        ConnectionState.OPENED,
                        ConnectionState.INPUT_OK,
                        ConnectionState.OUTPUT_OK,
                    )
                    ack = {
                        "Status": "DSX Received UDP Instructions",
                        "TimeReceived": datetime.datetime.now().strftime("%H:%M:%S"),
                        "isControllerConnected": connected,
                        "BatteryLevel": 100,
                    }
                    sock.sendto(json.dumps(ack).encode("utf-8"), addr)
                except OSError:
                    pass

        def _apply_commands_main_thread(self, commands: List[DsxCommand], source: str) -> None:
            self._packet_count += 1
            self.packet_count_changed.emit(self._packet_count)

            if self._lighting_getter is not None:
                self._lighting = self._lighting_getter()

            summaries: List[str] = []
            for cmd in commands:
                summaries.append(cmd.summary)
                if cmd.kind == "trigger" and cmd.side and cmd.trigger is not None:
                    self._controller_service.apply_trigger(cmd.side, cmd.trigger)
                elif cmd.kind == "rgb" and cmd.rgb is not None:
                    self._lighting.red, self._lighting.green, self._lighting.blue = cmd.rgb
                    self._controller_service.apply_lighting(self._lighting)
                elif cmd.kind == "player_led" and cmd.player_led is not None:
                    self._lighting.player_led = cmd.player_led
                    self._controller_service.apply_lighting(self._lighting)
                elif cmd.kind == "reset":
                    self._controller_service.restore_defaults()

            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.packet_logged.emit(f"[{ts}] ({source}) " + " | ".join(summaries))

except ImportError:
    DsxUdpServer = None  # type: ignore
