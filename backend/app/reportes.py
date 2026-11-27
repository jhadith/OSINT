"""Exportes HTML autocontenidos con diagramas SVG para gerencia y para presentación (S14/T16).

Dos plantillas genéricas —no hardcodeadas— alimentadas SOLO por el dict que reciban:
mismo código con datasets distintos produce informes distintos y correctos. Solo stdlib
(html.escape + f-strings; sin Jinja ni dependencias nuevas), cero recursos externos
(todo inline, sin CDN) y `@media print` para que «Guardar como PDF» del navegador dé un
documento pulido. Salida determinista: sin reloj ni fechas de emisión.

Contrato de `datos` (dict; TODAS las claves son OPCIONALES; las claves desconocidas se
ignoran; las sublistas aceptan entradas con claves de más; cualquier entrada que no sea
dict se descarta; todo dato de entrada se escapa con html.escape antes de renderizar):

  periodo: str | dict          Texto libre del período; si es dict {"desde":…, "hasta":…}
                               se une con " a ". Ausente → "sin datos".
  resumen: str                 Frase del «qué pasó este mes» (gerencial) y del resumen
                               ejecutivo (presentación). Ausente → se deriva de los casos
                               o "sin datos".
  kpis: dict                   Solo el gerencial (semáforo):
                                 "alertas": {"critica": int, "alta": int, "media": int,
                                             "baja": int}   ← luces por gravedad
                                 "cuentas_a_revisar": int     ← 0 verde, >0 rojo
                                 "conexiones_inseguras": int  ← 0 verde, >0 ámbar
                               Cada subclave ausente → "sin datos" con luz gris.
  casos: list[dict]            {"titulo": str, "fecha": str (alias "inicio"),
                                "gravedad": str ("crítica|alta|media|baja"),
                                "frase": str (alias "explicacion" | "resumen")}
                               Claves extra (ipOrigen, cuenta, tecnicas, seudonimo…)
                               se ignoran: el gerencial jamás las renderiza.
  riesgos: list[dict]          {"id": str, "nombre": str, "probabilidad": 1-5,
                                "impacto": 1-5, "nivel": 1-25,
                                "recomendacion": str (alias "tratamiento" | "asignacion"),
                                "casos": list (opcional, solo presentación)}
  tendencias: list[dict]       {"titulo": str (alias "nombre"), "fuente": str,
                                "estado": str, "marca": "real" | "simulado"
                                (alias "sello"; o bool "simulado")}
  controles: list[dict]        {"control": str (alias "nombre"; con "id" se antepone),
                                "estado": str}   ← badge con color según brecha
  tecnicas: list[dict]         {"id": str, "nombre": str, "detalle": str}
                               Técnicas MITRE: SOLO en el anexo de la presentación.
  indicadores: list[dict]      {"nombre": str, "valor": str, "nota": str}
                               SOLO en el anexo de la presentación (puede traer IPs).
  recomendaciones: list[str | dict]   Prioridades del gerencial (dict con "texto" |
                               "recomendacion"); si falta, se derivan de los riesgos
                               ordenados por nivel descendente.

Prohibido en el gerencial: IPs, cuentas, nombres personales, técnicas MITRE y scores
numéricos crudos — solo seudónimos, frases y colores. El informe de presentación sí
muestra el detalle técnico, pero separado en su anexo final.
"""
from __future__ import annotations

import html
import json
from datetime import date

SIN_DATOS = "sin datos"

COLORES_GRAVEDAD = {
    "critica": "#c62828", "crítica": "#c62828",
    "alta": "#ef6c00",
    "media": "#f9a825",
    "baja": "#2e7d32",
}
COLOR_DESCONOCIDO = "#78909c"


# ---------------------------------------------------------------------------
# Utilidades de datos tolerantes
# ---------------------------------------------------------------------------
def _esc(valor) -> str:
    """Todo texto de datos pasa por aquí: los informes nunca interpretan HTML de entrada."""
    return html.escape(str(valor), quote=True)


def _entero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor) if valor == int(valor) else None
    if isinstance(valor, str):
        try:
            return int(valor.strip())
        except ValueError:
            return None
    return None


def _texto_opt(d: dict, *claves):
    """Primer valor no vacío entre las claves, o None (ausente = "sin datos" para el caller)."""
    for k in claves:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _texto(d: dict, *claves) -> str:
    return _texto_opt(d, *claves) or SIN_DATOS


def _lista(datos: dict, clave: str) -> list[dict]:
    v = datos.get(clave)
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, dict)]


def _rango1a5(valor):
    n = _entero(valor)
    return n if n is not None and 1 <= n <= 5 else None


def _nivel(r: dict):
    """Nivel 1-25 del riesgo: el dado, o probabilidad × impacto; si nada es válido, None."""
    n = _entero(r.get("nivel"))
    if n is not None and 1 <= n <= 25:
        return n
    p, i = _rango1a5(r.get("probabilidad")), _rango1a5(r.get("impacto"))
    return p * i if p is not None and i is not None else None


def _color_nivel(n):
    if n is None:
        return COLOR_DESCONOCIDO
    if n >= 20:
        return "#c62828"
    if n >= 12:
        return "#ef6c00"
    if n >= 6:
        return "#f9a825"
    return "#2e7d32"


