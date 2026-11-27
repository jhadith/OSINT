"""Impacto en el negocio y datos del tablero.

Toda amenaza que aparece en cualquier sección (casos, anomalías, citas, denuncias, verificar contenido,
tendencias) se conecta a sus riesgos de la matriz (R1–R11). Cada riesgo afecta cinco dimensiones del
negocio con un impacto fijo de 1 a 5 (fijos/impacto_negocio.json). La exposición viva de una dimensión
es la mayor probabilidad × impacto entre los riesgos que la tocan: si el analista descarta un caso,
baja la probabilidad del riesgo y baja también el impacto en el negocio.
"""
from __future__ import annotations

import json
from collections import Counter

from fastapi import HTTPException

from . import config

# Técnica MITRE → riesgo de la matriz (para conectar tendencias externas con el negocio).
TECNICA_RIESGO = {"T1486": "R3", "T1021.002": "R3", "T1078": "R1", "T1048": "R2", "T1021.004": "R2",
                  "T1566": "R4", "T1110": "R4", "T1046": "R7", "T1213": "R2", "T1190": "R3"}
DENUNCIA_RIESGO = {"venta_de_citas": ["R9"], "pedido_de_datos": ["R4", "R1"], "enlace_sospechoso": ["R4"],
                   "uso_de_mis_datos": ["R1", "R9"], "contenido_reportado": ["R4"], "otro": ["R10"]}


def modelo() -> dict:
    return json.loads((config.FIJOS / "impacto_negocio.json").read_text(encoding="utf-8"))


def nivel_txt(n: int) -> str:
    return "critica" if n >= 20 else "alta" if n >= 12 else "media" if n >= 6 else "baja"


def negocio(riesgos: list[dict]) -> dict:
    """Exposición por dimensión y riesgos con su explicación de negocio."""
    m = modelo()
    por_id = {r["id"]: r for r in riesgos}
    dims = []
    for d in m["dimensiones"]:
        aportes = []
        for rid, info in m["riesgos"].items():
            r = por_id.get(rid)
            if not r:
                continue
            imp = info["impactos"].get(d["id"], 1)
            aportes.append({"riesgo": rid, "nombre": r["nombre"], "probabilidad": r["probabilidad"], "impacto": imp,
                            "exposicion": r["probabilidad"] * imp})
        aportes.sort(key=lambda a: (-a["exposicion"], a["riesgo"]))
        # promedio de los tres riesgos que más la golpean: distingue dimensiones mejor que el máximo
        tres = [a["exposicion"] for a in aportes[:3]] or [1]
        top = round(sum(tres) / len(tres))
        dims.append({**d, "exposicion": top, "nivel": nivel_txt(top), "riesgos": aportes[:4]})
    detalle = []
    for r in sorted(riesgos, key=lambda x: (-x["nivel"], x["id"])):
        info = m["riesgos"].get(r["id"])
        if info:
            detalle.append({**r, **{k: info[k] for k in ("proceso", "escenario", "operativa", "legal", "reputacional",
                                                          "financiera", "decision")}, "impactos": info["impactos"]})
    top5 = sorted((r["nivel"] for r in riesgos), reverse=True)[:5] or [0]
    return {"dimensiones": dims, "riesgos": detalle, "indice": round(100 * sum(top5) / (25 * len(top5))),
            "nota": m["nota"]}


def _dims_de(riesgos_ids: list[str], m: dict) -> list[str]:
    """Las dimensiones más golpeadas (impacto ≥ 4) por esos riesgos."""
    c: Counter = Counter()
    for rid in riesgos_ids:
        for dim, v in m["riesgos"].get(rid, {}).get("impactos", {}).items():
            if v >= 4:
                c[dim] = max(c[dim], v)
    return [d for d, _ in c.most_common(3)]


