"""OSINT real para ThreatPulse (S13/T15): CTI + TECHINT de nivel 1, sin claves obligatorias.

- recoletores: CISA KEV, NVD (sin key), Exploit-DB, RSS/Atom de CERTs, PSIRTs y prensa,
  AlienVault OTX solo si OTX_API_KEY está en el entorno; VulnCheck degradado (sin fetch).
- cache: estado/osint.db con fetched_at por fuente (TTL 6 h; KEV 24 h).
- sincronizar: sync MANUAL (cero automático), tolerante a fallos por fuente.
- adaptador: ítems → tendencias evaluables por threatpulse.evaluar + sello real/simulado.

Uso típico:  osint.sincronizar()  (POST /api/threatpulse/actualizar)
             osint.tendencias_reales()  (GET /api/threatpulse, solo lectura de caché).
"""
from __future__ import annotations

from . import adaptador, cache, recoletores
from .sincronizar import sincronizar

__all__ = ["sincronizar", "tendencias_reales"]


def tendencias_reales() -> tuple[list[dict], dict | None]:
    """Ítems de la caché adaptados a tendencias + metadatos; ([], None) si no hay datos reales.

    Con la caché vacía main.py responde idéntico a como respondía antes de existir OSINT
    (sin clave `osint` ni campos nuevos): el feed fijo es el respaldo total.
    """
    items = cache.leer()
    if not items:
        return [], None
    elegidos = adaptador.seleccion(adaptador.cruzar(items))
    tendencias = [adaptador.a_tendencia(i) for i in elegidos]
    meta = {
        "sincronizadoEn": cache.sincronizado_en() or "",
        "items": len(tendencias),
        "fuentes": len({i["fuente"] for i in elegidos}),
        "notas": recoletores.notas_omitidas(),
    }
    return tendencias, meta
