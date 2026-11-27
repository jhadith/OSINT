"""«Mi panorama»: lo que el personal de salud puede saber de la seguridad del mes, ya filtrado en el servidor.

Regla de oro: aquí solo salen cantidades y frases simples. Nunca IPs, cuentas, seudónimos, nombres, horarios
exactos ni identificadores de casos. Aunque alguien lea la respuesta de la API, no encuentra nada técnico.
"""
from __future__ import annotations

from collections import Counter

from fastapi import HTTPException

from . import avisos, datos, denuncias, impacto, riesgos

# Categorías en lenguaje simple. «riesgos»: qué riesgos de la matriz cuentan para cada una.
CATEGORIAS = [
    ("claves", "Intentos de adivinar contraseñas", ["R4"]),
    ("cuenta", "Cuentas usadas de forma extraña", ["R1"]),
    ("fuga", "Posible salida de información", ["R2"]),
    ("red", "Exploración de los sistemas", ["R7", "R5", "R3"]),
    ("citas", "Reventa de citas", ["R9"]),
    ("engano", "Mensajes y enlaces falsos", []),
]
CONSEJOS = {
    "claves": "Usa una contraseña larga y distinta para el sistema médico. Nadie de soporte te la va a pedir.",
    "cuenta": "Cierra tu sesión cuando dejes el equipo y no prestes tu usuario, ni siquiera por un momento.",
    "fuga": "No envíes historias clínicas por correo personal, WhatsApp ni USB. Usa solo los canales del sistema.",
    "red": "Si el sistema se pone lento o raro, avisa a TI en lugar de reiniciar o instalar programas.",
    "citas": "Si un paciente dice que pagó por su cita, recuérdale que es gratis y que puede denunciarlo.",
    "engano": "Antes de abrir un enlace o imagen dudosa, revísala en «Verificar contenido».",
}
SIEMPRE = "Si algo te parece raro, repórtalo. Es mejor una falsa alarma que un problema callado."
DIMENSIONES = {
    "atencion": "Si un ataque detiene los sistemas, hay que atender con procesos manuales.",
    "datos": "Las historias clínicas de tus pacientes son el blanco más buscado.",
    "citas": "La reventa de turnos deja sin cita a quien más la necesita.",
}
ESTADO_REPORTE = denuncias.ESTADOS


def _intento(fn, defecto):
    try:
        return fn()
    except (HTTPException, OSError, ValueError, KeyError):
        return defecto


def _amenazas(casos: list[dict], agenda: dict | None, dens: list[dict]) -> list[dict]:
    vigentes = [c for c in casos if c.get("estado") != "descartado"]
    cuenta: Counter = Counter()
    for c in vigentes:
        rs = set(c.get("riesgos", []))
        for cid, _, ids in CATEGORIAS:
            if rs & set(ids):
                cuenta[cid] += 1
                break
    if agenda:
        cuenta["citas"] += sum(1 for x in agenda.get("casos", []) if x.get("review_required"))
    cuenta["citas"] += sum(1 for d in dens if d["tipo"] == "venta_de_citas" and d["estado"] != "descartada")
    cuenta["engano"] += sum(1 for d in dens if d["tipo"] in avisos.ENGANOS and d["estado"] != "descartada")
    return [{"id": cid, "nombre": nombre, "n": cuenta.get(cid, 0)} for cid, nombre, _ in CATEGORIAS]


def _dimensiones() -> list[dict]:
    neg = _intento(lambda: impacto.negocio(riesgos.calcular()), None)
    if not neg:
        return []
    return [{"id": d["id"], "nombre": d["nombre"], "pregunta": d["pregunta"], "nivel": d["nivel"],
             "exposicion": d["exposicion"], "explicacion": DIMENSIONES[d["id"]]}
            for d in neg["dimensiones"] if d["id"] in DIMENSIONES]


def _por_dia() -> list[dict]:
    serie = _intento(lambda: datos.consola("serie"), [])
    dias: dict[str, int] = {}
    for p in serie:
        dias[p["ts"][:10]] = dias.get(p["ts"][:10], 0) + int(p.get("fallidos", 0))
    return [{"dia": k, "intentos": v} for k, v in sorted(dias.items())]


def _sector() -> list[dict]:
    lista = _intento(impacto._tendencias, [])
    out = []
    for t in lista:
        resumen = str(t.get("resumen") or "").split(". ")[0].strip().rstrip(".")
        if not resumen:
            continue
        out.append({"titulo": t["titulo"], "resumen": resumen[:160] + ".", "fuente": t.get("fuente", ""),
                    "fecha": t.get("fecha", "")})
        if len(out) == 4:
            break
    return out


def _mis_reportes(usuario: str, dens: list[dict]) -> list[dict]:
    mios = [d for d in dens if d.get("reportado_por") == usuario]
    return [{"codigo": d["codigo"], "fecha": d["fecha"], "que": (d.get("enlace") or d.get("descripcion") or
                                                                d["tipo_texto"])[:90],
             "estado": ESTADO_REPORTE.get(d["estado"], d["estado"]), "respuesta": d.get("respuesta_publica", "")}
            for d in mios[:8]]


def salud(usuario: str) -> dict:
    casos = _intento(datos.casos, [])
    agenda = _intento(datos.agendamiento, None)
    dens = _intento(denuncias.todas, [])
    amenazas = _amenazas(casos, agenda, dens)
    activas = [a["id"] for a in sorted(amenazas, key=lambda a: -a["n"]) if a["n"]]
    periodo = None
    if casos:
        res = _intento(lambda: datos.motor("resumen_motor.json", {}), {})
        periodo = (res or {}).get("periodo")
    return {
        "hayAnalisis": bool(casos),
        "periodo": periodo,
        "avisos": avisos.para(usuario),
        "amenazas": amenazas,
        "total": sum(a["n"] for a in amenazas),
        "porDia": _por_dia() if casos else [],
        "dimensiones": _dimensiones() if casos else [],
        "sector": _sector(),
        "misReportes": _mis_reportes(usuario, dens),
        "consejos": [CONSEJOS[c] for c in activas[:3]] + [SIEMPRE],
    }
