"""Control de acceso por rol.

- Contraseñas guardadas con PBKDF2-SHA256 (600.000 iteraciones) y sal propia; nunca en texto plano.
- Bloqueo temporal tras 5 intentos fallidos seguidos.
- Sesiones con token aleatorio de 256 bits que vence a las 8 horas.
- Cada ruta declara el permiso que necesita; el backend lo exige aunque la pantalla no muestre el botón.
- Cada ingreso, intento fallido y salida queda en la bitácora.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Header, HTTPException

from . import config, estado

ROLES = {
    "jefe": {"nombre": "Jefatura de seguridad", "permisos": ["estrategico", "operativo", "ver_denuncias", "auditar"],
             "descripcion": "Ve el panorama del mes, los riesgos y recibe las alertas críticas."},
    "analista": {"nombre": "Analista del SOC", "permisos": ["estrategico", "operativo", "decidir", "reidentificar",
                                                             "cargar_datos", "tecnico", "ver_denuncias",
                                                             "gestionar_denuncias", "verificar"],
                 "descripcion": "Investiga los casos, decide y gestiona las denuncias."},
    "ti": {"nombre": "Equipo de TI", "permisos": ["estrategico", "tecnico", "cargar_datos", "ver_ci"],
           "descripcion": "Carga los datos y aplica reglas e indicadores en sus sistemas."},
    "salud": {"nombre": "Personal de salud", "permisos": ["verificar"],
              "descripcion": "Revisa enlaces e imágenes sospechosos antes de abrirlos."},
    "auditor": {"nombre": "Auditoría", "permisos": ["estrategico", "auditar"],
                "descripcion": "Revisa quién hizo qué y cuándo. Solo lectura."},
}
ITERACIONES = 600_000


def derivar(clave: str, sal: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, ITERACIONES).hex()


def _usuarios() -> dict:
    """Usuarios de demostración. La primera vez se crean con contraseña cifrada en estado/usuarios.json."""
    f = config.estado() / "usuarios.json"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        base = {"jefe": "Jefatura de seguridad", "analista": "Analista SOC A-01", "ti": "Equipo de TI",
                "salud": "Personal de salud · Unidad 3", "auditor": "Auditoría interna"}
        datos = {}
        for usuario, nombre in base.items():
            sal = secrets.token_bytes(16)
            datos[usuario] = {"nombre": nombre, "rol": usuario, "sal": sal.hex(),
                              "hash": derivar(config.CLAVE_DEMO, sal)}
        f.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return json.loads(f.read_text(encoding="utf-8"))


@dataclass
class Sesion:
    usuario: str
    nombre: str
    rol: str
    vence: float

    @property
    def permisos(self) -> list[str]:
        return ROLES[self.rol]["permisos"]

    def publica(self) -> dict:
        return {"usuario": self.usuario, "nombre": self.nombre, "rol": self.rol, "rolNombre": ROLES[self.rol]["nombre"],
                "permisos": self.permisos, "vence": int(self.vence)}


_sesiones: dict[str, Sesion] = {}
_fallos: dict[str, list[float]] = {}
_lock = threading.Lock()


def ingresar(usuario: str, clave: str) -> tuple[str, Sesion]:
    usuario = usuario.strip().lower()
    ahora = time.time()
    with _lock:
        recientes = [t for t in _fallos.get(usuario, []) if ahora - t < config.BLOQUEO_MIN * 60]
        _fallos[usuario] = recientes
        if len(recientes) >= config.INTENTOS_MAX:
            espera = int(config.BLOQUEO_MIN * 60 - (ahora - recientes[0])) // 60 + 1
            raise HTTPException(423, f"Cuenta bloqueada por {config.INTENTOS_MAX} intentos fallidos. "
                                     f"Intenta de nuevo en {espera} min.")
    u = _usuarios().get(usuario)
    ok = bool(u) and hmac.compare_digest(derivar(clave, bytes.fromhex(u["sal"])), u["hash"])
    if not ok:
        with _lock:
            _fallos.setdefault(usuario, []).append(ahora)
            quedan = config.INTENTOS_MAX - len(_fallos[usuario])
        estado.bitacora(usuario or "desconocido", "-", "Intento de ingreso fallido", "consola",
                        f"Quedan {max(quedan, 0)} intentos antes del bloqueo")
        if quedan <= 0:
            estado.bitacora(usuario or "desconocido", "-", "Cuenta bloqueada", "consola",
                            f"{config.INTENTOS_MAX} intentos fallidos; bloqueo de {config.BLOQUEO_MIN} min")
            raise HTTPException(423, f"Cuenta bloqueada por {config.INTENTOS_MAX} intentos fallidos. "
                                     f"Intenta de nuevo en {config.BLOQUEO_MIN} min.")
        raise HTTPException(401, "Usuario o contraseña incorrectos." +
                            (f" Te quedan {quedan} intentos." if 0 < quedan < config.INTENTOS_MAX else ""))
    with _lock:
        _fallos.pop(usuario, None)
        token = secrets.token_urlsafe(32)
        s = Sesion(usuario, u["nombre"], u["rol"], ahora + config.SESION_HORAS * 3600)
        _sesiones[token] = s
    estado.bitacora(s.nombre, ROLES[s.rol]["nombre"], "Ingreso a la consola", "consola", "Sesión de 8 horas")
    return token, s


def salir(token: str) -> None:
    with _lock:
        s = _sesiones.pop(token, None)
    if s:
        estado.bitacora(s.nombre, ROLES[s.rol]["nombre"], "Salida de la consola", "consola", "")


def sesion_actual(authorization: str = Header(default="")) -> Sesion:
    token = authorization.removeprefix("Bearer ").strip()
    with _lock:
        s = _sesiones.get(token)
        if s and s.vence < time.time():
            _sesiones.pop(token, None)
            s = None
    if not s:
        raise HTTPException(401, "La sesión no existe o venció. Vuelve a ingresar.")
    return s


def requiere(permiso: str):
    def dep(authorization: str = Header(default="")) -> Sesion:
        s = sesion_actual(authorization)
        if permiso not in s.permisos:
            estado.bitacora(s.nombre, ROLES[s.rol]["nombre"], "Acceso denegado", permiso,
                            "Intentó abrir una sección que no corresponde a su rol")
            raise HTTPException(403, f"Tu rol ({ROLES[s.rol]['nombre']}) no tiene acceso a esta sección.")
        return s
    return dep
