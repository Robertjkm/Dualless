# Plantilla de Driver Virtual DualSense (KMDF + VHF) — Solo desarrollo WDK

Esta carpeta contiene un esqueleto limpio en C (`dualless_vhf.c`) y su archivo
de instalación (`dualless_vhf.inf`) para experimentar con el **Virtual HID Framework (VHF)**
de Windows Driver Kit (WDK).

## Aviso honesto antes de compilar

* **Dualless NO instala este driver ni lo necesita para funcionar.** En el día a día usa **Native Mode**, **Xbox 360 / DualShock 4 Emulation (ViGEmBus)**, **HidHide**, **LED Passthrough** y **Rumble-to-Triggers**.
* En Windows 10/11 x64, un driver en modo kernel no firmado comercialmente solo carga si activas **Test Signing Mode**, lo cual **bloquea la mayoría de los sistemas anti-cheat** (Vanguard, EAC, BattlEye, Ricochet).
* Para distribución pública sin Test Signing Mode se requiere un certificado EV comercial y firma *Microsoft Attestation Signing*.

## Cómo compilarlo (Visual Studio 2022 + WDK)

1. Instala **Visual Studio 2022** (carga *Desktop development with C++*) y el **Windows Driver Kit (WDK)** correspondiente a tu SDK.
2. Crea un proyecto **Kernel Mode Driver, Empty (KMDF)** y agrega `dualless_vhf.c` y `dualless_vhf.inf`.
3. En *Project Properties → Linker → Input → Additional Dependencies*, añade `$(DDK_LIB_PATH)vhfkm.lib`.
4. Compila en configuración `Release | x64`.
5. Solo en una máquina de pruebas (sin anti-cheat):
   ```cmd
   bcdedit /set testsigning on
   ```
   Reinicia e instala con `devcon install dualless_vhf.inf Root\DuallessVhf`.
6. Una vez registrado el servicio `DuallessVhf`, Dualless lo detectará automáticamente en **Game Compatibility → Estado y requisitos**.
