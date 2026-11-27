"""Reporte de inteligencia de amenazas en PDF con los 8 entregables del reto.

1. Fuentes y metodología          5. Inteligencia operativa
2. Evaluación de adversarios       6. Inteligencia técnica
3. Inteligencia estratégica        7. Evaluación de escenarios (IPE)
4. Inteligencia táctica            8. Conclusiones

Todo sale del análisis activo (casos, riesgos, inteligencia, agendamiento, denuncias, OSINT):
otro dataset produce otro reporte. Solo seudónimos; ningún nombre real.
"""
from __future__ import annotations

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config

VERDE = colors.HexColor("#00713D")
VERDE_OSC = colors.HexColor("#003D24")
VERDE_CLARO = colors.HexColor("#E2F1E7")
GRIS = colors.HexColor("#46574E")
LINEA = colors.HexColor("#D1DBD5")
GRAVEDAD = {"critica": colors.HexColor("#C1272D"), "alta": colors.HexColor("#E0730F"),
            "media": colors.HexColor("#E6B200"), "baja": colors.HexColor("#2D7A4C")}
NOMBRE_GRAV = {"critica": "Crítica", "alta": "Alta", "media": "Media", "baja": "Baja"}

# Perfil de adversario por tipo de caso: actor, motivación, objetivo y capacidad estimada.
PERFILES = [
    ("fuga", {"actor": "Interno con acceso o cuenta legítima comprometida",
              "motivacion": "Económica: los datos clínicos se venden o se usan para extorsión",
              "objetivo": "Sacar información del sistema médico por un canal remoto cifrado",
              "capacidad": "Media-alta: conoce la red y usa un canal permitido (SSH)"}),
    ("fantasma", {"actor": "Interno o tercero con una credencial genérica sin dueño",
                  "motivacion": "Acceso no autorizado a historias clínicas sin dejar rastro nominal",
                  "objetivo": "Consultar o descargar registros fuera del horario de control",
                  "capacidad": "Media: aprovecha cuentas genéricas y desfase de relojes"}),
    ("fuerza", {"actor": "Externo oportunista o bot de adivinación de contraseñas",
                "motivacion": "Acceso inicial para fraude, ransomware o reventa del acceso",
                "objetivo": "Servicios con autenticación débil o protocolos sin cifrado (Telnet)",
                "capacidad": "Baja-media: herramientas automatizadas de uso común"}),
    ("escaneo", {"actor": "Externo o interno en fase de reconocimiento",
                 "motivacion": "Mapear servicios expuestos para preparar un ataque",
                 "objetivo": "Puertos y servicios del servidor del sistema médico",
                 "capacidad": "Media: barridos sistemáticos de puertos"}),
]
PERFIL_GENERICO = {"actor": "Por determinar", "motivacion": "Por determinar",
                   "objetivo": "Servidor del sistema médico", "capacidad": "Por determinar"}


def _perfil(titulo: str) -> dict:
    t = titulo.lower()
    return next((p for clave, p in PERFILES if clave in t), PERFIL_GENERICO)


# ---------- recolección ----------
def recolectar() -> dict:
    """Junta lo que existe del análisis activo. Cada fuente falla por separado sin romper el reporte."""
    from . import datos, denuncias, ejecutivo, riesgos
    casos = datos.casos()                                   # 409 si no hay análisis activo
    detalles = []
    for c in casos:
        try:
            detalles.append(datos.caso(c["id"]))
        except Exception:
            detalles.append(c)

    def intento(fn, defecto):
        try:
            return fn()
        except Exception:
            return defecto

    ejec = intento(ejecutivo.armar, {})
    intel = intento(lambda: datos.consola("inteligencia"), {"sigma": [], "iocs": []})
    agenda = intento(datos.agendamiento, None)
    dens = intento(denuncias.todas, [])
    tendencias = intento(_tendencias, [])
    return {"ejecutivo": ejec, "casos": detalles, "riesgos": intento(riesgos.calcular, []), "inteligencia": intel,
            "agenda": agenda, "denuncias": dens, "tendencias": tendencias,
            "motor": intento(lambda: datos.motor("resumen_motor.json", {}), {})}


def _tendencias() -> list[dict]:
    import json

    from . import osint, threatpulse
    fijo = json.loads((config.FIJOS / "tendencias.json").read_text(encoding="utf-8"))["tendencias"]
    try:
        reales, _ = osint.tendencias_reales()
    except Exception:
        reales = []
    return threatpulse.evaluar([{**t, "sello": "simulado"} for t in fijo] + reales)


