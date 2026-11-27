"""Tickets de cambio de reglas: el analista del SOC pide crear, ajustar o desactivar una regla y TI la atiende.

Solo se agregan líneas (control de repudio): la creación va a «tickets» y cada cambio de estado a
«tickets_estado»; el estado vigente es la última línea por código. Cada paso queda en la bitácora y al
crearse se avisa a TI por Telegram (simulado si no hay token).
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException

from . import config, estado

TIPOS = {
    "nueva": "Crear una regla nueva",
    "ajustar": "Ajustar una regla existente (umbral, horario, alcance)",
    "desactivar": "Desactivar una regla que genera falsas alertas",
    "indicador": "Agregar un indicador (IP, dominio, cuenta) a una regla",
}
PRIORIDADES = {"alta": "Alta", "media": "Media", "baja": "Baja"}
ESTADOS = {"abierto": "Abierto", "en_progreso": "En progreso", "aplicado": "Aplicado", "rechazado": "Rechazado"}


def _codigo() -> str:
    return "TK-" + secrets.token_hex(3).upper()


def todos() -> list[dict]:
    vigente = estado.ultimo_por("tickets_estado", "codigo")
    out = []
    for t in estado.leer("tickets"):
        e = vigente.get(t["codigo"])
        out.append({**t, "estado": e["estado"] if e else "abierto", "respuesta": e["respuesta"] if e else "",
                    "atendido_por": e["actor"] if e else "", "actualizado": e["fecha"] if e else t["fecha"],
                    "tipo_texto": TIPOS.get(t["tipo"], t["tipo"])})
    return sorted(out, key=lambda t: t["actualizado"], reverse=True)


def uno(codigo: str) -> dict:
    t = next((x for x in todos() if x["codigo"] == codigo), None)
    if not t:
        raise HTTPException(404, "No existe ese ticket.")
    return t


def crear(d: dict, actor: str, rol: str) -> dict:
    t = {"codigo": _codigo(), "fecha": estado.ahora(), "autor": actor, "tipo": d["tipo"], "regla": d["regla"],
         "titulo": d["titulo"], "descripcion": d["descripcion"], "prioridad": d["prioridad"],
         "caso": d.get("caso") or ""}
    estado.agregar("tickets", t)
    estado.bitacora(actor, rol, "Ticket de regla creado", t["codigo"], f"{TIPOS[t['tipo']]}: {t['titulo']}")
    _avisar_ti(t, actor, rol)
    return uno(t["codigo"])


def gestionar(codigo: str, nuevo: str, respuesta: str, actor: str, rol: str) -> dict:
    t = uno(codigo)
    if t["estado"] in ("aplicado", "rechazado"):
        raise HTTPException(400, "Ese ticket ya está cerrado.")
    estado.agregar("tickets_estado", {"codigo": codigo, "estado": nuevo, "respuesta": respuesta, "actor": actor,
                                      "fecha": estado.ahora()})
    estado.bitacora(actor, rol, f"Ticket {ESTADOS[nuevo].lower()}", codigo, respuesta)
    return uno(codigo)


def _avisar_ti(t: dict, actor: str, rol: str) -> None:
    texto = (f"Sentinel Salud · Nuevo ticket {t['codigo']} para TI\n"
             f"Prioridad {PRIORIDADES[t['prioridad']]}: {TIPOS[t['tipo']]}\n"
             f"Regla: {t['regla']}\n{t['titulo']}")
    detalle = "Simulación: el envío real se activa con SENTINEL_TELEGRAM=enviar"
    if config.TELEGRAM_ENVIAR:
        try:
            from .telegram import _enviar
            _enviar(texto)
            detalle = "Enviado por Telegram al equipo de TI"
        except Exception as e:  # el ticket se crea igual aunque falle el aviso
            detalle = f"No se pudo enviar por Telegram: {e}"
    estado.bitacora(actor, rol, "Aviso a TI", t["codigo"], detalle)
