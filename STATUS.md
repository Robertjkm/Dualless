# STATUS — Dualless v1.4.0

Este documento refleja la arquitectura real y el estado actual de **Dualless v1.4.0**.

## Arquitectura actual

* **Transporte HID nativo (`win32_hid.py`, `real.py`, `protocol.py`):** USB y Bluetooth nativo en Windows (`hid.dll` / `setupapi.dll`), audio/altavoz/Mute LED y DualSense Edge.
* **Motor de entrada y emulación (`mapper.py`, `xinput_vigem.py`, `virtual_controller_service.py`, `touchpad_mouse.py`, `keyboard_mapper.py`):** Xbox 360 / DS4 (ViGEmBus) con *LED Passthrough*, *Rumble-to-Triggers*, **Gyro Pro** (EMA, Yaw/Roll, activación configurable), **Rapid Trigger**, *Hair Trigger* ajustable, *Dual Stage* táctil, Turbo, curvas y Anti-Drift.
* **Distribución Windows:** `compilar_exe.bat` (`--onedir`), `compilar_onefile.bat` (`--onefile`), `crear_iexpress.bat` (IExpress nativo automatizado) y `crear_instalador.bat` (Inno Setup 6).

## Historial reciente

* **v1.4.0:** Gyro Pro (EMA, Yaw/Roll, activación libre), Rapid Trigger, umbrales ajustables de Hair Trigger y Dual Stage con tope táctil, corrección Multi-Mando en Touchpad/Macros y scripts 1-clic `compilar_onefile.bat` / `crear_iexpress.bat`.
* **v1.3.0:** Nivel 3 — LED Passthrough real en DS4, Motor Rumble-to-Triggers, Detector de conflictos HID y plantilla WDK KMDF/VHF.
* **v1.2.0:** Nivel 2 — Gyro-to-Stick, Hair Trigger, mapeo libre a teclado/ratón, Turbo, altavoz/Mute y DualSense Edge.
* **v1.1.0:** Nivel 1 — Integración real con HidHide, Multi-Mando simultáneo P1–P4 y Hápticos HD USB de 4 canales.