# ---------- estilos ----------
def _estilos():
    base = getSampleStyleSheet()
    e = {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontName="Helvetica-Bold", fontSize=24,
                                 textColor=VERDE_OSC, leading=29, alignment=TA_CENTER),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=12, textColor=GRIS, alignment=TA_CENTER,
                              leading=16),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=16,
                             textColor=VERDE_OSC, spaceBefore=6, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12,
                             textColor=VERDE, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", parent=base["Normal"], fontSize=10, leading=14, spaceAfter=5),
        "chico": ParagraphStyle("chico", parent=base["Normal"], fontSize=8.5, leading=11, textColor=GRIS),
        "celda": ParagraphStyle("celda", parent=base["Normal"], fontSize=8.5, leading=11),
        "celdab": ParagraphStyle("celdab", parent=base["Normal"], fontSize=8.5, leading=11,
                                 fontName="Helvetica-Bold"),
        "dest": ParagraphStyle("dest", parent=base["Normal"], fontSize=10.5, leading=15, textColor=VERDE_OSC,
                               backColor=VERDE_CLARO, borderPadding=7, spaceBefore=4, spaceAfter=10),
    }
    return e


def _fecha(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(iso or "")


def _t(texto) -> str:
    return escape(str(texto if texto is not None else ""))


def _tabla(filas: list[list], anchos: list[float], e: dict, encabezado=True) -> Table:
    datos = [[c if not isinstance(c, str) else Paragraph(_t(c), e["celdab"] if (encabezado and i == 0) else e["celda"])
              for c in fila] for i, fila in enumerate(filas)]
    t = Table(datos, colWidths=[a * cm for a in anchos], repeatRows=1 if encabezado else 0)
    estilo = [("GRID", (0, 0), (-1, -1), 0.4, LINEA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if encabezado:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), VERDE_CLARO)]
    t.setStyle(TableStyle(estilo))
    return t


def _barras_gravedad(casos: list[dict]) -> Drawing:
    orden = ["critica", "alta", "media", "baja"]
    n = [sum(1 for c in casos if c.get("gravedad") == g and c.get("estado") != "descartado") for g in orden]
    d = Drawing(8 * cm, 4.6 * cm)
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 30, 22, 7 * cm - 20, 3.4 * cm
    ch.data = [n]
    ch.categoryAxis.categoryNames = [NOMBRE_GRAV[g] for g in orden]
    ch.valueAxis.valueMin = 0
    ch.valueAxis.valueStep = 1
    ch.valueAxis.valueMax = max(n + [1]) + 1
    ch.bars.strokeColor = None
    for i, g in enumerate(orden):
        ch.bars[(0, i)].fillColor = GRAVEDAD[g]
    ch.categoryAxis.labels.fontSize = 8
    ch.valueAxis.labels.fontSize = 7
    d.add(ch)
    d.add(String(0, 4.25 * cm, "Incidentes vigentes por gravedad", fontSize=8.5, fillColor=GRIS))
    return d


def _barras_riesgos(riesgos: list[dict]) -> Drawing:
    top = sorted(riesgos, key=lambda r: -r["nivel"])[:6][::-1]
    d = Drawing(9.5 * cm, 4.6 * cm)
    ch = HorizontalBarChart()
    ch.x, ch.y, ch.width, ch.height = 30, 10, 9.5 * cm - 40, 3.6 * cm
    ch.data = [[r["nivel"] for r in top]]
    ch.categoryAxis.categoryNames = [r["id"] for r in top]
    ch.valueAxis.valueMin, ch.valueAxis.valueMax, ch.valueAxis.valueStep = 0, 25, 5
    ch.bars.strokeColor = None
    for i, r in enumerate(top):
        ch.bars[(0, i)].fillColor = _color_nivel(r["nivel"])
    ch.categoryAxis.labels.fontSize = 8
    ch.valueAxis.labels.fontSize = 7
    d.add(ch)
    d.add(String(0, 4.25 * cm, "Riesgos con mayor nivel (probabilidad x impacto)", fontSize=8.5, fillColor=GRIS))
    return d


def _color_nivel(n: int):
    return GRAVEDAD["critica"] if n >= 20 else GRAVEDAD["alta"] if n >= 12 else GRAVEDAD["media"] if n >= 6 else GRAVEDAD["baja"]


