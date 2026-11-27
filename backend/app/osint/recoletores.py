"""Recoletores OSINT de nivel 1 (S13/T15): solo GET públicos, sin claves de API y sin
dependencias nuevas (urllib, csv, json y xml.etree de la stdlib).

Todos los ítems salen por `normalizar()` con el mismo juego de 12 campos:
{fuente, tipo, id_externo, titulo, resumen, cvss, kev, exploit_publico, enlace, fecha, tags}.

`obtener()` es el ÚNICO punto de red de todo el paquete: los tests lo mockean y una guarda
de socket bloquea cualquier conexión real durante la suite.
"""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree  # nosec B405 - solo tipos; el parseo usa defusedxml

from defusedxml.ElementTree import fromstring as xml_seguro

# Navegador compatible + identificación honesta del agente (algunos CDN exigen UA con Mozilla/5.0).
UA = "Mozilla/5.0 (compatible; Sentinel-Salud-OSINT/1.0)"
TIEMPO = 15                       # timeout por recolector, en segundos
VENTANA_NVD_DIAS = 7              # ventana pubStartDate/pubEndDate (7-14 días pedidos)
NVD_MAX_PAGINA = 2000             # resultsPerPage máximo de la API 2.0

# La URL del spec (…/sites/defaultfeeds/feeds/…) responde 404; se usa el feed real de CISA
# en …/sites/default/files/feeds/… (mismo catálogo completo KEV, verificado con GET 200).
URL_KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# La URL del spec (…/exploitdb/-raw/…) responde 302→403; se usa la ruta estándar de GitLab
# …/exploitdb/-/raw/main/files_exploits.csv (verificada con GET 200).
URL_EXPLOITDB = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv"

_CAMPOS = ("fuente", "tipo", "id_externo", "titulo", "resumen", "cvss", "kev",
           "exploit_publico", "enlace", "fecha", "tags")
_CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def obtener(url: str, timeout: int = TIEMPO, headers: dict | None = None) -> bytes:
    """GET público con timeout. Única función que toca la red; nunca envía datos propios."""
    if not url.startswith("https://"):
        raise ValueError("solo se consultan fuentes oficiales por https")
    peticion = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:  # nosec B310 - solo https, URLs fijas
        return respuesta.read()


# ---------- normalización ----------
def _espacios(texto: object, tope: int = 600) -> str:
    """Texto limpio: quita etiquetas HTML, colapsa espacios y recorta."""
    s = unescape(re.sub(r"<[^>]+>", " ", str(texto or "")))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:tope]


