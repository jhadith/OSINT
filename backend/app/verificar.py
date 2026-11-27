"""Módulo Proteger: revisión local de enlaces e imágenes para el personal de salud.
No abre el enlace ni lo consulta en internet: revisa su forma contra listas y patrones de phishing conocidos.

Las listas blancas/negras las sirve el repositorio DINÁMICO (app.listas, SQLite): el enlace se
clasifica en 5 estados — blanca | negra | desconocido | typosquatting | conflicto — con detección
de typosquatting/homógrafos (similitud contra la blanca, punycode, marcas) y devuelve además las
técnicas MITRE que apliquen (T1566.002 phishing, T1583.001 dominios). Un valor que está en ambas
listas es CONFLICTO: no se da por bueno ni por malo, queda para revisión humana.

Las imágenes se revisan por su tipo real (bytes iniciales), no por la extensión que dice el nombre."""
from __future__ import annotations

import ipaddress
import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from . import listas

FIRMAS = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpeg", b"GIF8": "gif", b"RIFF": "webp", b"BM": "bmp"}

# Typosquatting: confusiones típicas de OCR y de atacantes; se comparan en su forma "visual".
_CONFUSIONES = [("rn", "m"), ("vv", "w"), ("1", "i"), ("l", "i"), ("j", "i"), ("|", "i"), ("0", "o")]
_UMBRAL_SIMILITUD = 0.88
_UMBRAL_EDICION = 2
# Keywords de marca: un dominio que imita estas marcas es typosquatting aunque no se parezca a la blanca.
_MARCAS = ("microsoft", "google", "apple", "icloud", "outlook", "whatsapp", "facebook", "instagram",
           "paypal", "amazon", "iess", "biess")

_MITRE_PHISHING = {"id": "T1566.002", "nombre": "Spearphishing Link"}
_MITRE_INFRA = {"id": "T1583.001", "nombre": "Acquire Infrastructure: Domains"}


def _veredicto(puntuacion: int, negra: bool = False) -> str:
    return "malicioso" if negra or puntuacion >= 60 else "sospechoso" if puntuacion >= 25 else "seguro"


def _clave_visual(texto: str) -> str:
    """Forma visual de un dominio: micr0soft y micr0s0ft (y su lectura OCR) se comparan iguales."""
    d = texto.lower()
    for a, b in _CONFUSIONES:
        d = d.replace(a, b)
    return d


def _distancia_edicion(a: str, b: str) -> int:
    """Distancia de Levenshtein (dominios cortos: programación dinámica de una fila)."""
    if a == b:
        return 0
    previo = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previo[j] + 1, actual[j - 1] + 1, previo[j - 1] + (ca != cb)))
        previo = actual
    return previo[-1]


def _host_idn(host: str) -> bool:
    """True si el host usa punycode o caracteres no ASCII (homógrafos cirílicos, etc.)."""
    return "xn--" in host or any(ord(c) > 127 for c in host)


def _typosquatting(host: str, blancos: list[str]) -> tuple[bool, str | None]:
    """¿Imita el host a un dominio de la lista blanca o a una marca? Devuelve (¿sí?, referencia)."""
    if _host_idn(host):
        return True, None
    clave = _clave_visual(host)
    for dominio in blancos:
        forma = _clave_visual(dominio)
        if not forma:
            continue
        if (forma in clave or SequenceMatcher(None, clave, forma).ratio() >= _UMBRAL_SIMILITUD
                or (min(len(clave), len(forma)) >= 8 and _distancia_edicion(clave, forma) <= _UMBRAL_EDICION)):
            return True, dominio
    if any(_clave_visual(marca) in clave for marca in _MARCAS):
        return True, None
    return False, None


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
                "clasificacion": "desconocido", "tecnicas": [], "referencia": None,
                "senales": [{"texto": "No tiene la forma de un enlace web", "tipo": "riesgo", "peso": 50}],
                "recomendacion": "No lo abras. Si llegó por correo o mensaje, repórtalo a seguridad."}
    vigentes = listas.listas()
    completo = (host + u.path).lower()
    blanca = any(host == d or host.endswith("." + d) for d in vigentes["blanca"])
    negra = any(completo.startswith(d) or host == d for d in vigentes["negra"])
    referencia = None
    if blanca and negra:
        clasificacion = "conflicto"                    # en ambas: revisión humana, ni bueno ni malo
    elif negra:
        clasificacion = "negra"
    elif blanca:
        clasificacion = "blanca"
    else:
        typos, referencia = _typosquatting(host, vigentes["blanca"])
        clasificacion = "typosquatting" if typos else "desconocido"

    def r(t, p):
        senales.append({"texto": t, "tipo": "riesgo", "peso": p})

    gancho = bool(re.search(r"(login|verific|actualiz|clave|contrasen|password|pago)", completo))
    if clasificacion == "negra":
        r("El dominio está en la lista negra del SOC", 90)
    elif clasificacion == "conflicto":
        r("Está en la lista blanca y en la negra a la vez: requiere revisión humana del SOC", 40)
    elif clasificacion == "typosquatting":
        if referencia:
            r(f"Se parece a un dominio de la lista blanca ({referencia})", 45)
        elif _host_idn(host):
            r("Usa caracteres que imitan letras de otro dominio (punycode u homógrafos)", 45)
        else:
            r("Usa en su nombre una marca conocida para parecerse a un sitio legítimo (typosquatting)", 45)
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
    if gancho:
        r("Pide iniciar sesión, verificar o actualizar datos", 20)
    if re.search(r"(bit\.ly|tinyurl|acortar|t\.co)", host):
        r("Enlace acortado: no se ve el destino real", 20)
    if "@" in (u.netloc or ""):
        r("Esconde el destino real detrás de un @", 30)
    if blanca and clasificacion != "conflicto":
        senales.append({"texto": "El dominio está en la lista blanca institucional", "tipo": "confianza", "peso": 60})
    if u.scheme == "https":
        senales.append({"texto": "Usa HTTPS", "tipo": "confianza", "peso": 5})
    riesgo = sum(s["peso"] for s in senales if s["tipo"] == "riesgo")
    confianza = sum(s["peso"] for s in senales if s["tipo"] == "confianza")
    puntuacion = max(0, min(100, riesgo - confianza + 10))
    if clasificacion == "conflicto":
        puntuacion, v = 50, "sospechoso"               # fijo para revisión humana: ni blanco ni negro
    else:
        v = _veredicto(puntuacion, negra=(clasificacion == "negra"))
    if clasificacion == "negra":
        tecnicas = [dict(_MITRE_PHISHING)]
    elif clasificacion == "typosquatting":
        tecnicas = [dict(_MITRE_INFRA)]
    elif clasificacion == "desconocido" and gancho:
        tecnicas = [dict(_MITRE_PHISHING)]
    else:
        tecnicas = []
    return {"entrada": texto, "tipo": "enlace", "veredicto": v, "puntuacion": puntuacion,
            "lista": "negra" if negra else "blanca" if blanca else None,
            "clasificacion": clasificacion, "tecnicas": tecnicas, "referencia": referencia,
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