def _matriz(riesgos: list[dict]) -> Drawing:
    lado = 1.25 * cm
    d = Drawing(lado * 5 + 40, lado * 5 + 30)
    for imp in range(1, 6):
        for pr in range(1, 6):
            x, y = 30 + (pr - 1) * lado, 20 + (imp - 1) * lado
            col = _color_nivel(pr * imp)
            d.add(Rect(x, y, lado - 2, lado - 2, fillColor=colors.Color(col.red, col.green, col.blue, 0.22),
                       strokeColor=None))
            ids = [r["id"] for r in riesgos if r["probabilidad"] == pr and r["impacto"] == imp]
            for k, rid in enumerate(ids[:3]):
                d.add(String(x + 3, y + lado - 11 - k * 10, rid, fontSize=7, fontName="Helvetica-Bold",
                             fillColor=colors.black))
            if len(ids) > 3:
                d.add(String(x + 3, y + 3, f"+{len(ids) - 3}", fontSize=6.5, fillColor=GRIS))
    for i in range(5):
        d.add(String(30 + i * lado + lado / 2 - 3, 8, str(i + 1), fontSize=7, fillColor=GRIS))
        d.add(String(18, 20 + i * lado + lado / 2 - 3, str(i + 1), fontSize=7, fillColor=GRIS))
    d.add(String(30, 0, "Probabilidad", fontSize=7.5, fillColor=GRIS))
    d.add(String(0, 20 + 5 * lado + 2, "Impacto", fontSize=7.5, fillColor=GRIS))
    return d


