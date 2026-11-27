"""Canal de denuncias para afiliados y jubilados, y reportes del personal de salud.

Mínimo necesario (LOPDP): no se pide cédula ni nombre. El contacto sospechoso que la persona reporta se guarda solo
como seudónimo (para cruzarlo con el módulo de agendamiento, patrón HG-07) y en forma enmascarada para el SOC.
El contacto para responder es opcional y solo lo ve quien gestiona denuncias.
"""
from __future__ import annotations

import secrets
import threading
import time

from fastapi import HTTPException

from . import estado, verificar

TIPOS = {
    "venta_de_citas": "Me ofrecieron una cita médica a cambio de dinero",
    "pedido_de_datos": "Me llamaron o escribieron pidiendo mis datos o claves",
    "enlace_sospechoso": "Recibí un mensaje o enlace sospechoso",
    "uso_de_mis_datos": "Creo que alguien usó mis datos o mi cita",
    "otro": "Otra situación",
    "contenido_reportado": "Contenido sospechoso reportado por el personal de salud",
}
ESTADOS = {"recibida": "Recibida", "en_revision": "En revisión", "atendida": "Atendida", "descartada": "Cerrada"}
_ventana: dict[str, list[float]] = {}
_lock = threading.Lock()


def _ref_contacto(texto: str) -> str:
    from motor.agendamiento import referencia_contacto   # misma función y sal que el motor
    return referencia_contacto(texto)


def limitar(ip: str, maximo: int = 5, segundos: int = 600) -> None:
    ahora = time.time()
    with _lock:
        v = [t for t in _ventana.get(ip, []) if ahora - t < segundos]
        if len(v) >= maximo:
            raise HTTPException(429, "Recibimos varias denuncias desde este equipo. Intenta de nuevo en unos minutos.")
        v.append(ahora)
        _ventana[ip] = v


def _enmascarar(texto: str) -> str:
    t = texto.strip()
    return ("•" * max(0, len(t) - 4)) + t[-4:] if len(t) > 4 else "••••"


def crear(datos: dict, origen: str = "ciudadano") -> dict:
    codigo = "DN-" + secrets.token_hex(3).upper()
    sospechoso = (datos.get("contacto_sospechoso") or "").strip()
    enlace = (datos.get("enlace") or "").strip()
    reg = {
        "codigo": codigo, "fecha": estado.ahora(), "origen": origen, "tipo": datos["tipo"],
        "tipo_texto": TIPOS[datos["tipo"]], "descripcion": (datos.get("descripcion") or "").strip(),
        "cuando": datos.get("cuando") or "", "medio": datos.get("medio") or "",
        "contacto_sospechoso_ref": _ref_contacto(sospechoso) if sospechoso else "",
        "contacto_sospechoso_mascara": _enmascarar(sospechoso) if sospechoso else "",
        "enlace": enlace, "verificacion": verificar.enlace(enlace) if enlace else None,
        "responder_a": (datos.get("responder_a") or "").strip(), "estado": "recibida",
        "respuesta_publica": "Recibimos tu denuncia. El equipo de seguridad la revisará.",
        "nota_interna": "", "gestionado_por": "",
    }
    estado.agregar("denuncias", reg)
    estado.bitacora("Ciudadanía" if origen == "ciudadano" else datos.get("actor", "Personal de salud"),
                    "Canal de denuncias", "Denuncia recibida", codigo, reg["tipo_texto"])
    return reg


def todas() -> list[dict]:
    return sorted(estado.ultimo_por("denuncias", "codigo").values(), key=lambda d: d["fecha"], reverse=True)


def una(codigo: str) -> dict:
    d = estado.ultimo_por("denuncias", "codigo").get(codigo)
    if not d:
        raise HTTPException(404, "No encontramos una denuncia con ese código. Revisa que esté bien escrito.")
    return d


def publica(codigo: str) -> dict:
    d = una(codigo)
    return {"codigo": d["codigo"], "fecha": d["fecha"], "tipo": d["tipo_texto"], "estado": ESTADOS[d["estado"]],
            "respuesta": d["respuesta_publica"]}


def gestionar(codigo: str, nuevo_estado: str, respuesta: str, nota: str, actor: str, rol: str) -> dict:
    d = dict(una(codigo))
    d.update(estado=nuevo_estado, respuesta_publica=respuesta or d["respuesta_publica"], nota_interna=nota,
             gestionado_por=actor, actualizado=estado.ahora())
    estado.agregar("denuncias", d)
    estado.bitacora(actor, rol, "Denuncia gestionada", codigo, f"Estado: {ESTADOS[nuevo_estado]}")
    return d


def contactos_reportados() -> dict[str, list[str]]:
    """Seudónimo de contacto -> códigos de denuncia que lo mencionan (para el patrón HG-07)."""
    out: dict[str, list[str]] = {}
    for d in todas():
        if d["contacto_sospechoso_ref"] and d["estado"] != "descartada":
            out.setdefault(d["contacto_sospechoso_ref"], []).append(d["codigo"])
    return out
