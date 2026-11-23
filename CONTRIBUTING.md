# Contribuir a Dualless

Gracias por tu interés en mejorar **Dualless**.

## Flujo recomendado

1. Haz un *fork* del repositorio y crea una rama descriptiva (`git checkout -b fix/mi-mejora`).
2. Instala las dependencias de desarrollo en un entorno virtual:
   ```bash
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. Ejecuta los tests antes de enviar tu Pull Request:
   ```bash
   .venv\Scripts\python.exe -m pytest -q
   ```
4. Mantén los cambios enfocados y documenta cualquier ajuste en `STATUS.md` si cambia el comportamiento de usuario.

## Principios del proyecto

* **Sin instalaciones silenciosas:** Dualless nunca instala drivers de kernel (`ViGEmBus`, `HidHide`, WDK) sin acción explícita del usuario.
* **Separación clara:** La interfaz (`dualcontrol/ui/`) nunca accede directamente al hardware HID; todo pasa por `AppContext` y los servicios (`dualcontrol/services/`).