# ---------- documento ----------
def generar() -> bytes:
    d = recolectar()
    e = _estilos()
    ej, casos, riesgos_ = d["ejecutivo"], d["casos"], d["riesgos"]
    vigentes = [c for c in casos if c.get("estado") != "descartado"]
    periodo = ej.get("periodo") or d["motor"].get("periodo") or {}
    periodo_txt = f"{periodo.get('desde', '')} a {periodo.get('hasta', '')}" if isinstance(periodo, dict) else str(periodo)
    registros = ej.get("registros") or d["motor"].get("registros", {}).get("total", 0)
    agenda = d["agenda"]
    ordenados = sorted(riesgos_, key=lambda r: (-r["nivel"], r["id"]))

    s: list = []
    # Portada
    logo = config.PROYECTO / "web" / "public" / "logo-espethreat-360.png"
    if logo.exists():
        s += [Spacer(1, 1.2 * cm), Image(str(logo), width=6.5 * cm, height=6.6 * cm)]
    s += [Spacer(1, 0.8 * cm), Paragraph("Reporte de inteligencia de amenazas", e["titulo"]),
          Paragraph("Sentinel Salud · protección de datos de salud de afiliados y jubilados", e["sub"]),
          Spacer(1, 0.4 * cm), Paragraph(f"Periodo analizado: {_t(periodo_txt)}", e["sub"]),
          Paragraph(f"{registros:,} registros analizados".replace(",", "."), e["sub"]),
          Paragraph(f"Generado el {datetime.now():%d/%m/%Y %H:%M} · Equipo ESPEThreat", e["sub"]),
          Spacer(1, 0.8 * cm),
          Paragraph("Documento de uso interno. Contiene solo seudónimos; la reidentificación requiere motivo y queda "
                    "registrada. Datos del reto y datos sintéticos; sin conexión a sistemas reales.", e["chico"]),
          PageBreak()]

    # Resumen
    s += [Paragraph("Resumen", e["h1"]),
          Paragraph(f"Se revisaron {registros:,} registros del firewall y del sistema médico. ".replace(",", ".") +
                    f"Se identificaron <b>{len(vigentes)} incidentes vigentes</b>, "
                    f"<b>{sum(1 for c in vigentes if c.get('gravedad') == 'critica')} críticos</b>. "
                    f"En {ej.get('extraccionesExitosas', 0)} ocasiones la información sí salió del sistema.", e["dest"]),
          Table([[_barras_gravedad(casos), _barras_riesgos(riesgos_)]], colWidths=[8 * cm, 9.5 * cm])]

    # 1. Fuentes y metodología
    s += [Paragraph("1. Fuentes y metodología", e["h1"]),
          Paragraph("Se siguió el ciclo de inteligencia (planificación, recolección, procesamiento, análisis, difusión y "
                    "realimentación) y la Preparación de Inteligencia del Entorno (IPE) para los escenarios.", e["p"]),
          _tabla([["Disciplina", "Fuente", "Uso en el análisis"],
                  ["TECHINT (registros técnicos)", "Registros del firewall y del sistema médico del reto",
                   f"{registros:,} filas normalizadas; correlación por persona y tiempo con corrección de reloj".replace(",", ".")],
                  ["CTI y TECHINT oficial", "CISA KEV, NVD, avisos de CISA e INCIBE-CERT y avisos PSIRT de fabricantes",
                   f"{len(d['tendencias'])} tendencias evaluadas; solo fuentes oficiales para evitar ruido"],
                  ["HUMINT", "Denuncias de afiliados (portal público) y del personal de salud",
                   f"{len(d['denuncias'])} {'denuncia' if len(d['denuncias']) == 1 else 'denuncias'}; el contacto "
                   "denunciado se cruza con las citas (patrón HG-07)"],
                  ["Datos sintéticos", "Registro del chatbot de citas (generado)",
                   "Validación de comportamiento HBVF para posibles tramitadores" if agenda else "No incluido"]],
                 [3.6, 6.2, 7.4], e),
          Spacer(1, 6),
          _tabla([["Técnica", "Qué hace"],
                  ["Reglas", "Ráfagas de fallos, escaneos, servicios inseguros, cuentas genéricas y fuera de horario"],
                  ["Correlación entre fuentes", "Une eventos del firewall y del sistema médico de la misma persona; "
                                                "corrige desfases de reloj (0, -12 y +12 horas)"],
                  ["Machine learning", "Isolation Forest por ventanas de tiempo: mide qué tan fácil es aislar a un usuario"],
                  ["Priorización", "Probabilidad x impacto (1 a 25) y MITRE ATT&CK"],
                  ["Protección de datos", "Seudónimos con sal; reidentificación solo con motivo en bitácora (LOPDP)"]],
                 [4.2, 13], e)]

    # 2. Evaluación de adversarios
    s += [PageBreak(), Paragraph("2. Evaluación de adversarios", e["h1"]),
          Paragraph("Perfil estimado de quién está detrás de cada incidente. Es una hipótesis de trabajo basada en la "
                    "evidencia, no una atribución.", e["p"])]
    for c in vigentes:
        p = _perfil(c.get("titulo", ""))
        ttp = ", ".join(f"{t['id']} {t['nombre']}" for t in c.get("tecnicas", [])) or "Sin técnica asignada"
        s.append(KeepTogether([Paragraph(f"{_t(c['id'])} · {_t(c.get('titulo'))} "
                                         f"({NOMBRE_GRAV.get(c.get('gravedad'), '')})", e["h2"]),
                               _tabla([["Actor", p["actor"]], ["Motivación", p["motivacion"]],
                                       ["Objetivo", p["objetivo"]], ["Capacidad", p["capacidad"]], ["TTP", ttp],
                                       ["Evidencia", c.get("resumen", "")]], [3.2, 14], e, encabezado=False)]))
    if agenda:
        prior = [x for x in agenda.get("casos", []) if x.get("review_required")]
        s.append(KeepTogether([Paragraph("Tramitadores de citas (módulo HBVF)", e["h2"]),
                               _tabla([["Actor", "Intermediarios que acaparan citas para revenderlas"],
                                       ["Motivación", "Lucro: cobran por turnos que son gratuitos"],
                                       ["Objetivo", "Agenda del chatbot de citas al abrirse cada día"],
                                       ["Capacidad", "Baja-media: scripts, rotación de IP, VPN o nube, varios contactos"],
                                       ["TTP", "Reserva masiva para muchos pacientes, reservas en los primeros minutos, "
                                               "reasignación inmediata de citas canceladas"],
                                       ["Evidencia", f"{len(prior)} orígenes para revisión humana; "
                                                     f"{agenda['resumen'].get('citas_en_revision', 0)} citas a confirmar. "
                                                     "Datos sintéticos: prueba preliminar."]], [3.2, 14], e,
                                      encabezado=False)]))

    # 3. Inteligencia estratégica
    s += [PageBreak(), Paragraph("3. Inteligencia estratégica: impacto institucional", e["h1"]),
          Table([[_matriz(riesgos_), Paragraph(
              f"<b>{sum(1 for r in riesgos_ if r['nivel'] >= 20)} riesgos en zona crítica</b>. La matriz es dinámica: la "
              "probabilidad sale de la evidencia del análisis activo y de las decisiones del analista; el impacto es fijo "
              "por riesgo. Si un caso se descarta, su evidencia deja de contar.", e["p"])]],
                colWidths=[8.4 * cm, 8.8 * cm]),
          _tabla([["Riesgo", "P", "I", "Nivel", "Tratamiento"]] +
                 [[f"{r['id']} {r['nombre']}", str(r["probabilidad"]), str(r["impacto"]), str(r["nivel"]),
                   r["tratamiento"]] for r in ordenados[:8]], [5.6, 0.8, 0.8, 1.2, 8.8], e),
          Spacer(1, 6),
          Paragraph("Impacto para la institución: exposición de historias clínicas con obligación de notificar según la "
                    "Ley Orgánica de Protección de Datos Personales, pérdida de confianza de afiliados y jubilados, "
                    "reventa de turnos gratuitos y riesgo de interrupción del servicio médico.", e["p"])]

    # 4. Inteligencia táctica
    s += [PageBreak(), Paragraph("4. Inteligencia táctica: comportamientos y TTP", e["h1"])]
    for c in vigentes:
        pasos = [f"<b>{_t(r.get('paso'))}</b>: {_t(r.get('detalle'))}" for r in c.get("recorrido", [])]
        bloque = [Paragraph(f"{_t(c['id'])} · {_t(c.get('titulo'))}", e["h2"]),
                  Paragraph(f"Inicio {_t(_fecha(c.get('inicio')))}, duración {_t(c.get('duracion'))}, desde "
                            f"{_t(c.get('ipOrigen'))} por {_t(c.get('protocolo'))}.", e["p"])]
        bloque += [Paragraph("• " + p, e["celda"]) for p in pasos[:6]]
        med = c.get("explicacion") or []
        if med:
            bloque.append(Spacer(1, 3))
            bloque.append(_tabla([["Medición", "Valor", "Rango normal"]] +
                                 [[x["nombre"], f"{x['valor']} {x.get('unidad', '')}",
                                   f"{x['refMin']} a {x['refMax']}"] for x in med[:5]], [8, 4, 5.2], e))
        s.append(KeepTogether(bloque))

    # 5. Inteligencia operativa
    s += [PageBreak(), Paragraph("5. Inteligencia operativa: campañas, actividades y escenarios de ataque", e["h1"]),
          _tabla([["Fecha", "Actividad", "Gravedad", "Estado", "Acción recomendada"]] +
                 [[str(h.get("fecha", "")), h.get("titulo", ""), NOMBRE_GRAV.get(h.get("gravedad"), ""),
                   h.get("estado", ""), h.get("accion", "")] for h in ej.get("historia", [])],
                 [2.6, 3.6, 1.8, 2.0, 7.2], e)]
    if agenda:
        r = agenda["resumen"]
        est = r.get("estados", {})
        s += [Paragraph("Campaña de acaparamiento de citas", e["h2"]),
              Paragraph(f"{r.get('reservas', 0)} reservas y {r.get('sesiones', 0)} conversaciones agrupadas en "
                        f"{r.get('puntos', 0)} orígenes. Revisión prioritaria: {est.get('Revisión prioritaria', 0)}; "
                        f"requiere revisión: {est.get('Requiere revisión', 0)}; explicados por cuidadores u operadores "
                        f"autorizados: {est.get('Explicado por contexto legítimo', 0)}. Ninguna cita se cancela de forma "
                        "automática.", e["p"])]
    dens = d["denuncias"]
    if dens:
        por_tipo: dict[str, int] = {}
        for x in dens:
            por_tipo[x.get("tipo_texto", x.get("tipo", ""))] = por_tipo.get(x.get("tipo_texto", x.get("tipo", "")), 0) + 1
        s += [Paragraph("Actividad reportada por afiliados y personal", e["h2"]),
              _tabla([["Tipo de denuncia", "Cantidad"]] + [[k, str(v)] for k, v in sorted(por_tipo.items())],
                     [13, 4.2], e)]

    # 6. Inteligencia técnica
    intel = d["inteligencia"]
    s += [PageBreak(), Paragraph("6. Inteligencia técnica: IoC, IoA, reglas de detección y correlación", e["h1"]),
          Paragraph("Indicadores de compromiso (IoC)", e["h2"]),
          _tabla([["Tipo", "Valor", "Descripción", "Caso", "Conf."]] +
                 [[i["tipo"], i["valor"], i["descripcion"], i["casoId"], f"{i['confianza']} %"]
                  for i in intel.get("iocs", [])[:18]], [2.4, 3.6, 7.6, 1.6, 2.0], e),
          Paragraph("Indicadores de ataque (IoA)", e["h2"]),
          _tabla([["Comportamiento", "Técnica"]] +
                 [[f"{c.get('titulo')}: {c.get('resumen', '')}",
                   ", ".join(t["id"] for t in c.get("tecnicas", []))] for c in vigentes], [13.2, 4], e),
          Paragraph("Reglas de detección (Sigma) y correlación", e["h2"]),
          _tabla([["Regla", "Nivel", "Técnica", "Casos"]] +
                 [[r["titulo"], r["nivel"], r["tecnica"], ", ".join(r.get("casos", []))]
                  for r in intel.get("sigma", [])], [9, 2.2, 3, 3], e),
          Paragraph("Correlación: un incidente se confirma cuando el mismo comportamiento aparece en el firewall y en el "
                    "sistema médico en la misma ventana de tiempo, con corrección de reloj. Exportes disponibles: STIX "
                    "2.1, MISP, Sigma, Maltego y Power BI.", e["p"])]

    # 7. Evaluación de escenarios (IPE)
    # Más peligroso: el de mayor impacto (y nivel). Más probable: entre los de mayor probabilidad, el más
    # frecuente y menos grave, distinto del peligroso (el curso de acción "común" del adversario).
    peligroso = max(riesgos_, key=lambda r: (r["impacto"], r["nivel"]), default=None)
    resto = [r for r in riesgos_ if not peligroso or r["id"] != peligroso["id"]] or riesgos_
    comun = min(resto, key=lambda r: (-r["probabilidad"], r["impacto"], -r["nivel"]), default=None)
    s += [PageBreak(), Paragraph("7. Evaluación de escenarios (IPE)", e["h1"]),
          Paragraph("Con la Preparación de Inteligencia del Entorno se plantean dos cursos de acción del adversario: el "
                    "más probable y el más peligroso.", e["p"])]
    if comun:
        s += [Paragraph("Escenario más probable (más común)", e["h2"]),
              _tabla([["Escenario", f"{comun['id']} {comun['nombre']}"],
                      ["Por qué", "; ".join(comun.get("evidencia", [])[:3])],
                      ["Probabilidad x impacto", f"{comun['probabilidad']} x {comun['impacto']} = {comun['nivel']}"],
                      ["Indicadores de alerta temprana", "Ráfagas de accesos fallidos, reservas masivas al abrir la agenda, "
                                                         "denuncias de cobro por citas"],
                      ["Respuesta", comun["tratamiento"]]], [4.2, 13], e, encabezado=False)]
    if peligroso:
        s += [Paragraph("Escenario más peligroso", e["h2"]),
              _tabla([["Escenario", f"{peligroso['id']} {peligroso['nombre']}"],
                      ["Desarrollo", "Una cuenta válida o genérica accede fuera de horario, consulta historias clínicas "
                                     "y las extrae por un canal remoto; los datos se venden o se usan para extorsión."],
                      ["Por qué", "; ".join(peligroso.get("evidencia", [])[:3])],
                      ["Probabilidad x impacto",
                       f"{peligroso['probabilidad']} x {peligroso['impacto']} = {peligroso['nivel']}"],
                      ["Indicadores de alerta temprana", "Transferencias SSH fuera de rango, cuentas sin dueño activas en "
                                                         "fin de semana, desfase de relojes entre fuentes"],
                      ["Respuesta", peligroso["tratamiento"]]], [4.2, 13], e, encabezado=False)]

    # 8. Conclusiones
    s += [PageBreak(), Paragraph("8. Conclusiones y prioridades", e["h1"])]
    conclusiones = [
        f"De {registros:,} registros salieron {len(vigentes)} incidentes vigentes; ".replace(",", ".") +
        f"{sum(1 for c in vigentes if c.get('gravedad') == 'critica')} son críticos y requieren acción inmediata.",
        "El cruce de firewall y sistema médico confirma los ataques que una sola fuente no explica, incluido el desfase "
        "de reloj.",
        "La amenaza con mayor impacto es la extracción de datos clínicos por cuentas válidas o genéricas: es la "
        "prioridad de control de accesos.",
    ]
    if agenda:
        conclusiones.append("El acaparamiento de citas es detectable con patrones de comportamiento sin castigar a "
                            "cuidadores autorizados; se confirma con el afiliado antes de actuar.")
    if dens:
        conclusiones.append("Las denuncias ciudadanas aportan evidencia externa (HUMINT) que acelera la revisión.")
    s += [Paragraph("• " + _t(c), e["p"]) for c in conclusiones]
    s += [Paragraph("Acciones priorizadas", e["h2"]),
          _tabla([["#", "Acción", "Riesgo"]] + [[str(i + 1), r["tratamiento"], f"{r['id']} (nivel {r['nivel']})"]
                                                for i, r in enumerate(ordenados[:5])], [0.8, 12.6, 3.8], e),
          Spacer(1, 10),
          Paragraph("Resultado esperado: priorizar acciones oportunas y controles de seguridad de la información y "
                    "ciberseguridad. Ninguna acción sobre personas o citas es automática: el sistema recomienda y una "
                    "persona decide.", e["dest"])]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.9 * cm, rightMargin=1.9 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title="Reporte de inteligencia de amenazas", author="ESPEThreat")

    def pie(c, doc_):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS)
        c.drawString(1.9 * cm, 1.1 * cm, "Sentinel Salud · ESPEThreat · Uso interno, solo seudónimos")
        c.drawRightString(A4[0] - 1.9 * cm, 1.1 * cm, f"Página {doc_.page}")
        c.setStrokeColor(VERDE)
        c.setLineWidth(2)
        c.line(1.9 * cm, A4[1] - 1.2 * cm, A4[0] - 1.9 * cm, A4[1] - 1.2 * cm)
        c.restoreState()

    doc.build(s, onFirstPage=lambda c, d_: None, onLaterPages=pie)
    return buf.getvalue()