def _tinte(n: int) -> str:
    """Fondo de la celda de la matriz, versión clara del color de nivel."""
    if n >= 20:
        return "#ffebee"
    if n >= 12:
        return "#fff3e0"
    if n >= 6:
        return "#fff8e1"
    return "#e8f5e9"


def _color_gravedad(g) -> str:
    return COLORES_GRAVEDAD.get(str(g).strip().lower(), COLOR_DESCONOCIDO)


def _color_estado(estado) -> str:
    e = str(estado).strip().lower()
    if not e or e == SIN_DATOS:
        return COLOR_DESCONOCIDO
    if "brecha" in e:
        return "#c62828"
    if "conforme" in e or "implementa" in e or "cumple" in e:
        return "#2e7d32"
    return "#f9a825"


def _cortar(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _como_fecha(c: dict):
    v = _texto_opt(c, "fecha", "inicio")
    if v is None or len(v) < 10:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def _casos_ordenados(casos: list[dict]) -> list[dict]:
    con = sorted([c for c in casos if _como_fecha(c) is not None], key=_como_fecha)
    sin = [c for c in casos if _como_fecha(c) is None]
    return con + sin


def _periodo(datos: dict) -> str:
    p = datos.get("periodo")
    if isinstance(p, dict):
        partes = [str(p[k]) for k in ("desde", "hasta") if p.get(k) not in (None, "")]
        return " a ".join(partes) if partes else SIN_DATOS
    if isinstance(p, str) and p.strip():
        return p
    return SIN_DATOS


def _resumen(datos: dict, casos: list[dict]) -> str:
    r = _texto_opt(datos, "resumen")
    if r:
        return r
    if casos:
        return f"Este período se revisaron {len(casos)} caso(s)."
    return SIN_DATOS


def _marca(t: dict):
    """(texto, clase) de la marca real/simulado de una tendencia; sin marca → "sin datos"."""
    m = t.get("marca")
    if m is None:
        m = t.get("sello")
    if m is None and isinstance(t.get("simulado"), bool):
        m = "simulado" if t["simulado"] else "real"
    if m is None or not str(m).strip():
        return SIN_DATOS, "desconocida"
    m = str(m).strip().lower()
    if m in ("real", "simulado"):
        return m, m
    return m, "otro"


def _conteo(d: dict, *claves):
    for k in claves:
        if k in d:
            return _entero(d[k])
    return None


# ---------------------------------------------------------------------------
# Diagramas SVG (inline, sin xmlns externo ni recursos referenciados)
# ---------------------------------------------------------------------------
def _burbujas_posiciones(n: int):
    """(offsetes dx,dy) y radio para n riesgos en la misma celda, siempre dentro de ella."""
    if n <= 1:
        return [(0, 0)], 24
    if n == 2:
        return [(-19, 0), (19, 0)], 17
    if n == 3:
        return [(0, -20), (-20, 16), (20, 16)], 17
    if n == 4:
        return [(-19, -19), (19, -19), (-19, 19), (19, 19)], 17
    cols, filas = (-26, 0, 26), (-24, 24)
    return [(cols[k % 3], filas[min(k // 3, 1)]) for k in range(n)], 13


def _svg_matriz(riesgos: list[dict], numerico: bool) -> str:
    """Matriz de riesgos 1-25: impacto (eje x) × probabilidad (eje y), burbuja por riesgo
    coloreada por nivel. `numerico=True` añade el valor de nivel en cada celda (presentación);
    el gerencial usa solo colores, sin scores crudos."""
    x0, y0, lado = 80, 46, 84
    partes = ['<svg class="matriz" viewBox="0 0 540 520" role="img" '
              'aria-label="Matriz de riesgos 1 a 25">',
              "<title>Matriz de riesgos: impacto por probabilidad</title>"]
    for p in range(1, 6):                       # filas: probabilidad, 5 arriba
        for i in range(1, 6):                   # columnas: impacto
            x, y = x0 + (i - 1) * lado, y0 + (5 - p) * lado
            partes.append(f'<rect x="{x}" y="{y}" width="{lado}" height="{lado}" '
                          f'fill="{_tinte(i * p)}" stroke="#cfd8dc" stroke-width="1"/>')
            if numerico:
                partes.append(f'<text x="{x + lado - 7}" y="{y + 15}" text-anchor="end" '
                              f'font-size="10" fill="#b0bec5">{i * p}</text>')
    for p in range(1, 6):
        cy = y0 + (5 - p) * lado + lado // 2
        partes.append(f'<text x="{x0 - 14}" y="{cy + 5}" text-anchor="end" font-size="13" '
                      f'fill="#546e7a">{p}</text>')
    for i in range(1, 6):
        cx = x0 + (i - 1) * lado + lado // 2
        partes.append(f'<text x="{cx}" y="{y0 + 5 * lado + 22}" text-anchor="middle" '
                      f'font-size="13" fill="#546e7a">{i}</text>')
    partes.append(f'<text x="{x0}" y="{y0 - 16}" font-size="14" font-weight="bold" '
                  f'fill="#37474f">Probabilidad ↑</text>')
    partes.append(f'<text x="{x0 + 5 * lado // 2}" y="{y0 + 5 * lado + 46}" text-anchor="middle" '
                  f'font-size="14" font-weight="bold" fill="#37474f">Impacto →</text>')
    grupos: dict[tuple[int, int], list[dict]] = {}
    for r in riesgos:
        p, i = _rango1a5(r.get("probabilidad")), _rango1a5(r.get("impacto"))
        if p is None or i is None:
            continue                              # sin coordenadas válidas: no hay burbuja
        grupos.setdefault((i, p), []).append(r)
    for (i, p), grupo in grupos.items():
        offsets, radio = _burbujas_posiciones(len(grupo))
        cx0 = x0 + (i - 1) * lado + lado // 2
        cy0 = y0 + (5 - p) * lado + lado // 2
        for (dx, dy), r in zip(offsets, grupo, strict=False):
            cx, cy = cx0 + dx, cy0 + dy
            rid = _texto(r, "id")
            tam = (14 if radio >= 24 else 11) if len(rid) <= 4 else 9
            partes.append(f'<circle cx="{cx}" cy="{cy}" r="{radio}" '
                          f'fill="{_color_nivel(_nivel(r))}" stroke="#ffffff" stroke-width="3"/>')
            partes.append(f'<text x="{cx}" y="{cy + tam // 3}" text-anchor="middle" '
                          f'font-size="{tam}" font-weight="bold" fill="#ffffff">{_esc(rid)}</text>')
    partes.append("</svg>")
    return "".join(partes)


def _separar(xs: list[float], minimo: float, izq: float, der: float) -> list[float]:
    """Separa etiquetas con un mínimo de distancia y las mantiene dentro del lienzo."""
    xs = list(xs)
    for i in range(1, len(xs)):
        if xs[i] - xs[i - 1] < minimo:
            xs[i] = xs[i - 1] + minimo
    if xs and xs[-1] > der and xs[-1] > izq:
        escala = (der - izq) / (xs[-1] - izq)
        xs = [izq + (x - izq) * escala for x in xs]
    return xs


def _posiciones(casos: list[dict], izq: float, der: float) -> list[float]:
    n = len(casos)
    fechas = [_como_fecha(c) for c in casos]
    if n == 1:
        return [(izq + der) / 2]
    if all(f is not None for f in fechas) and len(set(fechas)) > 1:
        d0, d1 = min(fechas), max(fechas)
        span = (d1 - d0).days or 1
        xs = [izq + (f - d0).days / span * (der - izq) for f in fechas]
    else:                                        # fechas ausentes o no ISO: columnas parejas
        paso = (der - izq) / n
        xs = [izq + (i + 0.5) * paso for i in range(n)]
    return _separar(xs, 68, izq, der)


def _svg_timeline(casos: list[dict]) -> str:
    """Línea de tiempo de casos por fecha, cada punto con el color de su gravedad."""
    izq, der, y = 64, 694, 150
    partes = ['<svg class="linea-tiempo" viewBox="0 0 760 300" role="img" '
              'aria-label="Casos por fecha">',
              "<title>Casos por fecha con color de gravedad</title>",
              f'<line x1="{izq}" y1="{y}" x2="{der}" y2="{y}" stroke="#90a4ae" stroke-width="3"/>',
              f'<polygon points="{der},{y - 6} {der + 12},{y} {der},{y + 6}" fill="#90a4ae"/>']
    if not casos:
        partes.append(f'<text x="380" y="{y + 40}" text-anchor="middle" font-size="15" '
                      f'fill="#90a4ae">{SIN_DATOS}</text>')
    else:
        for idx, (c, x) in enumerate(zip(casos, _posiciones(casos, izq, der), strict=False)):
            xi = int(round(x))
            fecha = _texto(c, "fecha", "inicio")
            titulo = _cortar(_texto(c, "titulo"), 22)
            color = _color_gravedad(_texto(c, "gravedad"))
            fila_f = 86 if idx % 2 == 0 else 64
            fila_t = 178 if idx % 2 == 0 else 200
            partes.append(f'<line x1="{xi}" y1="{fila_f + 8}" x2="{xi}" y2="{y - 14}" '
                          f'stroke="#cfd8dc" stroke-width="2"/>')
            partes.append(f'<text x="{xi}" y="{fila_f}" text-anchor="middle" font-size="11" '
                          f'fill="#37474f">{_esc(fecha)}</text>')
            partes.append(f'<circle cx="{xi}" cy="{y}" r="10" fill="{color}" '
                          f'stroke="#ffffff" stroke-width="2"/>')
            partes.append(f'<text x="{xi}" y="{fila_t}" text-anchor="middle" font-size="10" '
                          f'fill="#546e7a">{_esc(titulo)}</text>')
    partes.append("</svg>")
    return "".join(partes)


def _svg_semaforo(kpis: dict) -> str:
    """Semáforo de KPIs: alertas por gravedad, cuentas a revisar y conexiones inseguras.
    Luz: verde en 0, rojo/ámbar por encima de 0, gris cuando falta el dato."""
    alertas = kpis.get("alertas") if isinstance(kpis.get("alertas"), dict) else {}
    partes = ['<svg class="semaforo" viewBox="0 0 760 300" role="img" '
              'aria-label="Semáforo de indicadores">',
              "<title>Semáforo de indicadores del período</title>"]
    panel1 = [("Crítica", "#c62828", ("critica", "crítica", "Crítica")),
              ("Alta", "#ef6c00", ("alta", "Alta")),
              ("Media", "#f9a825", ("media", "Media")),
              ("Baja", "#2e7d32", ("baja", "Baja"))]
    partes.append('<text x="140" y="30" text-anchor="middle" font-size="14" font-weight="bold" '
                  'fill="#37474f">Alertas por gravedad</text>')
    for k, (etiqueta, color, claves) in enumerate(panel1):
        cy = 70 + k * 40
        n = _conteo(alertas, *claves)
        valor = str(n) if n is not None else SIN_DATOS
        partes.append(f'<circle cx="52" cy="{cy - 5}" r="8" fill="{color}"/>')
        partes.append(f'<text x="70" y="{cy}" font-size="13" fill="#37474f">{etiqueta}</text>')
        partes.append(f'<text x="234" y="{cy + 2}" text-anchor="end" font-size="16" '
                      f'font-weight="bold" fill="#263238">{valor}</text>')
    for cx, titulo, clave in ((390, "Cuentas a revisar", "cuentas_a_revisar"),
                              (630, "Conexiones inseguras", "conexiones_inseguras")):
        partes.append(f'<text x="{cx}" y="30" text-anchor="middle" font-size="14" '
                      f'font-weight="bold" fill="#37474f">{titulo}</text>')
        partes.append(f'<rect x="{cx - 34}" y="46" width="68" height="150" rx="10" '
                      f'fill="#263238"/>')
        n = _entero(kpis.get(clave))
        if n is None:
            luces, texto = ("#455a64", "#455a64", "#455a64"), SIN_DATOS
        elif n == 0:
            luces, texto = ("#455a64", "#455a64", "#2e7d32"), str(n)
        elif clave == "cuentas_a_revisar":
            luces, texto = ("#c62828", "#455a64", "#455a64"), str(n)
        else:
            luces, texto = ("#455a64", "#f9a825", "#455a64"), str(n)
        for j, luz in enumerate(luces):
            partes.append(f'<circle cx="{cx}" cy="{76 + j * 45}" r="16" fill="{luz}"/>')
        partes.append(f'<text x="{cx}" y="234" text-anchor="middle" font-size="18" '
                      f'font-weight="bold" fill="#263238">{texto}</text>')
    partes.append('<line x1="270" y1="16" x2="270" y2="274" stroke="#eceff1" stroke-width="2"/>')
    partes.append('<line x1="510" y1="16" x2="510" y2="274" stroke="#eceff1" stroke-width="2"/>')
    partes.append("</svg>")
    return "".join(partes)


def _svg_flujo() -> str:
    """Flujo de detección en seis pasos: ingesta → privacidad → detección → priorización
    → decisión → difusión."""
    pasos = [("Ingesta", "fuentes y alertas"), ("Privacidad", "seudonimización"),
             ("Detección", "reglas y modelo"), ("Priorización", "por gravedad"),
             ("Decisión", "revisión humana"), ("Difusión", "informes y avisos")]
    ancho, alto, y0, x0, salto = 110, 64, 54, 15, 124
    partes = ['<svg class="flujo" viewBox="0 0 760 140" role="img" '
              'aria-label="Flujo de detección en seis pasos">',
              "<title>Flujo de detección: seis pasos</title>"]
    for k, (nombre, detalle) in enumerate(pasos):
        x = x0 + k * salto
        if k:
            partes.append(f'<line x1="{x - 12}" y1="86" x2="{x - 6}" y2="86" '
                          f'stroke="#546e7a" stroke-width="2"/>')
            partes.append(f'<polygon points="{x - 6},82 {x},86 {x - 6},90" fill="#546e7a"/>')
        partes.append(f'<rect x="{x}" y="{y0}" width="{ancho}" height="{alto}" rx="8" '
                      f'fill="#e3f2fd" stroke="#1565c0" stroke-width="2"/>')
        partes.append(f'<text x="{x + 8}" y="{y0 - 6}" font-size="10" fill="#90a4ae">'
                      f"{k + 1}</text>")
        partes.append(f'<text x="{x + ancho // 2}" y="{y0 + 28}" text-anchor="middle" '
                      f'font-size="13" font-weight="bold" fill="#0d47a1">{nombre}</text>')
        partes.append(f'<text x="{x + ancho // 2}" y="{y0 + 48}" text-anchor="middle" '
                      f'font-size="9" fill="#546e7a">{detalle}</text>')
    partes.append("</svg>")
    return "".join(partes)


# ---------------------------------------------------------------------------
# Bloques HTML
# ---------------------------------------------------------------------------
class _Celda:
    """Celda cuyo contenido ya es HTML construido (badges): no se vuelve a escapar."""
    __slots__ = ("html",)

    def __init__(self, html_generado: str):
        self.html = html_generado


def _celda(c):
    return c.html if isinstance(c, _Celda) else _esc(c)


def _tabla(cabeceras: list[str], filas: list[list]) -> str:
    th = "".join(f"<th>{_esc(c)}</th>" for c in cabeceras)
    if filas:
        body = "".join("<tr>" + "".join(f"<td>{_celda(c)}</td>" for c in fila) + "</tr>"
                       for fila in filas)
    else:
        body = f'<tr><td class="vacio" colspan="{len(cabeceras)}">{SIN_DATOS}</td></tr>'
    return f'<table class="tabla"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def _seccion(titulo: str, contenido: str, sid: str | None = None) -> str:
    attr = f' id="{sid}"' if sid else ""
    return f'<section{attr}><h2>{_esc(titulo)}</h2>{contenido}</section>'


def _pagina(titulo: str, cuerpo: str, css: str) -> str:
    return ("<!DOCTYPE html>\n"
            '<html lang="es">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{_esc(titulo)}</title>\n"
            f"<style>\n{css}\n</style>\n"
            "</head>\n<body>\n"
            f"{cuerpo}\n"
            "</body>\n</html>\n")


def _leyenda(riesgos: list[dict]) -> str:
    if not riesgos:
        return f'<p class="vacio">{SIN_DATOS}</p>'
    items = []
    for r in riesgos:
        rid, nombre = _texto(r, "id"), _texto(r, "nombre")
        color = _color_nivel(_nivel(r))
        items.append(f'<li><span class="punto" style="background:{color}"></span>'
                     f"<strong>{_esc(rid)}</strong> — {_esc(nombre)}</li>")
    return f'<ul class="leyenda">{"".join(items)}</ul>'


def _lista_casos(casos: list[dict]) -> str:
    if not casos:
        return f'<p class="vacio">{SIN_DATOS}</p>'
    items = []
    for c in casos:
        g = _texto(c, "gravedad")
        color = _color_gravedad(g)
        items.append(f'<li><span class="badge" style="background:{color}">{_esc(g)}</span> '
                     f"<strong>{_esc(_texto(c, 'fecha', 'inicio'))}</strong> — "
                     f"{_esc(_texto(c, 'titulo'))}. {_esc(_texto(c, 'frase', 'explicacion', 'resumen'))}</li>")
    return f'<ul class="lista-casos">{"".join(items)}</ul>'


def _recomendaciones(datos: dict, riesgos: list[dict]) -> list[str]:
    """Prioridades: la lista dada, o los riesgos ordenados por nivel descendente."""
    extra = datos.get("recomendaciones")
    if isinstance(extra, list) and extra:
        salida = []
        for x in extra:
            if isinstance(x, str) and x.strip():
                salida.append(x)
            elif isinstance(x, dict):
                t = _texto_opt(x, "texto", "recomendacion", "descripcion")
                if t:
                    salida.append(t)
        if salida:
            return salida

    def orden(r):
        n = _nivel(r)
        return -(n if n is not None else 0)

    salida = []
    for r in sorted(riesgos, key=orden):
        rid, nombre = _texto(r, "id"), _texto(r, "nombre")
        rec = _texto(r, "recomendacion", "tratamiento", "asignacion")
        titulo = nombre if rid == SIN_DATOS else f"{rid} — {nombre}"
        salida.append(f"{titulo}: {rec}")
    return salida


def _recomendaciones_html(datos: dict, riesgos: list[dict]) -> str:
    items = _recomendaciones(datos, riesgos)
    if not items:
        return f'<p class="vacio">{SIN_DATOS}</p>'
    return '<ol class="recomendaciones">' + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ol>"


def _tabla_evidencia(casos: list[dict]) -> str:
    filas = []
    for c in casos:
        g = _texto(c, "gravedad")
        badge = f'<span class="badge" style="background:{_color_gravedad(g)}">{_esc(g)}</span>'
        filas.append([_texto(c, "fecha", "inicio"), _texto(c, "titulo"),
                      _texto(c, "frase", "explicacion", "resumen"), _Celda(badge)])
    return _tabla(["Fecha", "Caso", "Explicación en una frase", "Gravedad"], filas)


def _asignacion(r: dict) -> _Celda:
    partes = [_esc(_texto(r, "asignacion", "tratamiento", "recomendacion"))]
    vinc = r.get("casos")
    if isinstance(vinc, list) and vinc:
        partes.append("<br><small>Casos: "
                      + ", ".join(_esc(str(x)) for x in vinc) + "</small>")
    return _Celda("".join(partes))


def _tabla_riesgos(riesgos: list[dict]) -> str:
    filas = [[_texto(r, "id"), _texto(r, "nombre"), _texto(r, "probabilidad"),
              _texto(r, "impacto"), _texto(r, "nivel"), _asignacion(r)] for r in riesgos]
    return _tabla(["Riesgo", "Nombre", "Probabilidad", "Impacto", "Nivel",
                   "Asignación actual"], filas)


def _tabla_tendencias(tendencias: list[dict]) -> str:
    filas = []
    for t in tendencias:
        marca, clase = _marca(t)
        badge = f'<span class="marca {clase}">{_esc(marca)}</span>'
        filas.append([_texto(t, "titulo", "nombre"), _texto(t, "fuente"),
                      _texto(t, "estado"), _Celda(badge)])
    return _tabla(["Tendencia", "Fuente", "Estado", "Marca"], filas)


def _control(c: dict) -> str:
    base = _texto(c, "control", "nombre")
    cid = _texto_opt(c, "id")
    return f"{cid} — {base}" if cid and cid != base else base


def _tabla_controles(controles: list[dict]) -> str:
    filas = []
    for c in controles:
        est = _texto(c, "estado")
        badge = f'<span class="badge" style="background:{_color_estado(est)}">{_esc(est)}</span>'
        filas.append([_control(c), _Celda(badge)])
    return _tabla(["Control", "Estado"], filas)


def _anexo(datos: dict) -> str:
    tecnicas = _tabla(["Id", "Técnica", "Detalle"],
                      [[_texto(t, "id"), _texto(t, "nombre"), _texto(t, "detalle")]
                       for t in _lista(datos, "tecnicas")])
    indicadores = _tabla(["Indicador", "Valor", "Nota"],
                         [[_texto(i, "nombre"), _texto(i, "valor"), _texto(i, "nota")]
                          for i in _lista(datos, "indicadores")])
    return ('<p class="flujo-nota">Detalles técnicos para las preguntas durante la '
            'presentación.</p><h3>Técnicas MITRE ATT&amp;CK</h3>' + tecnicas +
            "<h3>Indicadores</h3>" + indicadores)


# ---------------------------------------------------------------------------
# CSS (inline; @media print para «Guardar como PDF»)
# ---------------------------------------------------------------------------
_CSS_BASE = """\
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:#eef1f5;color:#263238;font-family:Georgia,'Times New Roman',serif;
font-size:16px;line-height:1.55;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.hoja{max-width:960px;margin:0 auto;background:#ffffff;padding:36px 44px;
box-shadow:0 2px 12px rgba(0,0,0,.10)}
h1{font-size:30px;margin:0 0 6px;color:#0d47a1}
h2{font-size:22px;margin:36px 0 12px;color:#0d47a1;border-bottom:3px solid #e3f2fd;
padding-bottom:6px}
h3{font-size:17px;margin:22px 0 8px;color:#37474f}
p{margin:10px 0}
.portada{background:#0d47a1;color:#ffffff;padding:30px 34px;margin:-36px -44px 28px}
.portada h1{color:#ffffff}
.periodo{font-size:19px;color:#e3f2fd;margin:4px 0 0}
.tabla{width:100%;border-collapse:collapse;margin:12px 0 20px;font-size:14px;
font-family:Arial,Helvetica,sans-serif}
.tabla th{background:#0d47a1;color:#ffffff;text-align:left;padding:8px 10px;font-size:13px}
.tabla td{border-bottom:1px solid #e0e4e8;padding:8px 10px;vertical-align:top}
.tabla tbody tr:nth-child(even) td{background:#f7f9fc}
.badge{display:inline-block;padding:2px 9px;border-radius:11px;color:#ffffff;font-size:12px;
font-weight:bold;font-family:Arial,Helvetica,sans-serif}
.marca{display:inline-block;padding:2px 9px;border-radius:11px;font-size:12px;font-weight:bold;
font-family:Arial,Helvetica,sans-serif}
.marca.real{background:#2e7d32;color:#ffffff}
.marca.simulado{background:#f9a825;color:#263238}
.marca.desconocida{background:#eceff1;color:#546e7a}
.marca.otro{background:#546e7a;color:#ffffff}
.vacio{color:#78909c;font-style:italic}
.pie{margin-top:38px;border-top:1px solid #e0e4e8;padding-top:12px;font-size:12px;
color:#78909c}
svg{max-width:100%;height:auto;display:block;margin:14px auto 6px}
@media print{
  body{background:#ffffff}
  .hoja{box-shadow:none;margin:0;padding:0;max-width:none}
  .portada{margin:0 0 26px;page-break-after:always}
  section{page-break-inside:avoid}
  h2{page-break-after:avoid}
  .tabla tr{page-break-inside:avoid}
  @page{margin:14mm}
}"""

_CSS_GERENCIAL = """\
body{font-size:18px}
.resumen{font-size:20px;line-height:1.6}
.lista-casos{list-style:none;padding:0;margin:10px 0 0}
.lista-casos li{margin:12px 0;padding:10px 14px;background:#f7f9fc;
border-left:5px solid #e3f2fd;border-radius:0 8px 8px 0}
.punto{display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:8px;
vertical-align:-2px}
.leyenda{list-style:none;padding:0;margin:12px 0 0;display:flex;flex-wrap:wrap;gap:12px}
.leyenda li{background:#f7f9fc;border:1px solid #e0e4e8;border-radius:8px;padding:8px 13px;
font-size:15px}
.recomendaciones{margin:10px 0 0;padding-left:28px;font-size:17px}
.recomendaciones li{margin:13px 0;padding-left:4px}
.kpi-nota{font-size:14px;color:#546e7a}"""

_CSS_PRESENTACION = """\
body{font-size:15px}
.resumen-ejecutivo{font-size:17px;background:#f7f9fc;border-left:5px solid #0d47a1;
padding:14px 18px;border-radius:0 8px 8px 0}
.flujo-nota{font-size:13px;color:#546e7a}
#anexo{background:#f7f7f7;border:1px solid #dfe4ea;border-radius:8px;padding:4px 24px 20px;
margin-top:26px;page-break-before:always}"""


# ---------------------------------------------------------------------------
# Informes
# ---------------------------------------------------------------------------
def informe_gerencial(datos: dict) -> str:
    """Informe HTML autocontenido para cargos altos no técnicos.

    Portada con periodo, «qué pasó este mes» en frase simple, matriz de riesgos 1-25 con
    burbujas por impacto × probabilidad (color por nivel), línea de tiempo de casos por
    fecha con color de gravedad, semáforo de KPIs y «Qué recomendamos hacer» priorizado.
    Sin IPs, cuentas, nombres, técnicas MITRE ni scores crudos: solo seudónimos, frases y
    colores. Contrato completo de `datos` en el docstring del módulo.
    """
    datos = datos if isinstance(datos, dict) else {}
    casos = _casos_ordenados(_lista(datos, "casos"))
    riesgos = _lista(datos, "riesgos")
    kpis = datos.get("kpis") if isinstance(datos.get("kpis"), dict) else {}
    periodo = _periodo(datos)
    partes = [
        '<div class="hoja">',
        '<header class="portada"><h1>Informe gerencial de amenazas</h1>'
        f'<p class="periodo">Periodo: {_esc(periodo)}</p></header>',
        _seccion("Qué pasó este mes",
                 f'<p class="resumen">{_esc(_resumen(datos, casos))}</p>'),
        _seccion("Cómo se ven los riesgos",
                 _svg_matriz(riesgos, numerico=False) + _leyenda(riesgos)),
        _seccion("Los casos del período",
                 _svg_timeline(casos) + _lista_casos(casos)),
        _seccion("Semáforo del período",
                 _svg_semaforo(kpis) +
                 '<p class="kpi-nota">Verde: en orden · Ámbar: conviene revisar · '
                 'Rojo: requiere atención · Gris: sin datos.</p>'),
        _seccion("Qué recomendamos hacer", _recomendaciones_html(datos, riesgos)),
        '<footer class="pie">Informe para cargos directivos: frases y colores, sin detalle '
        'técnico. El detalle completo está en el informe de presentación.</footer>',
        "</div>",
    ]
    return _pagina(f"Informe gerencial — {periodo}", "\n".join(partes),
                   _CSS_BASE + _CSS_GERENCIAL)


def informe_presentacion(datos: dict) -> str:
    """Informe HTML autocontenido para el experto que presenta ante superiores.

    Resumen ejecutivo, evidencia condensada (cada caso con su explicación en una frase y
    gravedad), matriz de riesgos con asignación actual, tendencias con su marca
    real/simulado cuando viene en datos, controles ISO 27002 con estado de brecha, diagrama
    SVG del flujo de detección en 6 pasos y anexo técnico separado al final (MITRE e
    indicadores). Contrato completo de `datos` en el docstring del módulo.
    """
    datos = datos if isinstance(datos, dict) else {}
    casos = _casos_ordenados(_lista(datos, "casos"))
    riesgos = _lista(datos, "riesgos")
    periodo = _periodo(datos)
    partes = [
        '<div class="hoja">',
        '<header class="portada"><h1>Informe de presentación</h1>'
        f'<p class="periodo">Periodo: {_esc(periodo)}</p></header>',
        _seccion("Resumen ejecutivo",
                 f'<p class="resumen-ejecutivo">{_esc(_resumen(datos, casos))}</p>'),
        _seccion("Evidencia condensada", _tabla_evidencia(casos)),
        _seccion("Matriz de riesgos y asignación actual",
                 _svg_matriz(riesgos, numerico=True) + _tabla_riesgos(riesgos)),
        _seccion("Tendencias", _tabla_tendencias(_lista(datos, "tendencias"))),
        _seccion("Controles ISO 27002", _tabla_controles(_lista(datos, "controles"))),
        _seccion("Flujo de detección",
                 _svg_flujo() +
                 '<p class="flujo-nota">Seis pasos: de la ingesta de los datos a la '
                 'difusión del informe, con privacidad y revisión humana en el medio.</p>'),
        _seccion("Anexo técnico", _anexo(datos), sid="anexo"),
        '<footer class="pie">Informe para el experto: evidencia condensada arriba y '
        'detalle técnico solo en el anexo final.</footer>',
        "</div>",
    ]
    return _pagina(f"Informe de presentación — {periodo}", "\n".join(partes),
                   _CSS_BASE + _CSS_PRESENTACION)


# ---------------------------------------------------------------------------
# Alimentación desde el análisis activo (wiring S14/T16)
# ---------------------------------------------------------------------------
def datos_desde_estado() -> dict:
    """Contrato `datos` armado desde el estado real del análisis activo.

    Fuentes (cada una tolerante por separado): `ejecutivo.armar()` (periodo, resumen,
    historia de casos con frases simples), `resumen_motor.json` (periodo y KPIs),
    `alertas.json` (conteo por gravedad), `riesgos.calcular()` (trae `tratamiento`, alias
    aceptado por el contrato) y `fijos/controles.json`; además las tendencias con su sello
    real/simulado (misma fusión de solo-lectura que GET /api/threatpulse) y el anexo
    técnico (MITRE/indicadores) desde las salidas de la consola.

    Tolerante: cualquier archivo ausente o ilegible cae a defaults («sin datos») sin
    romper el informe. Sin análisis activo se propaga el 409 de `datos.casos()`, igual
    que el resto de la consola. Imports dentro de la función: `reportes.py` sigue siendo
    stdlib para generar los informes.
    """
    from . import config, ejecutivo, riesgos, threatpulse
    from . import datos as _datos

    vigentes = [c for c in _datos.casos() if c.get("estado") != "descartado"]   # 409 sin análisis

    resumen_motor = _datos.motor("resumen_motor.json", {}) or {}
    if not isinstance(resumen_motor, dict):
        resumen_motor = {}
    try:
        ejec = ejecutivo.armar()
    except Exception:                       # fuente parcial: se sigue con el resto
        ejec = {}
    if not isinstance(ejec, dict):
        ejec = {}

    contrato: dict = {}

    periodo = ejec.get("periodo") or resumen_motor.get("periodo")
    if periodo:
        contrato["periodo"] = periodo

    if ejec:
        contrato["resumen"] = (
            f"Se revisaron {ejec.get('registros', 0)} registros y se detectaron "
            f"{ejec.get('incidentes', 0)} incidentes, de los cuales {ejec.get('criticos', 0)} "
            f"son críticos ({ejec.get('confirmados', 0)} confirmados y "
            f"{ejec.get('pendientes', 0)} pendientes de decisión).")

    # Semáforo de KPIs: alertas por gravedad + contadores del resumen del motor.
    conteo = {"critica": 0, "alta": 0, "media": 0, "baja": 0}
    alertas = _datos.motor("alertas.json", []) or []
    if isinstance(alertas, list):
        for a in alertas:
            if isinstance(a, dict):
                g = str(a.get("gravedad", "")).strip().lower().replace("í", "i")
                if g in conteo:
                    conteo[g] += 1
    kpis: dict = {"alertas": conteo}
    for origen, destino in (("cuentas_sospechosas", "cuentas_a_revisar"),
                            ("conexiones_inseguras", "conexiones_inseguras")):
        if origen in resumen_motor:
            kpis[destino] = resumen_motor[origen]
    contrato["kpis"] = kpis

    # Casos: la historia del ejecutivo (frases simples); si falla, los vigentes sin frase.
    if isinstance(ejec.get("historia"), list) and ejec["historia"]:
        casos = [{"titulo": h.get("titulo"), "fecha": h.get("inicio"),
                  "gravedad": h.get("gravedad"), "frase": h.get("frase")}
                 for h in ejec["historia"] if isinstance(h, dict)]
    else:
        casos = [{"titulo": c.get("titulo"), "fecha": c.get("inicio"),
                  "gravedad": c.get("gravedad")} for c in vigentes if isinstance(c, dict)]
    if casos:
        contrato["casos"] = casos

    try:
        matriz = riesgos.calcular()
    except Exception:
        matriz = []
    if isinstance(matriz, list) and matriz:
        contrato["riesgos"] = [r for r in matriz if isinstance(r, dict)]   # «tratamiento» ya es alias

    try:
        controles = json.loads((config.FIJOS / "controles.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        controles = []
    if isinstance(controles, list) and controles:
        contrato["controles"] = [c for c in controles if isinstance(c, dict)]

    # Tendencias con su marca real/simulado: solo lee la caché OSINT, jamás hace red.
    try:
        from . import osint
        fijas = json.loads((config.FIJOS / "tendencias.json").read_text(encoding="utf-8"))
        base = fijas.get("tendencias", []) if isinstance(fijas, dict) else []
        reales, _meta = osint.tendencias_reales()
        lista = ([{**t, "sello": "simulado"} for t in base] + reales) if reales else base
        tendencias = threatpulse.evaluar(lista)
    except Exception:
        tendencias = []
    if isinstance(tendencias, list) and tendencias:
        contrato["tendencias"] = tendencias

    # Anexo técnico de la presentación: técnicas MITRE de los casos e indicadores de la consola.
    tecnicas: list[dict] = []
    for c in vigentes:
        for t in (c.get("tecnicas") or []):
            if isinstance(t, dict) and t.get("id"):
                tecnicas.append({"id": t.get("id"), "nombre": t.get("nombre", ""),
                                 "detalle": c.get("titulo", "")})
    if tecnicas:
        contrato["tecnicas"] = tecnicas
    try:
        intel = _datos.consola("inteligencia")
        iocs = [i for i in intel.get("iocs", []) if isinstance(i, dict)]
        indicadores = [{"nombre": i.get("tipo"), "valor": i.get("valor"),
                        "nota": i.get("descripcion", "")} for i in iocs]
    except Exception:
        indicadores = []
    if indicadores:
        contrato["indicadores"] = indicadores

    return contrato