def _fecha(valor: object) -> str | None:
    """Cualquier formato de fecha razonable → AAAA-MM-DD; inválido → None (no se inventa)."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    s = str(valor).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(s).date().isoformat()   # pubDate RFC 822
    except Exception:
        return None


def _cvss(valor: object) -> float | None:
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    return round(f, 1) if 0.0 <= f <= 10.0 else None


def _cves(texto: str) -> set[str]:
    return {c.upper() for c in _CVE.findall(texto or "")}


def normalizar(tipo: str, fuente: str, campos: dict) -> dict:
    """Ítem normalizado con el juego de campos exacto del spec (S13)."""
    return {
        "fuente": fuente,
        "tipo": tipo,
        "id_externo": str(campos.get("id_externo") or "").strip(),
        "titulo": _espacios(campos.get("titulo"), 300),
        "resumen": _espacios(campos.get("resumen")),
        "cvss": _cvss(campos.get("cvss")),
        "kev": bool(campos.get("kev", tipo == "kev")),
        "exploit_publico": bool(campos.get("exploit_publico", tipo == "exploit")),
        "enlace": str(campos.get("enlace") or "").strip(),
        "fecha": _fecha(campos.get("fecha")),
        "tags": [t for t in dict.fromkeys(str(x).strip() for x in campos.get("tags") or [] if str(x).strip())],
    }


# ---------- parsers por fuente ----------
def parse_kev(datos: bytes) -> list[dict]:
    """CISA Known Exploited Vulnerabilities (catálogo completo en JSON)."""
    catalogo = json.loads(datos)
    salida = []
    for v in catalogo.get("vulnerabilities", []):
        cve = str(v.get("cveID") or "")
        if not cve:
            continue
        salida.append(normalizar("kev", "CISA", {
            "id_externo": cve,
            "titulo": f"{cve} · {v.get('vulnerabilityName', '')}",
            "resumen": v.get("shortDescription", ""),
            "fecha": v.get("dateAdded"),
            "enlace": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
            "tags": [v.get("vendorProject", ""), v.get("product", ""),
                     "KEV", v.get("knownRansomwareCampaignUse", "")],
        }))
    return salida


def _cvss_de_metricas(metricas: dict | None) -> float | None:
    for clave in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for m in (metricas or {}).get(clave) or []:
            dato = m.get("cvssData") or {}
            if "baseScore" in dato:
                return _cvss(dato["baseScore"])
    return None


def parse_nvd(datos: bytes) -> list[dict]:
    """NVD API 2.0 sin clave: una petición por sync con ventana pubStartDate/pubEndDate."""
    respuesta = json.loads(datos)
    salida = []
    for entrada in respuesta.get("vulnerabilities", []):
        cve = entrada.get("cve") or {}
        ident = str(cve.get("id") or "")
        if not ident:
            continue
        desc = next((d.get("value", "") for d in cve.get("descriptions", [])
                     if d.get("lang") == "en"), "")
        tags = ["NVD"]
        for grupo in cve.get("cveTags") or []:
            tags += grupo.get("tags") or []
        salida.append(normalizar("cve", "NVD", {
            "id_externo": ident,
            "titulo": ident,
            "resumen": desc,
            "fecha": cve.get("published"),
            "enlace": f"https://nvd.nist.gov/vuln/detail/{ident}",
            "cvss": _cvss_de_metricas(cve.get("metrics")),
            "tags": tags,
        }))
    return salida


def parse_exploitdb(datos: bytes) -> list[dict]:
    """Exploit-DB (CSV del repo gitlab estándar): explotaciones públicas con sus CVE en codes."""
    texto = datos.decode("utf-8", errors="replace")
    salida = []
    for fila in csv.DictReader(io.StringIO(texto)):
        ident = (fila.get("id") or "").strip()
        desc = (fila.get("description") or "").strip()
        if not ident or not desc:
            continue
        cves = sorted(_cves(" ".join([desc, fila.get("codes") or "", fila.get("tags") or ""])))
        salida.append(normalizar("exploit", "Exploit-DB", {
            "id_externo": ident,
            "titulo": desc,
            "resumen": f"Explotación pública ({fila.get('type') or 'desconocido'}) para "
                       f"{fila.get('platform') or 'plataforma desconocida'} · {fila.get('author') or 'autor no registrado'}",
            "fecha": fila.get("date_published") or fila.get("date_added"),
            "enlace": f"https://www.exploit-db.com/exploits/{ident}",
            "tags": cves + [fila.get("type") or "", fila.get("platform") or ""],
        }))
    return salida


def _entrada_rss(item: ElementTree.Element) -> dict:
    return {
        "titulo": item.findtext("title") or "",
        "enlace": (item.findtext("link") or "").strip(),
        "resumen": item.findtext("description") or "",
        "fecha": item.findtext("pubDate") or item.findtext("published") or item.findtext("updated"),
        "id_externo": (item.findtext("guid") or item.findtext("link")
                       or item.findtext("title") or "").strip(),
    }


def _entrada_atom(entrada: ElementTree.Element) -> dict:
    ns = "{http://www.w3.org/2005/Atom}"
    enlace = ""
    for enlace_xml in entrada.findall(f"{ns}link"):
        if enlace_xml.get("href"):
            enlace = enlace_xml.get("href")
            break
    resumen = entrada.findtext(f"{ns}summary") or entrada.findtext(f"{ns}content") or ""
    fecha = (entrada.findtext(f"{ns}published") or entrada.findtext(f"{ns}updated") or "")
    return {
        "titulo": entrada.findtext(f"{ns}title") or "",
        "enlace": enlace,
        "resumen": resumen,
        "fecha": fecha,
        "id_externo": (entrada.findtext(f"{ns}id") or enlace).strip(),
    }


def parse_rss(datos: bytes, fuente: str, tipo: str) -> list[dict]:
    """RSS 2.0 y Atom con xml.etree (stdlib): CERT, PSIRT y prensa."""
    raiz = xml_seguro(datos)
    es_atom = raiz.tag.endswith("feed")
    entradas = ([_entrada_atom(e) for e in raiz if e.tag.endswith("entry")] if es_atom
                else [_entrada_rss(e) for e in raiz.iter("item")])
    return [normalizar(tipo, fuente, e) for e in entradas if e["id_externo"] or e["titulo"]]


def parse_otx(datos: bytes) -> list[dict]:
    """AlienVault OTX (solo con OTX_API_KEY): pulsos de inteligencia abierta."""
    respuesta = json.loads(datos)
    salida = []
    for p in respuesta.get("results", []):
        ident = str(p.get("id") or "")
        if not ident:
            continue
        salida.append(normalizar("pulso", "AlienVault OTX", {
            "id_externo": ident,
            "titulo": p.get("name") or "",
            "resumen": p.get("description") or "",
            "fecha": p.get("created"),
            "enlace": f"https://otx.alienvault.com/pulse/{ident}",
            "tags": p.get("tags") or [],
        }))
    return salida


# ---------- registro de fuentes ----------
def url_nvd(hoy: date | None = None) -> str:
    """Ventana reciente de publicación (7 días) en UNA petición (sin clave: ~5 req/30 s)."""
    hoy = hoy or date.today()
    inicio = hoy - timedelta(days=VENTANA_NVD_DIAS)
    return ("https://services.nvd.nist.gov/rest/json/cves/2.0"
            f"?pubStartDate={inicio.isoformat()}T00:00:00.000"
            f"&pubEndDate={hoy.isoformat()}T23:59:59.000"
            f"&resultsPerPage={NVD_MAX_PAGINA}")


def _fuente(id_: str, nombre: str, tipo: str, url: str, parse, headers: dict | None = None) -> dict:
    return {"id": id_, "nombre": nombre, "tipo": tipo, "url": url, "parse": parse, "headers": headers}


def _rss(id_: str, nombre: str, tipo: str, url: str) -> dict:
    # el parse queda atado al nombre/tipo de la fuente para que el ítem lleve su procedencia
    return _fuente(id_, nombre, tipo, url,
                   lambda datos, n=nombre, t=tipo: parse_rss(datos, n, t))


def fuentes() -> list[dict]:
    """Solo fuentes oficiales y verificables (CTI y TECHINT): catálogos de gobierno, CERT nacionales y avisos
    oficiales de fabricantes. Se excluyen medios, blogs, repositorios de exploits sin verificar y feeds
    comunitarios para no meter ruido ni falsos positivos en la inteligencia externa."""
    return [
        _fuente("cisa_kev", "CISA", "kev", URL_KEV, parse_kev),
        _fuente("nvd", "NVD", "cve", url_nvd(), parse_nvd),
        _rss("cisa_alertas", "CISA", "boletin", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
        _rss("incibe", "INCIBE-CERT", "boletin", "https://www.incibe.es/incibe-cert/alerta-temprana/avisos/feed"),
        _rss("fortinet", "Fortinet PSIRT", "psirt", "https://www.fortiguard.com/rss/ir.xml"),
        _rss("paloalto", "Palo Alto PSIRT", "psirt", "https://security.paloaltonetworks.com/rss.xml"),
        _rss("ubuntu", "Ubuntu Security Notices", "psirt", "https://ubuntu.com/security/notices/rss.xml"),
    ]


def notas_omitidas() -> list[str]:
    """Fuentes degradadas u omitidas en nivel 1, con su motivo (se muestra en la API/pantalla)."""
    return ["Solo fuentes oficiales: se excluyen medios, blogs, Exploit-DB y feeds comunitarios."]


def recolectar(fuente: dict) -> list[dict]:
    """Fetch + parse de UNA fuente: cualquier fallo lo captura el llamador (sync tolerante)."""
    datos = obtener(fuente["url"], headers=fuente.get("headers"))
    return fuente["parse"](datos)