# ---------- informe gerencial (para gerencia: sin IPs, cuentas ni códigos técnicos) ----------
def _kpis(valores: list[tuple[str, str, bool]], e: dict) -> Table:
    celdas = []
    for valor, etiqueta, critico in valores:
        celdas.append([Paragraph(f'<font size="20" color="{"#C1272D" if critico else "#003D24"}"><b>{_t(valor)}</b></font>',
                                 e["p"]), Paragraph(_t(etiqueta), e["chico"])])
    t = Table([[c for c in celdas]], colWidths=[17.2 * cm / len(celdas)] * len(celdas))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, LINEA), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINEA),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("LINEABOVE", (0, 0), (-1, 0), 3, VERDE)]))
    return t


def _barras_dimensiones(dims: list[dict]) -> Drawing:
    d = Drawing(17 * cm, 5.2 * cm)
    ch = HorizontalBarChart()
    ch.x, ch.y, ch.width, ch.height = 120, 8, 17 * cm - 160, 4.4 * cm
    datos = dims[::-1]
    ch.data = [[x["exposicion"] for x in datos]]
    ch.categoryAxis.categoryNames = [x["nombre"] for x in datos]
    ch.valueAxis.valueMin, ch.valueAxis.valueMax, ch.valueAxis.valueStep = 0, 25, 5
    ch.bars.strokeColor = None
    for i, x in enumerate(datos):
        ch.bars[(0, i)].fillColor = _color_nivel(x["exposicion"])
    ch.categoryAxis.labels.fontSize = 8.5
    ch.categoryAxis.labels.boxAnchor = "e"
    ch.valueAxis.labels.fontSize = 7
    ch.barLabelFormat = "%d"
    ch.barLabels.fontSize = 8
    ch.barLabels.nudge = 8
    d.add(ch)
    return d


