"""Validación de patrones HBVF contra explicaciones legítimas (informe 14.4, etapas 4-5).

Cada patrón del catálogo se contrasta con su explicación legítima (cuidador, operador
autorizado, red compartida). Si falta información, el patrón queda "desconocido", nunca
culpable. Los indicadores de la misma familia no cuentan como evidencias independientes:
el peso de familia proviene de ``pattern_catalog.json``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .. import config
from .mitigation_engine import recomendaciones as claves_recomendadas

RUTA_CATALOGO = Path(__file__).with_name("pattern_catalog.json")

_CACHE: dict[str, dict[str, Any]] = {}


def cargar_catalogo(ruta: Path | str | None = None) -> dict[str, Any]:
    """Catálogo HG-01..HG-07 (familias, pesos y estados) versionado en `pattern_catalog.json`."""
    clave = str(ruta) if ruta else str(RUTA_CATALOGO)
    if clave not in _CACHE:
        with open(clave, encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if not isinstance(datos.get("patrones"), list) or not datos["patrones"]:
            raise ValueError(f"catálogo inválido en {clave}: falta 'patrones'")
        _CACHE[clave] = datos
    return _CACHE[clave]


def estado_patron(presente: bool | None, explicado: bool = False) -> str:
    """Estado de un patrón: ``ausente``/``presente``/``explicado``; sin datos es ``desconocido``, nunca culpa."""
    if presente is None:
        return "desconocido"
    if presente and explicado:
        return "explicado"
    return "presente" if presente else "ausente"


def validar(r: pd.Series, reportados: set, catalogo: dict[str, Any] | None = None) -> dict:
    """Valida un punto contra el catálogo: patrones, estado, confianza, riesgo y mitigaciones."""
    cat = catalogo if catalogo is not None else cargar_catalogo()
    lista, pesos = cat["patrones"], cat["peso_familia"]
    c = config
    autorizado = bool(r["autorizado"]) and r["rol"] in ("cuidador", "operador_autorizado")
    tecnica = None if not r["con_datos_tecnicos"] else bool(
        r["no_navegador"] or r["pct_red_oculta"] >= 0.5 or r["ips"] >= c.CITAS_IPS_ROTACION)
    patrones = {
        "HG-01": estado_patron(r["pacientes_por_semana"] > c.CITAS_PACIENTES_SEMANA
                               or r["pacientes"] > c.CITAS_LIMITE_30_DIAS, explicado=autorizado),
        "HG-02": estado_patron(None if not r["con_tiempos"] else
                               bool(r["respuesta_mediana_ms"] < c.CITAS_RESPUESTA_HUMANA_MS), explicado=autorizado),
        "HG-03": estado_patron(r["cancelaciones"] >= c.CITAS_CANCELACIONES
                               and r["cancelaciones"] >= 0.3 * max(1, r["reservas"])),
        "HG-04": estado_patron(r["reservas_al_abrir"] >= c.CITAS_AL_ABRIR),
        "HG-05": estado_patron(r["reasignaciones"] >= 1),
        "HG-06": estado_patron(tecnica, explicado=autorizado),
        "HG-07": "presente" if r.name in reportados else "ausente",
    }
    fam = {p["id"]: p["familia"] for p in lista}
    familias = {fam[k] for k, v in patrones.items() if v == "presente"}
    independientes = sum(pesos[f] for f in familias)
    desconocidos = [k for k, v in patrones.items() if v == "desconocido"]
    explicados = [k for k, v in patrones.items() if v == "explicado"]
    presentes = [k for k, v in patrones.items() if v == "presente"]

    if not presentes and explicados:
        estado = "Explicado por contexto legítimo"
    elif independientes >= 3 or (independientes >= 2 and ("HG-05" in presentes or "HG-07" in presentes)):
        estado = "Revisión prioritaria"
    elif independientes >= 2:
        estado = "Requiere revisión"
    elif independientes >= 1 and len(desconocidos) >= 2:
        estado = "Indeterminado: falta información"
    elif independientes >= 1:
        estado = "Observación"
    else:
        estado = "Sin hallazgo"
    confianza = round(min(1.0, 0.22 * independientes + (0.12 if "HG-07" in presentes else 0)
                          - 0.05 * len(desconocidos)), 2)
    confianza = max(0.0, confianza)
    prob = 1 + min(4, int(round(independientes)))          # 1..5
    impacto = 5 if "HG-05" in presentes else 4             # disponibilidad y equidad del acceso a la salud
    legitimas = [p["contexto_legitimo"] for p in lista if patrones[p["id"]] in ("presente", "explicado")]
    return {"patrones": patrones, "estado": estado, "confianza": confianza, "evidencia_independiente": independientes,
            "riesgo": prob * impacto, "probabilidad": prob, "impacto": impacto,
            "explicaciones_legitimas": legitimas, "recomendaciones": claves_recomendadas(estado, patrones),
            "revision_requerida": estado in ("Revisión prioritaria", "Requiere revisión")
            or estado.startswith("Indeterminado")}
