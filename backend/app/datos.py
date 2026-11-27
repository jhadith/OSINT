"""Lectura del análisis activo con el estado de la consola encima (decisiones, avisos, denuncias)."""
from __future__ import annotations

import json

from fastapi import HTTPException

from . import analisis, estado


def _salidas():
    s = analisis.salidas_activas()
    if s is None:
        raise HTTPException(409, "Todavía no hay un análisis. Carga los datos en «Cargar datos» para empezar.")
    return s


def consola(nombre: str):
    f = _salidas() / "consola" / f"{nombre}.json"
    if not f.exists():
        raise HTTPException(409, "El análisis activo no tiene esta información.")
    return json.loads(f.read_text(encoding="utf-8"))


def motor(nombre: str, defecto=None):
    f = _salidas() / nombre
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else defecto


def clave_decision(caso_id: str) -> str:
    """Las decisiones son por análisis: el C3 de octubre no es el C3 de noviembre."""
    return f"{analisis.activo_id()}:{caso_id}"


def casos() -> list[dict]:
    lista = consola("casos")
    dec = estado.ultimo_por("decisiones", "clave")
    av = estado.ultimo_por("telegram", "clave")
    for c in lista:
        d = dec.get(clave_decision(c["id"]))
        if d:
            c["estado"] = d["estado"]
            c["decision"] = {k: d[k] for k in ("estado", "motivo", "analista", "fecha")}
            c["recorrido"] = [p if p["paso"] != "Decisión y respuesta" else
                              {**p, "detalle": f"Caso {d['estado']} por {d['analista']}: {d['motivo']}"}
                              for p in c["recorrido"]]
        a = av.get(clave_decision(c["id"]))
        if c.get("alerta") and a:
            c["alerta"] = {**c["alerta"], "enviada": a["enviada"], "fecha": a["fecha"], "modo": a["modo"]}
    return lista


def caso(caso_id: str) -> dict:
    for c in casos():
        if c["id"] == caso_id:
            return c
    raise HTTPException(404, f"No existe el caso {caso_id} en el análisis activo.")


def agendamiento() -> dict | None:
    a = motor("agendamiento.json")
    if not a:
        return None
    from .denuncias import contactos_reportados
    reportados = contactos_reportados()
    revisiones = estado.ultimo_por("revisiones_agenda", "clave")
    for c in a["casos"]:
        vinculadas = sorted({cod for ref in c.get("contactos_ref", []) for cod in reportados.get(ref, [])})
        c["denuncias_vinculadas"] = vinculadas
        r = revisiones.get(f"{analisis.activo_id()}:{c['case_id']}")
        c["revision"] = {k: r[k] for k in ("decision", "nota", "analista", "fecha")} if r else None
        c.pop("contactos_ref", None)      # el seudónimo del contacto no sale de la API
    return a
