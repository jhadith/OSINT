"""Vista ejecutiva: el mes contado en lenguaje simple para gerencia y para un jurado no técnico."""
from __future__ import annotations

import re

from . import datos, denuncias, riesgos

FRASE = {
    "Fuerza bruta": "Intentaron adivinar contraseñas del sistema médico, miles de veces en pocos minutos.",
    "Escaneo de servicios": "Revisaron una por una las puertas de entrada del servidor médico.",
    "Posible fuga de datos": "Se sacó información del sistema médico por una conexión remota, en segundos.",
    "Cuenta fantasma": "Una cuenta que nadie usaba entró una sola vez en el mes, solo para descargar información.",
    "Accesos fallidos masivos": "Una cuenta acumuló miles de ingresos fallidos en un día.",
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def _fecha_simple(iso: str) -> str:
    a, m, d = iso[:10].split("-")
    return f"{int(d)} de {MESES[int(m) - 1]}, {iso[11:16]}"


def _extracciones(alertas: list[dict], casos_vigentes: set[str]) -> int:
    total = 0
    for a in alertas:
        if not a.get("caso") or f"C{a['caso'].split()[1]}" not in casos_vigentes:
            continue
        acc = a.get("evidencia", {}).get("sistema_medico", {}).get("acciones", {})
        total += sum(v for k, v in acc.items() if re.search(r"EXITOSA|DESCARGA", k, re.I))
    return total


def armar() -> dict:
    r = datos.motor("resumen_motor.json", {})
    casos = datos.casos()
    vigentes = [c for c in casos if c["estado"] != "descartado"]
    registros = r["registros"]["total"]
    jornadas = registros / (8 * 3600)          # una persona leyendo un registro por segundo, 8 horas al día
    mat = riesgos.calcular()
    ag = datos.agendamiento()
    den = denuncias.todas()
    serie = datos.consola("serie")
    return {
        "periodo": r["periodo"], "archivos": r.get("archivos", {}),
        "registros": registros, "minutos": r["tiempo_analisis_min"],
        "jornadasManuales": round(jornadas), "anosManuales": round(jornadas / 240, 1),
        "incidentes": len(vigentes), "criticos": sum(1 for c in vigentes if c["gravedad"] == "critica"),
        "pendientes": sum(1 for c in vigentes if c["estado"] == "pendiente"),
        "confirmados": sum(1 for c in vigentes if c["estado"] == "confirmado"),
        "extraccionesExitosas": _extracciones(datos.motor("alertas.json", []), {c["id"] for c in vigentes}),
        "historia": [{"id": c["id"], "fecha": _fecha_simple(c["inicio"]), "inicio": c["inicio"], "titulo": c["titulo"],
                      "gravedad": c["gravedad"], "frase": FRASE.get(c["titulo"], c["resumen"]),
                      "accion": c["acciones"][0] if c["acciones"] else "", "estado": c["estado"],
                      "avisoTelegram": bool(c.get("alerta"))} for c in sorted(vigentes, key=lambda c: c["inicio"])],
        "riesgosPrincipales": sorted(mat, key=lambda x: -x["nivel"])[:3],
        "riesgosCriticos": sum(1 for x in mat if x["nivel"] >= 20),
        "agendamiento": None if not ag else {
            "origenesEnRevision": sum(1 for c in ag["casos"] if c["review_required"]
                                      and not c["status"].startswith("Indeterminado")),
            "citasAConfirmar": ag["resumen"]["citas_en_revision"], "reservas": ag["resumen"]["reservas"],
            "explicadosLegitimos": ag["resumen"]["estados"].get("Explicado por contexto legítimo", 0)},
        "denuncias": {"recibidas": len(den), "abiertas": sum(1 for d in den if d["estado"] in ("recibida", "en_revision"))},
        "pulso": [{"ts": p["ts"], "v": p["puntuacion"]} for p in serie],
    }
