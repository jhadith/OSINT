"""Adaptador: ítems OSINT → tendencias evaluables por threatpulse.evaluar, sin tocar threatpulse.py.

- `cruzar()` aplica el cruce por CVE del spec: en el catálogo KEV → kev=true; con explotación
  en Exploit-DB → exploit_publico=true.
- `seleccion()` elige el subconjunto para la vista (por fuente y tope global, priorizando
  fechas recientes; un CVE nunca aparece dos veces: gana la ficha con más datos).
- `a_tendencia()` entrega los 11 campos que lee Tendencias.tsx + el sello real/simulado.

threatpulse.py no se modifica: su mapa público CONFIANZA_FUENTE se COMPLETA (solo se añaden
claves) con las fuentes reales para que evaluar() las puntúe con honestidad; las 4 fuentes
del feed fijo conservan exactamente su confianza y sus scores.
"""
from __future__ import annotations

import re

from .. import threatpulse

CONFIANZA_REAL: dict[str, float] = {
    "NVD": 0.9,                       # NIST: catálogo CVE oficial
    "INCIBE-CERT": 0.85,              # CERT nacional
    "Fortinet PSIRT": 0.85,           # avisos oficiales de fabricante
    "Palo Alto PSIRT": 0.85,
    "Ubuntu Security Notices": 0.85,
}
threatpulse.CONFIANZA_FUENTE.update(CONFIANZA_REAL)   # CISA ya estaba: update solo añade claves

POR_FUENTE = 5               # cuántas lecturas por fuente entran a la vista
TOPE_TOTAL = 24              # tope global de lecturas reales fusionadas al feed
_CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)

_EXPOSICION_LOCAL = {
    "kev": "Explotación activa confirmada (CISA KEV): verificar de inmediato en qué grado aplica a nuestros sistemas.",
    "cve": "Revisar si la versión afectada corre en nuestra infraestructura antes de priorizar el parche.",
    "exploit": "Explotación pública disponible: verificar si el componente afectado está instalado.",
    "boletin": "Aplicar el parche o la mitigación recomendada si el producto afectado está en uso.",
    "psirt": "Aplicar el parche o la mitigación del fabricante si el producto afectado está en uso.",
    "medio": "Prensa/inteligencia abierta: verificar el dato antes de actuar sobre él.",
    "pulso": "Pulso de inteligencia abierta: correlacionar los indicadores con nuestro tráfico.",
}


def _cves(texto: str) -> set[str]:
    return {c.upper() for c in _CVE.findall(texto or "")}


def cruzar(items: list[dict]) -> list[dict]:
    """Cruce por CVE (S13): CVE en el catálogo KEV → kev=true; en Exploit-DB → exploit_publico=true.

    Solo aplica a las fichas cuya identidad ES un CVE (tipos cve/kev): una noticia o un exploit
    no se reetiquetan por mencionar el CVE.
    """
    en_kev = {i["id_externo"].upper() for i in items if i["tipo"] == "kev"}
    con_exploit: set[str] = set()
    for i in items:
        if i["tipo"] == "exploit":
            con_exploit |= _cves(" ".join([i["titulo"], i["resumen"], *i["tags"]]))
    for i in items:
        if i["tipo"] not in ("cve", "kev"):
            continue
        cve = i["id_externo"].upper()
        if cve in en_kev:
            i["kev"] = True
        if cve in con_exploit:
            i["exploit_publico"] = True
    return items


def sello(item: dict) -> str:
    """Sello que ve la pantalla: real (KEV) / real (NVD) / real (fuente)."""
    if item["kev"]:
        return "real (KEV)"
    if item["fuente"] == "NVD":
        return "real (NVD)"
    return f"real ({item['fuente']})"


def _riqueza(item: dict) -> tuple:
    """Ficha con más datos gana el desempate: CVSS, luego marca kev, luego exploit público."""
    return (item["cvss"] is not None, item["kev"], item["exploit_publico"])


def seleccion(items: list[dict], por_fuente: int = POR_FUENTE, tope: int = TOPE_TOTAL) -> list[dict]:
    """Subconjunto para la vista: un CVE = una ficha; más recientes primero; por fuente y tope."""
    mejores: dict[str, dict] = {}
    for i in items:
        # la identidad de un CVE es su id; el resto se distingue por fuente+id
        clave = (i["id_externo"].upper() if i["tipo"] in ("cve", "kev")
                 else f'{i["fuente"]}|{i["id_externo"]}')
        if clave not in mejores or _riqueza(i) > _riqueza(mejores[clave]):
            mejores[clave] = i
    orden = sorted(mejores.values(),
                   key=lambda i: ((i["fecha"] or "0000-00-00"), 1 if i["kev"] else 0), reverse=True)
    salida, cuentas = [], {}
    for i in orden:
        if cuentas.get(i["fuente"], 0) >= por_fuente:
            continue
        cuentas[i["fuente"]] = cuentas.get(i["fuente"], 0) + 1
        salida.append(i)
        if len(salida) >= tope:
            break
    return salida


def _id(item: dict) -> str:
    limpio = re.sub(r"[^A-Za-z0-9]+", "-", f'{item["fuente"]}-{item["id_externo"]}')
    return "O-" + limpio.strip("-")


def a_tendencia(item: dict) -> dict:
    """Ítem normalizado → tendencia con los 11 campos del feed fijo + sello y marcas nuevas."""
    cvss = item["cvss"]
    kev, exploit = item["kev"], item["exploit_publico"]
    # relevancia/impacto 0-5 para la fórmula del F-11; exposición local sin medir = 3 neutral
    relevancia = 5 if kev else (4 if (cvss or 0) >= 7 or exploit else 3)
    impacto = 5 if kev or (cvss or 0) >= 9 else (4 if exploit or (cvss or 0) >= 7 else 3)
    return {
        "id": _id(item),
        "titulo": item["titulo"],
        "fuente": item["fuente"],
        # sin atribución inventada al sector salud: sector vacío aplica el factor honesto de threatpulse
        "fecha": item["fecha"] or "",
        "sector": "",
        "relevancia": relevancia,
        "exposicion": 3,
        "impacto": impacto,
        "tecnicas": item["tags"][:4] or [item["tipo"].upper()],
        "resumen": item["resumen"] or item["titulo"],
        "serie": [],
        "exposicionLocal": _EXPOSICION_LOCAL.get(item["tipo"], "Revisar si aplica a nuestra infraestructura."),
        "sello": sello(item),
        "kev": kev,
        "exploitPublico": exploit,
        "cvss": cvss,
    }
