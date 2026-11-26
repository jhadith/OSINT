"""Rutas y opciones del backend. Todo se puede cambiar con variables de entorno."""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent           # backend/
PROYECTO = RAIZ.parent                                   # sentinel-salud/
MOTOR = PROYECTO / "motor"
FIJOS = Path(__file__).resolve().parent / "fijos"
WEB_DIST = PROYECTO / "web" / "dist"

if str(MOTOR) not in sys.path:        # el backend usa funciones del motor (seudónimo de contactos)
    sys.path.insert(0, str(MOTOR))


def _ruta(var: str, defecto: Path) -> Path:
    return Path(os.environ[var]).resolve() if os.environ.get(var) else defecto


def estado() -> Path:
    """Análisis, decisiones, denuncias y bitácora (archivos de solo agregar)."""
    return _ruta("SENTINEL_ESTADO", RAIZ / "estado")


def datos() -> Path:
    """Carpeta donde el equipo deja los CSV grandes para analizarlos sin subirlos por el navegador."""
    return _ruta("SENTINEL_DATOS", PROYECTO / "datos")


EJEMPLOS = PROYECTO / "datos_ejemplo"
PYTHON_MOTOR = os.environ.get("SENTINEL_PYTHON", sys.executable)
TELEGRAM_ENVIAR = os.environ.get("SENTINEL_TELEGRAM", "simulacion") == "enviar"
MAX_SUBIDA = int(os.environ.get("SENTINEL_MAX_MB", "1200")) * 1024 * 1024
MAX_IMAGEN = 15 * 1024 * 1024
SESION_HORAS = 8
INTENTOS_MAX = 5
BLOQUEO_MIN = 5
ORIGENES = ["http://localhost:5173", "http://127.0.0.1:5173"]
# Contraseña de las cuentas de demostración (se cifra al crear estado/usuarios.json). En producción: cuentas nominales
# del directorio institucional con MFA.
CLAVE_DEMO = os.environ.get("SENTINEL_CLAVE_DEMO", "demo2026")
