"""Estado de la consola en archivos JSONL de solo agregar: nunca se edita ni se borra una línea (control de repudio)."""
from __future__ import annotations

import datetime as dt
import json
import threading

from . import config

_lock = threading.RLock()


def ahora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _archivo(nombre: str):
    d = config.estado()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{nombre}.jsonl"


def leer(nombre: str) -> list[dict]:
    f = _archivo(nombre)
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def agregar(nombre: str, registro: dict) -> dict:
    with _lock, open(_archivo(nombre), "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


def bitacora(actor: str, rol: str, accion: str, objetivo: str, detalle: str) -> dict:
    with _lock:
        n = len(leer("bitacora")) + 1
        return agregar("bitacora", {"id": f"B-{n:05d}", "fecha": ahora(), "actor": actor, "rol": rol,
                                    "accion": accion, "objetivo": objetivo, "detalle": detalle})


def ultimo_por(nombre: str, clave: str) -> dict[str, dict]:
    """Última línea por clave (la decisión vigente de cada caso, el estado vigente de cada denuncia...)."""
    return {d[clave]: d for d in leer(nombre)}
