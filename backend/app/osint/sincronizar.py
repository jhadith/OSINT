"""Sincronización manual de fuentes OSINT (S13/T15): TTL por fuente, sync parcial y
tolerancia a fallos. NADA corre en import/startup: solo se llama desde
POST /api/threatpulse/actualizar.

Cada fuente se actualiza por separado (try/except con timeout en el fetch): una caída no
rompe el sincronizado de las demás y su caché previa queda intacta. Nunca lanza excepción.
"""
from __future__ import annotations

import datetime as dt

from . import cache, recoletores


def sincronizar(ahora: dt.datetime | None = None) -> dict:
    """Actualiza lo vencido, conserva lo fresco y lo que falle.

    Devuelve {actualizadas, fallidas, totales, sincronizado_en}:
    - `actualizadas`: fuentes al día al terminar (las frescas se saltan sin petición nueva).
    - `fallidas`: vencidas cuya petición falló (su caché previa sigue vigente).
    """
    ahora = ahora or dt.datetime.now()
    marca = ahora.strftime("%Y-%m-%dT%H:%M:%S")
    fuentes = recoletores.fuentes()
    actualizadas = fallidas = 0
    for fuente in fuentes:
        try:
            if cache.fresca(fuente["id"], ahora):
                actualizadas += 1
                continue
            items = recoletores.recolectar(fuente)
            cache.guardar(fuente["id"], items, marca)
            actualizadas += 1
        except Exception as e:                      # una fuente caída no rompe las demás
            _registrar_fallo(fuente["id"], e)
            fallidas += 1
    return {"actualizadas": actualizadas, "fallidas": fallidas, "totales": len(fuentes),
            "sincronizado_en": marca}


def _registrar_fallo(fuente: str, error: BaseException) -> None:
    try:
        cache.registrar_fallo(fuente, f"{type(error).__name__}: {error}"[:300])
    except Exception:
        pass                                        # ni el registro del fallo puede romper el sync
