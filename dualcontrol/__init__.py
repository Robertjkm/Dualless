"""Dualless — aplicación independiente para administrar el mando Sony DualSense.

Este paquete contiene toda la lógica de la aplicación. La comunicación HID real con
el hardware está aislada detrás de la interfaz ``dualcontrol.backend.base.ControllerBackend``
para que el resto de la aplicación (interfaz gráfica, perfiles, diagnósticos) nunca
dependa directamente del hardware ni de una biblioteca HID concreta.
"""

__version__ = "0.3.0"
