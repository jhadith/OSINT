"""Módulo Proteger: revisión local de enlaces e imágenes para el personal de salud.
No abre el enlace ni lo consulta en internet: revisa su forma contra listas y patrones de phishing conocidos.
Las imágenes se revisan por su tipo real (bytes iniciales), no por la extensión que dice el nombre."""
from __future__ import annotations

import ipaddress
import json
import re
from urllib.parse import urlsplit

from . import config

LISTAS = json.loads((config.FIJOS / "listas.json").read_text(encoding="utf-8"))
FIRMAS = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpeg", b"GIF8": "gif", b"RIFF": "webp", b"BM": "bmp"}


def _veredicto(puntuacion: int, negra: bool = False) -> str:
    return "malicioso" if negra or puntuacion >= 60 else "sospechoso" if puntuacion >= 25 else "seguro"


def enlace(entrada: str) -> dict:
    texto = (entrada or "").strip()[:2000]
    senales = []
    try:
        u = urlsplit(texto if re.match(r"^[a-z]+://", texto, re.I) else f"http://{texto}")
        host = (u.hostname or "").lower()
        if not host or " " in texto:
            raise ValueError
    except ValueError:
        return {"entrada": texto, "tipo": "enlace", "veredicto": "sospechoso", "puntuacion": 50, "lista": None,
                "senales": [{"texto": "No tiene la forma de un enlace web", "tipo": "riesgo", "peso": 50}],
                "recomendacion": "No lo abras. Si llegó por correo o mensaje, repórtalo a seguridad."}
    completo = (host + u.path).lower()
    blanca = any(host == d or host.endswith("." + d) for d in LISTAS["blanca"])
    negra = any(completo.startswith(d) or host == d for d in LISTAS["negra"])

    def r(t, p):
        senales.append({"texto": t, "tipo": "riesgo", "peso": p})
    if negra:
        r("El dominio está en la lista negra del SOC", 90)
    if u.scheme == "http" and not blanca:
        r("Usa HTTP sin cifrado", 15)
    try:
        ipaddress.ip_address(host)
        r("Apunta a una dirección IP en lugar de un dominio", 25)
    except ValueError:
        pass
    if "xn--" in host:
        r("Usa caracteres que imitan letras de otro dominio (punycode)", 35)
    if len(host.split(".")) > 4:
        r("Tiene muchos subdominios encadenados", 15)
    if re.search(r"\.(xyz|top|click|zip|monster)$", host):
        r("Extensión de dominio frecuente en phishing", 20)
    if re.search(r"(login|verific|actualiz|clave|contrasen|password|pago)", completo):
        r("Pide iniciar sesión, verificar o actualizar datos", 20)
    if re.search(r"(bit\.ly|tinyurl|acortar|t\.co)", host):
        r("Enlace acortado: no se ve el destino real", 20)
    if "@" in (u.netloc or ""):
        r("Esconde el destino real detrás de un @", 30)
    if blanca:
        senales.append({"texto": "El dominio está en la lista blanca institucional", "tipo": "confianza", "peso": 60})
    if u.scheme == "https":
        senales.append({"texto": "Usa HTTPS", "tipo": "confianza", "peso": 5})
    riesgo = sum(s["peso"] for s in senales if s["tipo"] == "riesgo")
    confianza = sum(s["peso"] for s in senales if s["tipo"] == "confianza")
    puntuacion = max(0, min(100, riesgo - confianza + 10))
    v = _veredicto(puntuacion, negra)
    return {"entrada": texto, "tipo": "enlace", "veredicto": v, "puntuacion": puntuacion,
            "lista": "negra" if negra else "blanca" if blanca else None,
            "senales": senales or [{"texto": "No se encontraron señales de riesgo conocidas", "tipo": "confianza",
                                    "peso": 0}],
            "recomendacion": {"seguro": "Puedes abrirlo. Si te pide tu clave sin motivo, detente y repórtalo.",
                              "sospechoso": "No lo abras todavía. Repórtalo y espera la revisión del SOC.",
                              "malicioso": "No lo abras ni ingreses datos. Repórtalo a seguridad ahora."}[v]}


def imagen(nombre: str, contenido: bytes) -> dict:
    n = (nombre or "imagen").lower()[:200]
    senales = []
    real = next((t for firma, t in FIRMAS.items() if contenido.startswith(firma)), None)
    inicio = contenido[:512].lstrip().lower()
    if inicio.startswith((b"<svg", b"<?xml", b"<html", b"<!doctype")) or b"<script" in contenido[:4096].lower():
        senales.append({"texto": "Es un documento SVG/HTML que puede ejecutar código al abrirse", "tipo": "riesgo",
                        "peso": 45})
    elif real is None:
        senales.append({"texto": "El contenido no corresponde a un formato de imagen conocido", "tipo": "riesgo",
                        "peso": 35})
    ext = n.rsplit(".", 1)[-1] if "." in n else ""
    if real and ext and ext not in (real, "jpg" if real == "jpeg" else real):
        senales.append({"texto": f"La extensión .{ext} no coincide con el contenido real ({real})", "tipo": "riesgo",
                        "peso": 25})
    if re.search(r"qr", n):
        senales.append({"texto": "Parece un código QR: revisa su destino como enlace", "tipo": "riesgo", "peso": 30})
    if re.search(r"(factura|pago|premio|clave)", n):
        senales.append({"texto": "El nombre del archivo usa un gancho habitual de fraude", "tipo": "riesgo",
                        "peso": 20})
    if len(contenido) > 8 * 1024 * 1024:
        senales.append({"texto": "Archivo inusualmente grande para una imagen", "tipo": "riesgo", "peso": 10})
    if real:
        senales.append({"texto": f"Formato de imagen válido ({real})", "tipo": "confianza", "peso": 5})
    puntuacion = max(0, min(100, sum(s["peso"] if s["tipo"] == "riesgo" else -s["peso"] for s in senales) + 10))
    v = _veredicto(puntuacion)
    return {"entrada": nombre, "tipo": "imagen", "veredicto": v, "puntuacion": puntuacion, "lista": None,
            "senales": senales,
            "recomendacion": "No se encontraron señales de riesgo." if v == "seguro"
            else "No la abras ni escanees su contenido. Repórtala a seguridad."}
