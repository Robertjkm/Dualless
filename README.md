# Dualless

[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%20x64-0078D6.svg)](#inicio-rápido-en-windows)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22C55E.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v1.4.0-A855F7.svg)](STATUS.md)

**Dualless** es una aplicación de escritorio open-source para administrar las funciones avanzadas del mando **Sony DualSense** y **DualSense Edge** (PS5) en Windows, con transporte HID nativo por USB y Bluetooth sin requerir `hidapi.dll` externa.

## Características principales

* **Transporte nativo USB y Bluetooth (`win32_hid.py`):** Comunicación directa mediante `ctypes` sobre `hid.dll` y `setupapi.dll` de Windows, con detección automática, reconexión en caliente y restauración automática de gatillos, hápticos e iluminación.
* **Gatillos adaptativos y Hápticos:**
  * Control independiente de **L2** y **R2** con presets (*Feedback*, *Weapon*, *Vibration*, *Bow*, *Galloping*) y editor de parámetros crudos.
  * **Hápticos HD por USB de 4 canales** (enrutamiento WASAPI Loopback hacia canales 3–4 VCM) y respaldo automático a **Audio-to-Rumble** vía HID.
  * **Motor Rumble-to-Triggers:** Convierte en tiempo real la vibración de juegos Xbox/DS4 en retroceso y pulsos físicos en L2/R2.
* **Emulación de mando virtual y Anti-Double Input:**
  * Modos **Native**, **Xbox 360 (XInput)** y **DualShock 4** mediante `vgamepad` + `ViGEmBus` (opcional; nunca instala drivers en silencio).
  * **LED Passthrough real** en emulación DualShock 4.
  * Integración opcional con **HidHide** y **detector de conflictos HID en vivo** (`Steam Input`, `DSX`, `DS4Windows`, `reWASD`, `x360ce`).
* **Control competitivo y personalización:**
  * **Gyro Pro:** *Gyro Mouse* y *Gyro-to-Stick* con filtro de suavizado **EMA**, zona muerta anti-temblor, eje horizontal **Yaw / Roll** y botón de activación configurable.
  * **Hair Trigger ajustable**, **Rapid Trigger** en L2/R2 y **Dual Stage** con tope táctil físico.
  * Curvas de sticks (*Lineal*, *Precisión*, *Rápida*), **calibración Anti-Drift**, **Modo Turbo (`2–25 Hz`)**, mapeo libre a teclado/ratón, macros de Windows y soporte **DualSense Edge** (*Paddles* y botones `FN`).
* **Automatización diaria:**
  * **Multi-Mando simultáneo (`P1–P4`)** en paralelo con asignación de LED de jugador.
  * Cambio automático de perfil por proceso activo (`.exe`), **System Tray**, inicio opcional con Windows, alertas de batería baja, control de altavoz/Mute sincronizado y servidor UDP local (`127.0.0.1`) compatible con mods DSX.

## Inicio rápido en Windows

### Opción A — Descargar el ejecutable listo (recomendado para usuarios)
Descarga `Dualless.exe` o `Dualless-v1.4.0-win64-portable.zip` desde la sección **Releases** del repositorio y ejecútalo directamente (no requiere instalar Python).

### Opción B — Ejecutar desde el código fuente
1. Instala **Python 3.10+** desde [python.org](https://www.python.org/downloads/) marcando **"Add python.exe to PATH"**.
2. Clona o descarga este repositorio:
   ```bash
   git clone https://github.com/Robertjkm/Dualless.git
   cd Dualless
   ```
3. Haz doble clic en **`ejecutar.bat`** (crea `.venv`, valida `pip`, instala dependencias y abre la aplicación).

## Compilar tu propio `.exe` e instalador en Windows

* **Un único `.exe` portátil (`dist\Dualless.exe`):** Doble clic en **`compilar_onefile.bat`**.
* **Carpeta autocontenida (`dist\Dualless\Dualless.exe`):** Doble clic en **`compilar_exe.bat`**.
* **Paquete con IExpress nativo de Windows:** Doble clic en **`crear_iexpress.bat`**.
* **Instalador clásico con Inno Setup 6:** Doble clic en **`crear_instalador.bat`**.

## Compilación automática en GitHub Releases (CI/CD)

Este repositorio incluye dos workflows en `.github/workflows/`:
* **`ci.yml`:** Ejecuta las pruebas automatizadas (`pytest`) en cada push o Pull Request.
* **`release.yml`:** Al publicar un tag con formato `v*` (por ejemplo `git tag v1.4.0 && git push origin v1.4.0`), GitHub compila automáticamente `Dualless.exe` y el ZIP portátil en un runner `windows-latest` y los adjunta al Release.

## Pruebas automatizadas

```bash
python -m pytest -q
```

## Contribuciones y Licencia

Las contribuciones son bienvenidas — consulta [CONTRIBUTING.md](CONTRIBUTING.md).

Distribuido bajo licencia **MIT** ([LICENSE](LICENSE)). Consulta [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) para ver las licencias de terceros.

> **Aviso:** Dualless es un proyecto independiente de código abierto y no está afiliado ni respaldado por Sony Interactive Entertainment Inc. ni por Microsoft Corporation.