def tablero() -> dict:
    """Todo lo que necesitan las cinco pestañas del tablero, desde el análisis activo."""
    from . import datos, denuncias, ejecutivo, riesgos

    casos = datos.casos()                       # 409 si no hay análisis
    m = modelo()
    rs = riesgos.calcular()
    neg = negocio(rs)

    def intento(fn, defecto):
        try:
            return fn()
        except (HTTPException, OSError, ValueError, KeyError):
            return defecto

    ej = intento(ejecutivo.armar, {})
    serie = intento(lambda: datos.consola("serie"), [])
    agenda = intento(datos.agendamiento, None)
    dens = intento(denuncias.todas, [])
    anom = {f: intento(lambda f=f: datos.consola(f"anomalias_{f}"), {"filas": [], "total": 0})
            for f in ("firewall", "sistema_medico")}
    grafo = intento(lambda: datos.consola("grafo"), {"nodos": [], "aristas": []})
    tend = intento(_tendencias, [])
    detalles = [intento(lambda c=c: datos.caso(c["id"]), c) for c in casos]
    vigentes = [c for c in detalles if c.get("estado") != "descartado"]

    # ----- amenazas de todas las secciones, conectadas al negocio -----
    amenazas = []
    for c in vigentes:
        amenazas.append({"origen": "Casos", "titulo": c["titulo"], "gravedad": c["gravedad"], "riesgos": c.get("riesgos", []),
                         "ruta": f"/casos/{c['id']}", "fecha": c.get("inicio", "")})
    for f, p in anom.items():
        solas = [x for x in p.get("filas", []) if x.get("sospechosa") and not x.get("casoId")]
        if solas:
            quien = ("cuenta rara" if len(solas) == 1 else "cuentas raras") if f == "sistema_medico" else \
                ("usuario de red raro" if len(solas) == 1 else "usuarios de red raros")
            amenazas.append({"origen": "Anomalías", "titulo": f"{len(solas)} {quien} sin caso abierto",
                             "gravedad": "baja", "riesgos": ["R1"] if f == "sistema_medico" else ["R5"],
                             "ruta": "/anomalias", "fecha": ""})
    if agenda:
        rev = [x for x in agenda.get("casos", []) if x.get("review_required")]
        prior = [x for x in rev if x["status"] == "Revisión prioritaria"]
        if rev:
            amenazas.append({"origen": "Citas del chatbot", "titulo": f"{len(rev)} orígenes acaparan citas "
                                                                       f"({len(prior)} prioritarios)",
                             "gravedad": "alta" if prior else "media", "riesgos": ["R9"], "ruta": "/agendamiento", "fecha": ""})
    abiertas = [d for d in dens if d["estado"] in ("recibida", "en_revision")]
    for tipo, n in Counter(d["tipo"] for d in abiertas).items():
        origen = "Verificar contenido" if tipo == "contenido_reportado" else "Denuncias"
        txt = next((d["tipo_texto"] for d in abiertas if d["tipo"] == tipo), tipo)
        amenazas.append({"origen": origen, "titulo": f"{n} × {txt}", "gravedad": "media",
                         "riesgos": DENUNCIA_RIESGO.get(tipo, ["R10"]), "ruta": "/denuncias", "fecha": ""})
    for t in [t for t in tend if str(t.get("sello", "")).startswith("real")][:6]:
        rid = next((TECNICA_RIESGO[x] for x in t.get("tecnicas", []) if x in TECNICA_RIESGO), "R3")
        amenazas.append({"origen": "Amenazas externas", "titulo": t["titulo"], "gravedad": "alta" if t.get("kev") else "media",
                         "riesgos": [rid], "ruta": "/tendencias", "fecha": t.get("fecha", "")})
    orden = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
    for a in amenazas:
        a["dimensiones"] = _dims_de(a["riesgos"], m)
    amenazas.sort(key=lambda a: (orden.get(a["gravedad"], 9), a["origen"]))

    # ----- internas -----
    tecnicas = Counter(f"{t['id']} {t['nombre']}" for c in vigentes for t in c.get("tecnicas", []))
    por_dia: dict[str, dict] = {}
    for p in serie:
        d = por_dia.setdefault(p["ts"][:10], {"dia": p["ts"][:10], "fallidos": 0, "ssh": 0, "transferencias": 0})
        for k in ("fallidos", "ssh", "transferencias"):
            d[k] += p.get(k, 0)
    activos = Counter()                     # equipos de origen con más eventos hacia el servidor médico
    tipos = {n["id"]: n for n in grafo.get("nodos", [])}
    for a in grafo.get("aristas", []):
        o = tipos.get(a["origen"])
        if o and o["tipo"] == "ip":
            activos[o["etiqueta"]] += a.get("eventos", 0)

    return {
        "periodo": ej.get("periodo"), "registros": ej.get("registros", 0), "minutos": ej.get("minutos", 0),
        "indice": neg["indice"],
        "resumen": {k: ej.get(k) for k in ("incidentes", "criticos", "pendientes", "confirmados", "extraccionesExitosas",
                                            "jornadasManuales", "historia", "pulso", "denuncias", "agendamiento")},
        "amenazas": amenazas,
        "internas": {
            "casos": [{k: c.get(k) for k in ("id", "titulo", "gravedad", "inicio", "estado", "ipOrigen")} |
                      {"ambas": bool(c.get("firewall") and c.get("sistemaMedico"))} for c in detalles],
            "mitre": [{"tecnica": k, "casos": v} for k, v in tecnicas.most_common(8)],
            "porDia": list(por_dia.values()),
            "activos": [{"activo": k, "eventos": v} for k, v in activos.most_common(6)],
            "anomalias": {f: {"total": p.get("total", 0),
                              "sospechosas": sum(1 for x in p.get("filas", []) if x.get("sospechosa")),
                              "sinCaso": sum(1 for x in p.get("filas", []) if x.get("sospechosa") and not x.get("casoId"))}
                          for f, p in anom.items()},
        },
        "citas": {
            "agenda": ({"resumen": agenda["resumen"],
                        "top": [{k: x[k] for k in ("case_id", "status", "risk_score", "confidence", "pattern_ids")} |
                                {"pacientes": x["resumen"]["pacientes"], "reservas": x["resumen"]["reservas"],
                                 "denuncias": len(x.get("denuncias_vinculadas", []))}
                                for x in agenda["casos"] if x.get("review_required")][:8],
                        "evaluacion": agenda.get("evaluacion")} if agenda else None),
            "denunciasTipo": [{"tipo": t, "n": n} for t, n in Counter(d["tipo_texto"] for d in dens).most_common()],
            "denunciasEstado": dict(Counter(d["estado"] for d in dens)),
            "verificar": sum(1 for d in dens if d["tipo"] == "contenido_reportado"),
        },
        "externas": {
            "tendencias": [{k: t.get(k) for k in ("id", "titulo", "fuente", "fecha", "sello", "kev", "cvss", "relevancia",
                                                   "exposicion", "impacto", "exposicionLocal", "tecnicas", "score")}
                           for t in tend],
            "porFuente": dict(Counter(t.get("fuente", "") for t in tend)),
            "reales": sum(1 for t in tend if str(t.get("sello", "")).startswith("real")),
        },
        "negocio": neg,
    }


def _tendencias() -> list[dict]:
    from . import osint, threatpulse
    fijo = json.loads((config.FIJOS / "tendencias.json").read_text(encoding="utf-8"))["tendencias"]
    try:
        reales, _ = osint.tendencias_reales()
    except Exception:
        reales = []
    lista = threatpulse.evaluar(reales) if reales else threatpulse.evaluar([{**t, "sello": "simulado"} for t in fijo])
    return sorted(lista, key=lambda t: -(t.get("score") or 0))
