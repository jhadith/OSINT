"""Estado de la consola en SQLite (solo agregar): nunca se edita ni se borra una línea (control de repudio).

Las firmas públicas no cambian: leer, agregar, bitacora, ultimo_por y ahora siguen igual que cuando
los datos vivían en JSONL de estado/, así main.py no cambia. Por dentro todo va a estado/sentinel.db
a través de app.almacen (ciclo de vida, append-only con triggers y migración idempotente).
"""
from __future__ import annotations

import datetime as dt
import threading

from . import almacen, config

_lock = threading.RLock()


def ahora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _ruta():
    return config.estado() / "sentinel.db"


def leer(nombre: str) -> list[dict]:
    with almacen.abriendo(_ruta()) as db:
        if nombre == "bitacora":
            return almacen.leer_bitacora(db)
        return almacen.leer_registros(db, nombre)


def agregar(nombre: str, registro: dict) -> dict:
    with _lock, almacen.abriendo(_ruta()) as db:
        if nombre == "bitacora":
            almacen.agregar_bitacora(db, registro)
        else:
            almacen.agregar_registro(db, nombre, registro)
    return registro


def bitacora(actor: str, rol: str, accion: str, objetivo: str, detalle: str) -> dict:
    with _lock, almacen.abriendo(_ruta()) as db:
        return almacen.registrar_evento(db, actor, rol, accion, objetivo, detalle)


def ultimo_por(nombre: str, clave: str) -> dict[str, dict]:
    """Última línea por clave (la decisión vigente de cada caso, el estado vigente de cada denuncia...)."""
    return {d[clave]: d for d in leer(nombre)}
