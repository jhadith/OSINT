"""Resumen de los checks de GitHub Actions para mostrarlo en la consola.

El pipeline escribe ``web/public/estado-ci.json`` al terminar cada ejecución; el backend
solo lee ese archivo. No consulta GitHub ni necesita tokens: el prototipo sigue siendo local.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

ARCHIVO = "estado-ci.json"
RESULTADOS = {"success", "failure", "cancelled", "skipped"}


def _ruta() -> Path:
    """Prefiere el JSON copiado dentro de la web compilada; si no está, usa el de origen."""
    for base in (config.WEB_DIST, config.PROYECTO / "web" / "public"):
        candidata = base / ARCHIVO
        if candidata.is_file():
            return candidata
    return config.PROYECTO / "web" / "public" / ARCHIVO


def _vacio() -> dict:
    return {"disponible": False, "generado": "", "ejecucion": "", "rama": "", "commit": "",
            "origen": "", "estado": "sin_datos", "checks": []}


def _estado(checks: list[dict]) -> str:
    if not checks:
        return "sin_datos"
    if any(c["resultado"] in ("failure", "cancelled") for c in checks):
        return "fallido"
    if any(c["resultado"] == "skipped" for c in checks):
        return "parcial"
    return "correcto"


def estado() -> dict:
    """Devuelve el resumen saneado; si el archivo no existe o está roto, devuelve un estado vacío."""
    ruta = _ruta()
    if not ruta.is_file():
        return _vacio()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _vacio()
    if not isinstance(datos, dict):
        return _vacio()

    checks = []
    for c in datos.get("checks", []):
        if not isinstance(c, dict):
            continue
        resultado = c.get("resultado")
        if resultado not in RESULTADOS:
            resultado = "skipped"
        checks.append({
            "id": str(c.get("id", ""))[:60],
            "nombre": str(c.get("nombre", ""))[:120],
            "resultado": resultado,
            "detalle": str(c.get("detalle", ""))[:200],
        })
    return {
        "disponible": True,
        "generado": str(datos.get("generado", ""))[:40],
        "ejecucion": str(datos.get("ejecucion", ""))[:40],
        "rama": str(datos.get("rama", ""))[:80],
        "commit": str(datos.get("commit", ""))[:40],
        "origen": str(datos.get("origen", ""))[:40],
        "estado": _estado(checks),
        "checks": checks,
    }
