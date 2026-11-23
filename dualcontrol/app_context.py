from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from dualcontrol.backend.base import BackendError
from dualcontrol.backend.simulated import SimulatedBackend
from dualcontrol.models import (
    AudioSettings,
    ConnectionState,
    HapticSettings,
    LightingSettings,
    MappingSettings,
    Profile,
    TriggerSettings,
)
from dualcontrol.services.audio_rumble import AudioToRumbleService
from dualcontrol.services.controller_service import ControllerService
from dualcontrol.services.dsx_udp import DsxUdpServer
from dualcontrol.services.game_watcher import GameProfileWatcher
from dualcontrol.services.hidhide_service import HidHideService
from dualcontrol.services.keyboard_mapper import KeyboardMouseMapperService
from dualcontrol.services.lighting_engine import LightingEffectController
from dualcontrol.services.macro_service import MacroService
from dualcontrol.services.mod_portal import ModPortalManager
from dualcontrol.services.profile_manager import ProfileManager
from dualcontrol.services.settings_store import AppSettings, SettingsStore
from dualcontrol.services.touchpad_mouse import TouchpadGyroMouseService
from dualcontrol.services.virtual_controller_service import VirtualControllerService
from dualcontrol.virtualcontroller.base import VirtualControllerMode


@dataclass
class ControllerSlot:
    """Representa un puesto de jugador (P1..P4) con su propio servicio HID,
    mando virtual ViGEmBus, motor LED y configuración independiente."""

    slot_index: int
    controller_service: ControllerService
    virtual_controller_service: VirtualControllerService
    lighting_engine: Optional[LightingEffectController] = None
    using_real_backend: bool = False
    device_path: str = ""
    trigger_l2: TriggerSettings = field(default_factory=TriggerSettings)
    trigger_r2: TriggerSettings = field(default_factory=TriggerSettings)
    haptics: HapticSettings = field(default_factory=HapticSettings)
    lighting: LightingSettings = field(default_factory=LightingSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    mapping: MappingSettings = field(default_factory=MappingSettings)
    current_profile_name: Optional[str] = None


class AppContext(QObject):
    """Estado compartido entre páginas de la interfaz. Sección 13: ninguna página
    toca el backend directamente; todas pasan por aquí / por ControllerService."""

    profile_applied = Signal(object)          # Profile
    mapping_changed = Signal(object)          # MappingSettings
    backend_changed = Signal(bool)            # True = Real (USB/BT), False = Simulado
    diagnostics_updated = Signal()
    slot_changed = Signal(int, int)           # active_slot (0..3), total_real_connected
    active_state_changed = Signal(object)     # ControllerState del slot activo
    active_connection_changed = Signal(object)  # ConnectionState del slot activo
    audio_changed = Signal(object)              # AudioSettings del slot activo

    AUTO_DETECT_INTERVAL_MS = 2000
    MAX_SLOTS = 4

    def __init__(self, profiles_dir: Path) -> None:
        super().__init__()
        self.profile_manager = ProfileManager(profiles_dir)
        self.mod_portal = ModPortalManager(profiles_dir, self.profile_manager)
        self.settings_store = SettingsStore(Path(profiles_dir).parent / "settings.json")
        saved = self.settings_store.load()
        self._saved_settings = saved

        self.auto_detect_enabled = saved.auto_detect_enabled
        self.auto_hidhide = saved.auto_hidhide
        self.minimize_to_tray = saved.minimize_to_tray
        self.low_battery_alerts = saved.low_battery_alerts
        self.active_slot: int = 0
        self.physical_triggers_tested = False
        self.reconnection_verified = False
        self._had_disconnect = False

        # Crear 4 slots simultáneos (P1..P4)
        self.slots: List[ControllerSlot] = []
        for idx in range(self.MAX_SLOTS):
            cs = ControllerService(SimulatedBackend(), parent=self)
            le = LightingEffectController(cs, parent=self) if LightingEffectController is not None else None
            light_cfg = LightingSettings(player_led=idx + 1)
            if le is not None:
                le.set_settings(light_cfg)
            audio_cfg = AudioSettings(
                speaker_volume=saved.speaker_volume,
                headphone_volume=saved.headphone_volume,
                mic_volume=saved.mic_volume,
                speaker_enabled=saved.speaker_enabled,
                sync_windows_mute=saved.sync_windows_mute,
            ).clamp()
            vcs = VirtualControllerService(
                cs,
                lighting_getter=lambda s_idx=idx: self.slots[s_idx].lighting,
                triggers_restore_cb=lambda s_idx=idx: self._restore_slot_triggers(s_idx),
                parent=self,
            )
            vcs.set_rumble_to_triggers(saved.rumble_to_triggers)
            vcs.set_rumble_to_triggers_strength(saved.rumble_to_triggers_strength)
            vcs.set_led_passthrough(saved.ds4_led_passthrough)
            slot = ControllerSlot(
                slot_index=idx,
                controller_service=cs,
                virtual_controller_service=vcs,
                lighting_engine=le,
                lighting=light_cfg,
                audio=audio_cfg,
            )
            self.slots.append(slot)

            cs.state_changed.connect(lambda st, s_idx=idx: self._on_slot_state(s_idx, st))
            cs.connection_changed.connect(lambda cst, s_idx=idx: self._on_slot_connection(s_idx, cst))
            vcs.mode_changed.connect(lambda m_val, s_idx=idx: self._on_slot_virtual_mode(s_idx, m_val))

        self.hidhide_service = HidHideService(self)

        self.udp_server = (
            DsxUdpServer(self.slots[0].controller_service, lighting_getter=lambda: self.lighting)
            if DsxUdpServer is not None
            else None
        )

        self.touchpad_mouse = TouchpadGyroMouseService(None)
        self.touchpad_mouse.touchpad_mouse_enabled = saved.touchpad_mouse_enabled
        self.touchpad_mouse.touchpad_sensitivity = saved.touchpad_sensitivity
        self.touchpad_mouse.gyro_mouse_enabled = saved.gyro_mouse_enabled
        self.touchpad_mouse.gyro_only_when_l2 = saved.gyro_only_when_l2
        self.touchpad_mouse.gyro_activation = saved.gyro_activation
        self.touchpad_mouse.gyro_horizontal_axis = saved.gyro_horizontal_axis
        self.touchpad_mouse.gyro_deadzone = saved.gyro_deadzone
        self.touchpad_mouse.gyro_smoothing = saved.gyro_smoothing
        self.touchpad_mouse.gyro_sensitivity = saved.gyro_sensitivity
        self.active_state_changed.connect(self.touchpad_mouse.process_state)

        self.audio_rumble = AudioToRumbleService(self.slots[0].controller_service, lambda: self.haptics)
        self.game_watcher = GameProfileWatcher(self.profile_manager, self.apply_profile)
        self.game_watcher.set_enabled(saved.game_watcher_enabled)

        self.macro_service = MacroService(None, next_profile_cb=self.cycle_next_profile)
        self.macro_service.enabled = saved.macros_enabled
        self.macro_service.macros = dict(saved.macros)
        self.active_state_changed.connect(self.macro_service.process_state)

        self.keyboard_mapper = KeyboardMouseMapperService(
            lambda: self.mapping,
            on_mute_hardware_toggle=self.toggle_mic_mute_hardware,
            parent=self,
        )
        self.keyboard_mapper.sync_windows_mute = saved.sync_windows_mute
        self.active_state_changed.connect(self.keyboard_mapper.process_state)

        self._auto_detect_timer = QTimer(self)
        self._auto_detect_timer.timeout.connect(self._auto_detect_tick)

    # --- Propiedades dinámicas apuntando al slot activo (P1..P4) ---------------
    @property
    def current_slot(self) -> ControllerSlot:
        return self.slots[self.active_slot]

    @property
    def controller_service(self) -> ControllerService:
        return self.current_slot.controller_service

    @property
    def virtual_controller_service(self) -> VirtualControllerService:
        return self.current_slot.virtual_controller_service

    @property
    def lighting_engine(self) -> Optional[LightingEffectController]:
        return self.current_slot.lighting_engine

    @property
    def using_real_backend(self) -> bool:
        return self.current_slot.using_real_backend

    @using_real_backend.setter
    def using_real_backend(self, value: bool) -> None:
        self.current_slot.using_real_backend = bool(value)

    @property
    def trigger_l2(self) -> TriggerSettings:
        return self.current_slot.trigger_l2

    @trigger_l2.setter
    def trigger_l2(self, value: TriggerSettings) -> None:
        self.current_slot.trigger_l2 = value

    @property
    def trigger_r2(self) -> TriggerSettings:
        return self.current_slot.trigger_r2

    @trigger_r2.setter
    def trigger_r2(self, value: TriggerSettings) -> None:
        self.current_slot.trigger_r2 = value

    @property
    def haptics(self) -> HapticSettings:
        return self.current_slot.haptics

    @haptics.setter
    def haptics(self, value: HapticSettings) -> None:
        self.current_slot.haptics = value

    @property
    def lighting(self) -> LightingSettings:
        return self.current_slot.lighting

    @lighting.setter
    def lighting(self, value: LightingSettings) -> None:
        self.current_slot.lighting = value

    @property
    def audio(self) -> AudioSettings:
        return self.current_slot.audio

    @audio.setter
    def audio(self, value: AudioSettings) -> None:
        self.current_slot.audio = value

    @property
    def mapping(self) -> MappingSettings:
        return self.current_slot.mapping

    @mapping.setter
    def mapping(self, value: MappingSettings) -> None:
        self.current_slot.mapping = value

    @property
    def current_profile_name(self) -> Optional[str]:
        return self.current_slot.current_profile_name

    @current_profile_name.setter
    def current_profile_name(self, value: Optional[str]) -> None:
        self.current_slot.current_profile_name = value

    # --- Enrutamiento de señales por slot --------------------------------------
    def _on_slot_state(self, slot_idx: int, state) -> None:
        if slot_idx == self.active_slot:
            self.active_state_changed.emit(state)

    def _on_slot_connection(self, slot_idx: int, state: ConnectionState) -> None:
        slot = self.slots[slot_idx]
        if slot.using_real_backend and state in (ConnectionState.ERROR, ConnectionState.NOT_DETECTED):
            self._had_disconnect = True
        if slot_idx == self.active_slot:
            self.active_connection_changed.emit(state)

    def _on_slot_virtual_mode(self, _slot_idx: int, _mode_val: str) -> None:
        """Sincroniza HidHide automáticamente cuando cualquier mando entra/sale de emulación Xbox/DS4."""
        if not self.auto_hidhide:
            return
        any_emulating = any(
            s.virtual_controller_service.mode in (VirtualControllerMode.XINPUT, VirtualControllerMode.DUALSHOCK4)
            for s in self.slots
        )
        if any_emulating:
            paths = [s.device_path for s in self.slots if s.using_real_backend and s.device_path]
            if paths and not self.hidhide_service.is_cloak_active:
                self.hidhide_service.hide_controllers(paths)
        else:
            if self.hidhide_service.is_cloak_active:
                self.hidhide_service.unhide_all()

    def _restore_slot_triggers(self, slot_idx: int) -> None:
        if 0 <= slot_idx < len(self.slots):
            slot = self.slots[slot_idx]
            slot.controller_service.apply_trigger("L2", slot.trigger_l2)
            slot.controller_service.apply_trigger("R2", slot.trigger_r2)

    def _restore_slot_state_to_hardware(self, slot: ControllerSlot) -> None:
        slot.controller_service.apply_trigger("L2", slot.trigger_l2)
        slot.controller_service.apply_trigger("R2", slot.trigger_r2)
        slot.controller_service.apply_haptics(slot.haptics)
        slot.controller_service.apply_audio(slot.audio)
        if slot.lighting_engine is not None:
            slot.lighting_engine.set_settings(slot.lighting)
        else:
            slot.controller_service.apply_lighting(slot.lighting)

    def _restore_active_state_to_hardware(self) -> None:
        self._restore_slot_state_to_hardware(self.current_slot)

    # --- HidHide y Double Input ------------------------------------------------
    def set_auto_hidhide(self, enabled: bool) -> None:
        self.auto_hidhide = bool(enabled)
        if not self.auto_hidhide and self.hidhide_service.is_cloak_active:
            self.hidhide_service.unhide_all()
        elif self.auto_hidhide:
            self._on_slot_virtual_mode(self.active_slot, self.virtual_controller_service.mode.value)
        self.save_settings()

    def apply_hidhide_now(self) -> tuple[bool, str]:
        paths = [s.device_path for s in self.slots if s.using_real_backend and s.device_path]
        if not paths:
            devs = self.list_connected_controllers()
            paths = [d["path"] for d in devs if d.get("path")]
        ok = self.hidhide_service.hide_controllers(paths)
        if ok:
            return True, self.hidhide_service.check_status().summary
        return False, self.hidhide_service.last_error

    def fix_double_input_smart(self) -> str:
        """Reinicia la conexión del mando y, si HidHide está instalado y se usa emulación,
        oculta automáticamente el DualSense físico para eliminar el Double Input."""
        self.virtual_controller_service.fix_double_input()
        st = self.hidhide_service.check_status()
        if st.installed and self.virtual_controller_service.mode in (
            VirtualControllerMode.XINPUT,
            VirtualControllerMode.DUALSHOCK4,
        ):
            ok, msg = self.apply_hidhide_now()
            if ok:
                return f"Conexión reiniciada y HidHide activado: {msg}"
        return (
            "Se reinició la conexión del mando. Si algún juego sigue detectando doble entrada, "
            "instala/activa HidHide en Game Compatibility o cierra Steam Input."
        )

    # --- Pruebas de diagnóstico ------------------------------------------------
    def mark_physical_trigger_tested(self) -> None:
        if self.using_real_backend and self.controller_service.backend.connection_state == ConnectionState.OUTPUT_OK:
            if not self.physical_triggers_tested:
                self.physical_triggers_tested = True
                self.diagnostics_updated.emit()

    def test_physical_triggers_pulse(self) -> bool:
        from dualcontrol.models import TriggerMode

        test_cfg = TriggerSettings(enabled=True, mode=TriggerMode.PULSE, forces=[2, 230, 6, 0, 0, 0, 0], preset_name="weapon")
        self.trigger_l2 = test_cfg
        self.trigger_r2 = test_cfg
        self.controller_service.apply_trigger("L2", test_cfg)
        self.controller_service.apply_trigger("R2", test_cfg)
        if self.using_real_backend and self.controller_service.backend.connection_state == ConnectionState.OUTPUT_OK:
            self.physical_triggers_tested = True
            self.diagnostics_updated.emit()
            return True
        self.diagnostics_updated.emit()
        return False

    def test_reconnection_recovery(self) -> bool:
        self._had_disconnect = True
        self.controller_service.disconnect_controller()
        ok = self.controller_service.connect_controller()
        if ok:
            self._restore_active_state_to_hardware()
            self.reconnection_verified = True
            self._had_disconnect = False
        self.diagnostics_updated.emit()
        return ok

    # --- Persistencia y perfiles -----------------------------------------------
    def save_settings(self) -> None:
        cfg = AppSettings(
            auto_detect_enabled=self.auto_detect_enabled,
            auto_hidhide=self.auto_hidhide,
            minimize_to_tray=self.minimize_to_tray,
            low_battery_alerts=self.low_battery_alerts,
            game_watcher_enabled=self.game_watcher.enabled,
            last_virtual_mode=self.virtual_controller_service.mode.value,
            last_profile_name=self.current_profile_name or "",
            touchpad_mouse_enabled=self.touchpad_mouse.touchpad_mouse_enabled,
            touchpad_sensitivity=self.touchpad_mouse.touchpad_sensitivity,
            gyro_mouse_enabled=self.touchpad_mouse.gyro_mouse_enabled,
            gyro_only_when_l2=self.touchpad_mouse.gyro_only_when_l2,
            gyro_activation=self.touchpad_mouse.gyro_activation,
            gyro_horizontal_axis=self.touchpad_mouse.gyro_horizontal_axis,
            gyro_deadzone=self.touchpad_mouse.gyro_deadzone,
            gyro_smoothing=self.touchpad_mouse.gyro_smoothing,
            gyro_sensitivity=self.touchpad_mouse.gyro_sensitivity,
            macros_enabled=self.macro_service.enabled,
            macros=dict(self.macro_service.macros),
            speaker_volume=self.audio.speaker_volume,
            headphone_volume=self.audio.headphone_volume,
            mic_volume=self.audio.mic_volume,
            speaker_enabled=self.audio.speaker_enabled,
            sync_windows_mute=self.audio.sync_windows_mute,
            rumble_to_triggers=self.virtual_controller_service.rumble_to_triggers,
            rumble_to_triggers_strength=self.virtual_controller_service.rumble_to_triggers_strength,
            ds4_led_passthrough=self.virtual_controller_service.led_passthrough,
        )
        self.settings_store.save(cfg)

    def _load_all_profiles(self) -> list[Profile]:
        result: list[Profile] = []
        for item in self.profile_manager.list_profiles():
            try:
                result.append(self.profile_manager.load(item) if isinstance(item, str) else item)
            except Exception:
                continue
        return result

    def restore_saved_session(self) -> None:
        if self._saved_settings.last_profile_name:
            try:
                for p in self._load_all_profiles():
                    if p.name == self._saved_settings.last_profile_name:
                        self.apply_profile(p)
                        break
            except Exception:
                pass

    def cycle_next_profile(self) -> None:
        try:
            profiles = self._load_all_profiles()
        except Exception:
            return
        if not profiles:
            return
        names = [p.name for p in profiles]
        if self.current_profile_name in names:
            idx = (names.index(self.current_profile_name) + 1) % len(profiles)
        else:
            idx = 0
        self.apply_profile(profiles[idx])

    # --- Multi-Mando simultáneo (P1..P4) ---------------------------------------
    def list_connected_controllers(self) -> list[dict]:
        from dualcontrol.backend.real import list_connected_dualsense

        return list_connected_dualsense()

    def connected_real_count(self) -> int:
        return sum(
            1
            for s in self.slots
            if s.using_real_backend
            and s.controller_service.backend.connection_state
            in (ConnectionState.OPENED, ConnectionState.INPUT_OK, ConnectionState.OUTPUT_OK)
        )

    def slot_is_connected(self, slot_index: int) -> bool:
        if not (0 <= slot_index < self.MAX_SLOTS):
            return False
        s = self.slots[slot_index]
        return s.using_real_backend and s.controller_service.backend.connection_state in (
            ConnectionState.OPENED,
            ConnectionState.INPUT_OK,
            ConnectionState.OUTPUT_OK,
        )

    def select_controller_slot(self, slot_index: int) -> bool:
        """Cambia la vista de la UI al puesto P1..P4 sin detener los demás mandos activos."""
        slot_idx = max(0, min(self.MAX_SLOTS - 1, int(slot_index)))
        self.active_slot = slot_idx
        slot = self.slots[slot_idx]

        # Re-vincular servicios auxiliares al slot activo
        self.touchpad_mouse._controller_service = slot.controller_service
        self.audio_rumble._controller_service = slot.controller_service
        self.macro_service._controller_service = slot.controller_service

        # Asegurar LED de jugador correspondiente (1..4)
        if slot.lighting.player_led != slot_idx + 1:
            slot.lighting.player_led = slot_idx + 1
            self._restore_slot_state_to_hardware(slot)

        self.backend_changed.emit(slot.using_real_backend)
        self.active_connection_changed.emit(slot.controller_service.backend.connection_state)
        self.slot_changed.emit(slot_idx, self.connected_real_count())
        return self.slot_is_connected(slot_idx)

    def start_auto_detect(self) -> None:
        connected_real = self.try_auto_connect_real()
        if not connected_real and not self.slots[0].using_real_backend:
            self.slots[0].controller_service.connect_controller()
        if self.auto_detect_enabled and not self._auto_detect_timer.isActive():
            self._auto_detect_timer.start(self.AUTO_DETECT_INTERVAL_MS)
        self.restore_saved_session()
        self.game_watcher.start()

    def set_auto_detect(self, enabled: bool) -> None:
        self.auto_detect_enabled = bool(enabled)
        if self.auto_detect_enabled:
            if not self._auto_detect_timer.isActive():
                self._auto_detect_timer.start(self.AUTO_DETECT_INTERVAL_MS)
            self.try_auto_connect_real()
        else:
            self._auto_detect_timer.stop()

    def _auto_detect_tick(self) -> None:
        if not self.auto_detect_enabled:
            return
        self.try_auto_connect_real()

    def try_auto_connect_real(self) -> bool:
        """Detecta y mantiene conectados simultáneamente todos los DualSense físicos (P1..P4)."""
        from dualcontrol.backend.real import RealBackend, list_connected_dualsense

        devices = list_connected_dualsense()
        total_devs = min(self.MAX_SLOTS, len(devices))
        any_connected = False
        changed_active_backend = False

        for idx in range(self.MAX_SLOTS):
            slot = self.slots[idx]
            if idx < total_devs:
                dev_info = devices[idx]
                st = slot.controller_service.backend.connection_state
                is_live = slot.using_real_backend and st in (
                    ConnectionState.OPENED,
                    ConnectionState.INPUT_OK,
                    ConnectionState.OUTPUT_OK,
                )
                if is_live and slot.device_path == dev_info.get("path", ""):
                    any_connected = True
                    continue

                # Conectar o reconectar este slot en paralelo
                if slot.using_real_backend:
                    self._had_disconnect = True
                backend = RealBackend(device_index=idx)
                slot.using_real_backend = True
                slot.device_path = str(dev_info.get("path", ""))
                ok = slot.controller_service.set_backend(backend)
                if ok:
                    any_connected = True
                    slot.lighting.player_led = idx + 1
                    self._restore_slot_state_to_hardware(slot)
                    if self._had_disconnect:
                        self.reconnection_verified = True
                        self._had_disconnect = False
                    if idx == self.active_slot:
                        changed_active_backend = True
                else:
                    slot.using_real_backend = False
                    slot.device_path = ""
                    if idx == 0:
                        slot.controller_service.set_backend(SimulatedBackend())
            else:
                # No hay mando físico para este índice
                if slot.using_real_backend:
                    self._had_disconnect = True
                    slot.using_real_backend = False
                    slot.device_path = ""
                    if idx == 0:
                        slot.controller_service.set_backend(SimulatedBackend())
                        if self.active_slot == 0:
                            changed_active_backend = True
                    else:
                        slot.controller_service.disconnect_controller()

        if changed_active_backend:
            self.backend_changed.emit(self.using_real_backend)
            self.diagnostics_updated.emit()

        self.slot_changed.emit(self.active_slot, self.connected_real_count())
        return any_connected

    def switch_backend_manual(self, use_real: bool) -> bool:
        slot = self.current_slot
        if use_real:
            from dualcontrol.backend.real import RealBackend

            slot.using_real_backend = True
            connected = slot.controller_service.set_backend(RealBackend(device_index=self.active_slot))
            self.backend_changed.emit(True)
            return connected

        self.set_auto_detect(False)
        slot.using_real_backend = False
        slot.device_path = ""
        connected = slot.controller_service.set_backend(SimulatedBackend())
        self.backend_changed.emit(False)
        return connected

    def apply_audio(self, audio: AudioSettings) -> None:
        self.audio = audio.clamp()
        self.keyboard_mapper.sync_windows_mute = self.audio.sync_windows_mute
        self.controller_service.apply_audio(self.audio)
        self.audio_changed.emit(self.audio)
        self.save_settings()

    def toggle_mic_mute_hardware(self) -> None:
        self.audio.mic_muted = not self.audio.mic_muted
        self.controller_service.apply_audio(self.audio)
        self.audio_changed.emit(self.audio)

    def apply_lighting(self, lighting: LightingSettings) -> None:
        self.lighting = lighting.clamp()
        if self.lighting_engine is not None:
            self.lighting_engine.set_settings(self.lighting)
        else:
            self.controller_service.apply_lighting(self.lighting)

    def apply_dual_stage_tactile_stop(self, side: str = "BOTH") -> None:
        """Configura un tope físico tipo clic justo antes del umbral Dual Stage."""
        from dualcontrol.models import TriggerMode

        start_zone = max(3, min(8, int(round(self.mapping.dual_stage_threshold * 8.0)) - 1))
        tactile = TriggerSettings(
            enabled=True,
            mode=TriggerMode.PULSE,
            forces=[start_zone, 240, min(9, start_zone + 2), 0, 0, 0, 0],
            preset_name="dual_stage_stop",
        ).clamp()
        if side in ("L2", "BOTH"):
            self.trigger_l2 = tactile
            self.controller_service.apply_trigger("L2", tactile)
        if side in ("R2", "BOTH"):
            self.trigger_r2 = tactile
            self.controller_service.apply_trigger("R2", tactile)

    def apply_mapping(self, mapping: MappingSettings) -> None:
        self.mapping = mapping.clamp()
        self.virtual_controller_service.set_mapping(self.mapping)
        self.mapping_changed.emit(self.mapping)

    def apply_profile(self, profile: Profile) -> None:
        self.trigger_l2 = profile.trigger_l2
        self.trigger_r2 = profile.trigger_r2
        self.haptics = profile.haptics
        self.lighting = profile.lighting
        self.mapping = profile.mapping.clamp()
        self.current_profile_name = profile.name

        self.controller_service.apply_trigger("L2", self.trigger_l2)
        self.controller_service.apply_trigger("R2", self.trigger_r2)
        self.controller_service.apply_haptics(self.haptics)
        self.apply_lighting(self.lighting)
        self.virtual_controller_service.set_mapping(self.mapping)
        self.mapping_changed.emit(self.mapping)
        self.profile_applied.emit(profile)

    def build_profile(self, name: str, game: str | None) -> Profile:
        return Profile(
            name=name,
            game=game or None,
            trigger_l2=self.trigger_l2,
            trigger_r2=self.trigger_r2,
            haptics=self.haptics,
            lighting=self.lighting,
            mapping=self.mapping.clamp(),
        )

    def shutdown(self) -> None:
        self.save_settings()
        self._auto_detect_timer.stop()
        self.game_watcher.stop()
        self.keyboard_mapper.release_all()
        self.audio_rumble.stop()
        if self.hidhide_service.is_cloak_active:
            self.hidhide_service.unhide_all()
        if self.udp_server is not None and self.udp_server.is_running:
            self.udp_server.stop()
        for slot in self.slots:
            if slot.lighting_engine is not None:
                slot.lighting_engine.stop()
            slot.virtual_controller_service.shutdown()
            slot.controller_service.disconnect_controller()
