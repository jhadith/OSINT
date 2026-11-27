"""Avisos de seguridad para el personal de salud.

Un aviso es un mensaje corto, en lenguaje simple, que le dice al médico qué está pasando y qué debe hacer.
Nunca lleva IPs, cuentas, seudónimos, nombres ni detalles del caso: solo lo que el personal necesita para
cuidarse. Hay dos orígenes:

- Automático: al terminar un análisis, si el motor encontró algo que afecta al personal (posible fuga de datos,
  cuenta usada de forma extraña, intentos de adivinar contraseñas, reventa de citas) y cuando llegan varias
  denuncias de mensajes o enlaces falsos en la misma semana.
- Manual: el analista lo escribe desde un caso, partiendo de un texto sugerido.

Cada aviso queda en el stream «avisos» (solo agregar) y cada «Entendido» en «avisos_leidos», con su registro en la
bitácora: así queda evidencia de que el personal fue informado (concientización, LOPDP).
"""
from __future__ import annotations

import datetime as dt
import re
import secrets

from fastapi import HTTPException

from . import estado, telegram

# Plantillas por categoría. «riesgos» son los de la matriz que disparan el aviso.
PLANTILLAS: dict[str, dict] = {
    "fuga": {
        "riesgos": ["R2"], "nivel": "alto",
        "titulo": "Posible salida de información del sistema médico",
        "texto": "Se detectó una posible salida de información del sistema médico. El equipo de seguridad ya lo "
                 "está revisando.",
        "consejo": "Mientras tanto, no compartas historias clínicas por correo personal, WhatsApp ni USB, y avisa "
                   "si ves accesos raros con tu usuario.",
    },
    "cuenta": {
        "riesgos": ["R1"], "nivel": "alto",
        "titulo": "Una cuenta del sistema médico se usó de forma extraña",
        "texto": "Se vio una cuenta del sistema médico usada en horarios o de formas que no son normales.",
        "consejo": "Cierra tu sesión al dejar el equipo, no prestes tu usuario y cambia tu contraseña si la "
                   "compartiste alguna vez.",
    },
    "claves": {
        "riesgos": ["R4"], "nivel": "medio",
        "titulo": "Intentos de adivinar contraseñas",
        "texto": "Alguien intentó entrar a los sistemas probando muchas contraseñas.",
        "consejo": "Usa una contraseña larga que no uses en otro lado y nunca la des por teléfono ni por mensaje, "
                   "aunque digan que son de soporte técnico.",
    },
    "citas": {
        "riesgos": ["R9"], "nivel": "medio",
        "titulo": "Reventa de citas médicas",
        "texto": "Se detectaron orígenes que acaparan citas del chatbot, posiblemente para revenderlas.",
        "consejo": "Si un paciente te cuenta que pagó por su cita, recuérdale que es gratis e invítalo a usar el "
                   "canal de denuncias.",
    },
    "engano": {
        "riesgos": ["R4"], "nivel": "medio",
        "titulo": "Circulan mensajes y enlaces falsos",
        "texto": "Esta semana llegaron varias denuncias de mensajes o enlaces falsos que piden datos o claves.",
        "consejo": "Antes de abrir un enlace o una imagen que te parezca rara, revísala en «Verificar contenido».",
    },
}
ENGANOS = ("enlace_sospechoso", "pedido_de_datos", "contenido_reportado")
UMBRAL_ENGANOS = 3                       # denuncias de engaño en 7 días que disparan el aviso
NIVELES = ("alto", "medio", "info")
# Lo que nunca debe salir en un aviso: IPs, cédulas, correos y seudónimos del motor.
_PROHIBIDO = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|\b\d{10}\b|[\w.+-]+@[\w-]+\.[\w.]+|\bSEU-[0-9A-F]+\b", re.I)


def limpiar(texto: str) -> str:
    """Quita del texto IPs, cédulas, correos y seudónimos (por si un analista los pega sin querer)."""
    return _PROHIBIDO.sub("[dato retirado]", (texto or "").strip())


def _todos() -> dict[str, dict]:
    return estado.ultimo_por("avisos", "codigo")


def todos() -> list[dict]:
    return sorted(_todos().values(), key=lambda a: a["fecha"], reverse=True)


def _ya_existe(clave: str) -> bool:
    return any(a.get("clave") == clave for a in _todos().values())