def generar_gerencial() -> bytes:
    d = recolectar()
    e = _estilos()
    ej, casos, riesgos_ = d["ejecutivo"], d["casos"], d["riesgos"]
    vigentes = [c for c in casos if c.get("estado") != "descartado"]
    periodo = ej.get("periodo") or {}
    periodo_txt = f"{periodo.get('desde', '')} a {periodo.get('hasta', '')}" if isinstance(periodo, dict) else str(periodo)
    registros = ej.get("registros") or 0
    ag = ej.get("agendamiento")
    criticos = sum(1 for c in vigentes if c.get("gravedad") == "critica")
    ordenados = sorted(riesgos_, key=lambda r: (-r["nivel"], r["id"]))

    s: list = []
    logo = config.PROYECTO / "web" / "public" / "logo-espethreat-360.png"
    cab = [Paragraph("Informe gerencial de seguridad", e["h1"]),
           Paragraph(f"Periodo {_t(periodo_txt)} · Sentinel Salud · ESPEThreat", e["chico"])]
    if logo.exists():
        t = Table([[Image(str(logo), width=2.2 * cm, height=2.25 * cm), cab]], colWidths=[2.6 * cm, 14.6 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        s.append(t)
    else:
        s += cab
    s.append(Spacer(1, 8))
    s.append(Paragraph(
        f"Revisamos {registros:,} registros y encontramos <b>{len(vigentes)} incidentes</b>; ".replace(",", ".") +
        f"<b>{criticos} son críticos</b>." +
        (f" La información salió del sistema en {ej.get('extraccionesExitosas')} ocasiones: corresponde evaluar la "
         "notificación que exige la LOPDP." if ej.get("extraccionesExitosas") else ""), e["dest"]))
    corto = (f"{registros / 1e6:.1f} M".replace(".", ",") if registros >= 1e6 else
             f"{round(registros / 1e3)} mil" if registros >= 1e4 else str(registros))
    kp = [(corto, "registros revisados", False), (str(len(vigentes)), "incidentes", False),
          (str(criticos), "críticos", criticos > 0), (str(ej.get("extraccionesExitosas", 0)), "veces salió información",
                                                       bool(ej.get("extraccionesExitosas")))]
    if ag:
        kp.append((str(ag.get("citasAConfirmar", 0)), "citas a confirmar", False))
    kp.append((str(ej.get("denuncias", {}).get("recibidas", 0)), "denuncias", False))
    s += [_kpis(kp, e), Spacer(1, 10),
          Table([[_barras_gravedad(casos), _barras_riesgos(riesgos_)]], colWidths=[8 * cm, 9.5 * cm]),
          Paragraph("Qué pasó", e["h2"]),
          _tabla([["Fecha", "Qué pasó", "Gravedad", "Qué hacer"]] +
                 [[_fecha(h.get("inicio"))[:10], f"{h.get('titulo')}: {h.get('frase', '')}",
                   NOMBRE_GRAV.get(h.get("gravedad"), ""), h.get("accion", "")] for h in ej.get("historia", [])],
                 [2.2, 8.2, 1.8, 5.0], e),
          PageBreak()]
    from . import impacto
    neg = impacto.negocio(riesgos_)
    s += [Paragraph("Cómo afecta al negocio", e["h1"]),
          Paragraph(f"Índice de riesgo del mes: <b>{neg['indice']} de 100</b>. Cada barra muestra cuánto pesa hoy el riesgo "
                    "sobre una parte del negocio: probabilidad encontrada en los datos × impacto en esa dimensión "
                    "(de 1 a 25).", e["p"]),
          _barras_dimensiones(neg["dimensiones"]),
          _tabla([["Dimensión", "Pregunta de negocio", "Nivel", "Riesgos que más pesan"]] +
                 [[x["nombre"], x["pregunta"], NOMBRE_GRAV.get(x["nivel"], ""),
                   ", ".join(f"{r['riesgo']} {r['nombre']}" for r in x["riesgos"][:2])] for x in neg["dimensiones"]],
                 [3.4, 5.6, 1.6, 6.6], e)]
    for r in neg["riesgos"][:4]:
        s.append(KeepTogether([
            Paragraph(f"{_t(r['id'])} · {_t(r['nombre'])} (nivel {r['nivel']} de 25)", e["h2"]),
            _tabla([["Proceso afectado", r["proceso"]], ["Qué pasaría", r["escenario"]],
                    ["En la operación", r["operativa"]], ["Legal (LOPDP)", r["legal"]],
                    ["Reputación", r["reputacional"]], ["Costos", r["financiera"]],
                    ["Decisión recomendada", r["decision"]]], [3.6, 13.6], e, encabezado=False)]))
    s += [PageBreak(),
          Paragraph("Dónde está el riesgo", e["h1"]),
          Table([[_matriz(riesgos_), Paragraph(
              "La probabilidad sale de lo que encontramos en los datos y de las decisiones del analista; el impacto es "
              "fijo por riesgo. Rojo: atender ya. Naranja: planificar este mes.", e["p"])]], colWidths=[8.4 * cm, 8.8 * cm]),
          Paragraph("Prioridades recomendadas", e["h2"]),
          _tabla([["#", "Decisión", "Riesgo", "Nivel"]] +
                 [[str(i + 1), r["tratamiento"], r["nombre"], str(r["nivel"])] for i, r in enumerate(ordenados[:6])],
                 [0.8, 8.6, 6.2, 1.6], e)]
    if ag:
        s += [Paragraph("Citas del chatbot", e["h2"]),
              Paragraph(f"{ag.get('origenesEnRevision', 0)} orígenes reservan citas para muchos pacientes, como un "
                        f"tramitador. Conviene confirmar {ag.get('citasAConfirmar', 0)} de {ag.get('reservas', 0)} citas "
                        f"con el afiliado. {ag.get('explicadosLegitimos', 0)} casos parecidos eran cuidadores u operadores "
                        "autorizados y no se marcaron. Ninguna cita se cancela de forma automática.", e["p"])]
    s += [Spacer(1, 8), Paragraph("Ninguna acción sobre personas o citas es automática: el sistema recomienda y una "
                                  "persona decide. Datos del reto y datos sintéticos.", e["chico"])]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.9 * cm, rightMargin=1.9 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.8 * cm, title="Informe gerencial de seguridad", author="ESPEThreat")

    def pie(c, doc_):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS)
        c.drawString(1.9 * cm, 1.1 * cm, "Sentinel Salud · Informe gerencial · Uso interno")
        c.drawRightString(A4[0] - 1.9 * cm, 1.1 * cm, f"Página {doc_.page}")
        c.restoreState()

    doc.build(s, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()
