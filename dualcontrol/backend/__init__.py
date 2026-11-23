from .base import ControllerBackend, BackendError
from .simulated import SimulatedBackend

__all__ = ["ControllerBackend", "BackendError", "SimulatedBackend"]

# RealBackend se importa aparte (dualcontrol.backend.real) para no forzar la
# dependencia de hidapi/pydualsense cuando solo se usa el simulador (p. ej. en tests
# o en este propio entorno de desarrollo, que no tiene el hardware conectado).