def crear(titulo: str, texto: str, consejo: str, nivel: str, origen: str, actor: str, rol: str,
          clave: str = "", caso: str = "") -> dict:
    if nivel not in NIVELES:
        raise HTTPException(422, "Revisa estos datos: nivel.")
    reg = {"codigo": "AV-" + secrets.token_hex(3).upper(), "fecha": estado.ahora(), "origen": origen,
           "nivel": nivel, "titulo": limpiar(titulo), "texto": limpiar(texto), "consejo": limpiar(consejo),
           "clave": clave, "caso": caso, "autor": actor}
    enviado, detalle = telegram.avisar_personal(f"Sentinel Salud · {reg['titulo']}\n{reg['texto']}\n{reg['consejo']}")
    reg["telegram"] = "enviado" if enviado else ("simulado" if detalle.startswith("Simulación") else "error")
    estado.agregar("avisos", reg)
    estado.bitacora(actor, rol, "Aviso al personal de salud", reg["codigo"], f"{reg['titulo']} · Telegram: {detalle}")
    return reg


def sugerido(caso: dict) -> dict:
    """Texto sugerido para avisar al personal a partir de un caso, sin datos técnicos."""
    cat = categoria_de(caso.get("riesgos", []))
    p = PLANTILLAS.get(cat or "", {
        "nivel": "info", "titulo": "Actividad sospechosa en los sistemas",
        "texto": "El equipo de seguridad está revisando una actividad sospechosa en los sistemas.",
        "consejo": "Si notas algo raro con tu usuario o con el sistema médico, avisa al equipo de seguridad.",
    })
    return {"titulo": p["titulo"], "texto": p["texto"], "consejo": p["consejo"], "nivel": p["nivel"]}


def categoria_de(riesgos: list[str]) -> str | None:
    for cat in ("fuga", "cuenta", "claves", "citas"):
        if set(PLANTILLAS[cat]["riesgos"]) & set(riesgos):
            return cat
    return None


def tras_analisis(analisis_id: str, casos: list[dict], agenda: dict | None) -> list[dict]:
    """Avisos automáticos al terminar un análisis: uno por categoría que afecta al personal."""
    cats: list[str] = []
    for c in casos:
        if c.get("estado") == "descartado" or c.get("gravedad") not in ("critica", "alta"):
            continue
        cat = categoria_de(c.get("riesgos", []))
        if cat and cat not in cats:
            cats.append(cat)
    if agenda and any(x.get("status") == "Revisión prioritaria" for x in agenda.get("casos", [])):
        cats.append("citas")
    nuevos = []
    for cat in cats:
        clave = f"{analisis_id}:{cat}"
        if _ya_existe(clave):
            continue
        p = PLANTILLAS[cat]
        nuevos.append(crear(p["titulo"], p["texto"], p["consejo"], p["nivel"], "automatico",
                            "Sentinel Salud", "Avisos", clave=clave))
    return nuevos


def tras_denuncia(denuncias: list[dict]) -> dict | None:
    """Si en los últimos 7 días llegaron varias denuncias de engaño, avisa una vez por semana."""
    hoy = dt.datetime.now()
    hace7 = (hoy - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    n = sum(1 for d in denuncias if d["tipo"] in ENGANOS and d["fecha"] >= hace7 and d["estado"] != "descartada")
    if n < UMBRAL_ENGANOS:
        return None
    anio, semana, _ = hoy.isocalendar()
    clave = f"engano:{anio}-{semana:02d}"
    if _ya_existe(clave):
        return None
    p = PLANTILLAS["engano"]
    return crear(p["titulo"], p["texto"], p["consejo"], p["nivel"], "automatico", "Sentinel Salud", "Avisos",
                 clave=clave)


def leidos(usuario: str) -> set[str]:
    return {r["codigo"] for r in estado.leer("avisos_leidos") if r["usuario"] == usuario}


def para(usuario: str, limite: int = 20) -> list[dict]:
    """Avisos para una persona, con su marca de leído. Solo los campos que el personal puede ver."""
    ya = leidos(usuario)
    lista = [{k: a[k] for k in ("codigo", "fecha", "nivel", "titulo", "texto", "consejo", "origen")} |
             {"leido": a["codigo"] in ya} for a in todos()[:limite]]
    # primero lo que falta leer y, dentro de eso, lo más importante; la fecha ya viene de más nueva a más vieja
    return sorted(lista, key=lambda a: (a["leido"], NIVELES.index(a["nivel"])))


def marcar_leido(codigo: str, usuario: str, nombre: str, rol: str) -> dict:
    if codigo not in _todos():
        raise HTTPException(404, "No existe ese aviso.")
    if codigo in leidos(usuario):
        return {"codigo": codigo, "leido": True}
    estado.agregar("avisos_leidos", {"codigo": codigo, "usuario": usuario, "fecha": estado.ahora()})
    estado.bitacora(nombre, rol, "Aviso leído", codigo, "El personal de salud confirmó que leyó el aviso")
    return {"codigo": codigo, "leido": True}
