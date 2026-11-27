"""Genera un reporte de SonarQube Cloud (HTML imprimible + CSV + JSON) desde su API.

Uso:
    export SONAR_TOKEN=...            # token de sonarcloud.io (My Account > Security)
    export SONAR_PROJECT_KEY=jhadith_osit
    python scripts/reporte_sonar.py [--rama dev | --pr 27] [--salida reporte_sonarqube]

Crea en la carpeta de salida:
    reporte.html   resumen listo para abrir o imprimir como PDF desde el navegador
    issues.csv     problemas abiertos (bugs, vulnerabilidades, code smells)
    hotspots.csv   puntos de seguridad por revisar
    cobertura.csv  cobertura por archivo
    datos.json     todo lo anterior en crudo

Solo lee datos (peticiones GET). El token nunca se escribe en los archivos generados.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HOST = os.environ.get("SONAR_HOST_URL", "https://sonarcloud.io").rstrip("/")
METRICAS = [
    "alert_status", "bugs", "vulnerabilities", "code_smells", "security_hotspots", "security_hotspots_reviewed",
    "coverage", "lines_to_cover", "uncovered_lines", "duplicated_lines_density", "ncloc",
    "reliability_rating", "security_rating", "sqale_rating", "security_review_rating", "sqale_index",
]
NOMBRES = {
    "bugs": "Bugs", "vulnerabilities": "Vulnerabilidades", "code_smells": "Code smells",
    "security_hotspots": "Security hotspots", "security_hotspots_reviewed": "Hotspots revisados (%)",
    "coverage": "Cobertura (%)", "lines_to_cover": "Líneas a cubrir", "uncovered_lines": "Líneas sin cubrir",
    "duplicated_lines_density": "Duplicación (%)", "ncloc": "Líneas de código",
    "reliability_rating": "Fiabilidad", "security_rating": "Seguridad", "sqale_rating": "Mantenibilidad",
    "security_review_rating": "Revisión de seguridad", "sqale_index": "Deuda técnica (min)",
    "new_coverage": "Cobertura en código nuevo (%)", "new_duplicated_lines_density": "Duplicación en código nuevo (%)",
    "new_reliability_rating": "Fiabilidad en código nuevo", "new_security_rating": "Seguridad en código nuevo",
    "new_maintainability_rating": "Mantenibilidad en código nuevo",
    "new_security_hotspots_reviewed": "Hotspots revisados en código nuevo (%)", "new_violations": "Issues nuevos",
}
NOTA = {"1.0": "A", "2.0": "B", "3.0": "C", "4.0": "D", "5.0": "E"}
ESTADO_PUERTA = {"OK": "Aprobada", "ERROR": "No aprobada", "WARN": "Con advertencias", "NONE": "Sin puerta de calidad"}


class ErrorSonar(RuntimeError):
    pass


class Cliente:
    def __init__(self, token: str, proyecto: str, rama: str | None = None, pr: str | None = None, host: str = HOST):
        if not host.startswith("https://"):
            raise ErrorSonar(f"El host de SonarQube debe usar https:// (se recibió {host!r}).")
        self.token, self.proyecto, self.host = token, proyecto, host
        self.alcance = {"pullRequest": pr} if pr else {"branch": rama} if rama else {}

    def get(self, ruta: str, **params) -> dict:
        consulta = urllib.parse.urlencode({**params, **self.alcance})
        url = f"{self.host}{ruta}?{consulta}"  # el host se valida como https:// en __init__
        pedido = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
        if self.token:
            pedido.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(pedido, timeout=30) as r:  # nosec B310  # noqa: S310 (host https fijo)
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise ErrorSonar(f"SonarQube Cloud respondió {e.code} en {ruta}: {detalle}") from e
        except urllib.error.URLError as e:
            raise ErrorSonar(f"No se pudo conectar con {self.host}: {e.reason}") from e

    def paginas(self, ruta: str, lista: str, **params) -> list[dict]:
        """Recorre todas las páginas (la API permite hasta 10.000 resultados)."""
        out, p = [], 1
        while True:
            d = self.get(ruta, p=p, ps=500, **params)
            out += d.get(lista, [])
            total = d.get("paging", {}).get("total", d.get("total", 0))
            if not d.get(lista) or len(out) >= min(total, 10_000):
                return out
            p += 1


def recolectar(c: Cliente) -> dict:
    puerta = c.get("/api/qualitygates/project_status", projectKey=c.proyecto)["projectStatus"]
    medidas = c.get("/api/measures/component", component=c.proyecto,
                    metricKeys=",".join(METRICAS + [k for k in NOMBRES if k.startswith("new_")]))["component"]
    valores = {}
    for m in medidas.get("measures", []):
        valores[m["metric"]] = m.get("value", (m.get("period") or {}).get("value"))
    issues = c.paginas("/api/issues/search", "issues", componentKeys=c.proyecto, resolved="false")
    hotspots = c.paginas("/api/hotspots/search", "hotspots", projectKey=c.proyecto)
    archivos = c.paginas("/api/measures/component_tree", "components", component=c.proyecto, qualifiers="FIL",
                         metricKeys="coverage,uncovered_lines,lines_to_cover,ncloc")
    return {"proyecto": c.proyecto, "nombre": medidas.get("name", c.proyecto), "alcance": c.alcance,
            "generado": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "puerta": puerta, "metricas": valores,
            "issues": issues, "hotspots": hotspots, "archivos": archivos}


def _ruta(componente: str) -> str:
    return componente.split(":", 1)[-1]


def _valor(metrica: str, v) -> str:
    if v is None:
        return "—"
    if metrica.endswith("rating"):
        try:
            return NOTA.get(f"{float(v):.1f}", str(v))
        except ValueError:
            return str(v)
    return str(v)


def escribir_csv(datos: dict, carpeta: Path) -> None:
    with open(carpeta / "issues.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tipo", "severidad", "regla", "archivo", "linea", "mensaje", "estado", "creado"])
        for i in datos["issues"]:
            w.writerow([i.get("type"), i.get("severity"), i.get("rule"), _ruta(i.get("component", "")), i.get("line", ""),
                        i.get("message"), i.get("issueStatus", i.get("status")), i.get("creationDate")])
    with open(carpeta / "hotspots.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["categoria", "probabilidad", "estado", "archivo", "linea", "mensaje", "regla"])
        for h in datos["hotspots"]:
            w.writerow([h.get("securityCategory"), h.get("vulnerabilityProbability"), h.get("status"),
                        _ruta(h.get("component", "")), h.get("line", ""), h.get("message"), h.get("ruleKey")])
    with open(carpeta / "cobertura.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "cobertura", "lineas_sin_cubrir", "lineas_a_cubrir", "lineas_de_codigo"])
        for a in datos["archivos"]:
            m = {x["metric"]: x.get("value") for x in a.get("measures", [])}
            w.writerow([a.get("path", a.get("name")), m.get("coverage", ""), m.get("uncovered_lines", ""),
                        m.get("lines_to_cover", ""), m.get("ncloc", "")])


def _tabla(cabeceras: list[str], filas: list[list], vacio: str) -> str:
    if not filas:
        return f'<p class="vacio">{html.escape(vacio)}</p>'
    th = "".join(f"<th>{html.escape(c)}</th>" for c in cabeceras)
    tr = "".join("<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in f) + "</tr>" for f in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def escribir_html(datos: dict, carpeta: Path) -> None:
    p, m = datos["puerta"], datos["metricas"]
    estado = p.get("status", "NONE")
    alcance = ", ".join(f"{k}: {v}" for k, v in datos["alcance"].items()) or "rama principal"
    tarjetas = "".join(
        f'<div class="tarjeta"><span>{html.escape(NOMBRES[k])}</span><strong>{html.escape(_valor(k, m.get(k)))}</strong></div>'
        for k in ("bugs", "vulnerabilities", "code_smells", "security_hotspots", "coverage", "duplicated_lines_density",
                  "ncloc", "reliability_rating", "security_rating", "sqale_rating")
    )
    condiciones = _tabla(
        ["Métrica", "Valor", "Condición", "Umbral", "Resultado"],
        [[NOMBRES.get(c["metricKey"], c["metricKey"]), _valor(c["metricKey"], c.get("actualValue")),
          {"LT": "menor que", "GT": "mayor que"}.get(c.get("comparator"), c.get("comparator", "")),
          c.get("errorThreshold", ""), ESTADO_PUERTA.get(c.get("status"), c.get("status"))] for c in p.get("conditions", [])],
        "La puerta de calidad no tiene condiciones para este alcance.")
    orden = {"BLOCKER": 0, "CRITICAL": 1, "MAJOR": 2, "MINOR": 3, "INFO": 4}
    issues = sorted(datos["issues"], key=lambda i: (orden.get(i.get("severity"), 9), i.get("type", "")))
    t_issues = _tabla(["Tipo", "Severidad", "Archivo", "Línea", "Mensaje"],
                      [[i.get("type"), i.get("severity"), _ruta(i.get("component", "")), i.get("line", ""), i.get("message")]
                       for i in issues], "Sin issues abiertos.")
    t_hot = _tabla(["Probabilidad", "Categoría", "Estado", "Archivo", "Línea", "Mensaje"],
                   [[h.get("vulnerabilityProbability"), h.get("securityCategory"), h.get("status"),
                     _ruta(h.get("component", "")), h.get("line", ""), h.get("message")] for h in datos["hotspots"]],
                   "Sin security hotspots.")
    cob = []
    for a in datos["archivos"]:
        mm = {x["metric"]: x.get("value") for x in a.get("measures", [])}
        if "coverage" in mm:
            cob.append([a.get("path", a.get("name")), f"{mm['coverage']} %", mm.get("uncovered_lines", "")])
    cob.sort(key=lambda f: float(f[1].split()[0]))
    t_cob = _tabla(["Archivo", "Cobertura", "Líneas sin cubrir"], cob, "Sin datos de cobertura.")
    por_tipo = {}
    for i in datos["issues"]:
        por_tipo[i.get("type", "OTRO")] = por_tipo.get(i.get("type", "OTRO"), 0) + 1
    resumen_issues = " · ".join(f"{k}: {v}" for k, v in sorted(por_tipo.items())) or "ninguno"
    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reporte SonarQube Cloud · {html.escape(datos['nombre'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; color: #131316; margin: 32px auto; max-width: 1100px; padding: 0 16px; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; }} h2 {{ font-size: 18px; margin: 32px 0 8px; }}
  .meta {{ color: #5e5f6e; font-size: 14px; }}
  .puerta {{ display: inline-block; margin-top: 12px; padding: 6px 14px; border-radius: 999px; font-weight: 600; }}
  .OK {{ background: #e6f3ec; color: #00552e; }} .ERROR {{ background: #fbebea; color: #962620; }}
  .WARN, .NONE {{ background: #f2f2f4; color: #43444f; }}
  .tarjetas {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px; }}
  .tarjeta {{ border: 1px solid #d9d9de; border-radius: 10px; padding: 12px; }}
  .tarjeta span {{ display: block; font-size: 12px; color: #5e5f6e; }} .tarjeta strong {{ font-size: 22px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e4e4e8; vertical-align: top; }}
  th {{ font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #747686; }}
  .vacio {{ color: #5e5f6e; }}
  @media print {{ body {{ margin: 0; }} h2 {{ break-after: avoid; }} tr {{ break-inside: avoid; }} }}
</style></head><body>
<h1>Reporte de SonarQube Cloud</h1>
<p class="meta">Proyecto <strong>{html.escape(datos['nombre'])}</strong> ({html.escape(datos['proyecto'])}) ·
Alcance: {html.escape(alcance)} · Generado: {html.escape(datos['generado'])}</p>
<span class="puerta {html.escape(estado)}">Puerta de calidad: {html.escape(ESTADO_PUERTA.get(estado, estado))}</span>
<h2>Métricas</h2><div class="tarjetas">{tarjetas}</div>
<h2>Condiciones de la puerta de calidad</h2>{condiciones}
<h2>Issues abiertos ({len(datos['issues'])})</h2><p class="meta">{html.escape(resumen_issues)}</p>{t_issues}
<h2>Security hotspots ({len(datos['hotspots'])})</h2>{t_hot}
<h2>Cobertura por archivo</h2>{t_cob}
</body></html>
"""
    (carpeta / "reporte.html").write_text(doc, encoding="utf-8")


def ruta_segura(ruta: Path | str, base: Path | None = None) -> Path:
    """Devuelve la ruta resuelta solo si queda dentro de `base` (por defecto, la carpeta actual).

    Evita path traversal: rechaza `..`, rutas absolutas fuera del proyecto y enlaces simbólicos que escapen.
    """
    raiz = (base or Path.cwd()).resolve()
    destino = (raiz / Path(ruta)).resolve()
    if destino != raiz and raiz not in destino.parents:
        raise ErrorSonar(f"Ruta no permitida: {ruta}. Debe estar dentro de {raiz}.")
    return destino


def generar(cliente: Cliente, carpeta: Path | str, base: Path | None = None) -> dict:
    carpeta = ruta_segura(carpeta, base)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = recolectar(cliente)
    (carpeta / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_csv(datos, carpeta)
    escribir_html(datos, carpeta)
    return datos


def resumen_markdown(datos: dict) -> str:
    """Resumen corto en Markdown (para el resumen de la ejecución en GitHub Actions)."""
    m, estado = datos["metricas"], datos["puerta"].get("status", "NONE")
    filas = [f"| {NOMBRES[k]} | {_valor(k, m.get(k))} |" for k in
             ("bugs", "vulnerabilities", "code_smells", "security_hotspots", "coverage", "duplicated_lines_density")]
    return "\n".join([f"**Puerta de calidad:** {ESTADO_PUERTA.get(estado, estado)}", "", "| Métrica | Valor |",
                      "|---|---|", *filas, "", f"Issues abiertos: {len(datos['issues'])} · Hotspots: {len(datos['hotspots'])}"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reporte de SonarQube Cloud en HTML, CSV y JSON")
    ap.add_argument("--proyecto", default=os.environ.get("SONAR_PROJECT_KEY", ""))
    ap.add_argument("--rama", help="rama a reportar (por defecto, la principal)")
    ap.add_argument("--pr", help="número de pull request a reportar")
    ap.add_argument("--salida", type=Path, default=Path("reporte_sonarqube"))
    ap.add_argument("--resumen", type=Path, help="imprime en Markdown el resumen de un datos.json ya generado")
    a = ap.parse_args(argv)
    if a.resumen:
        try:
            archivo = ruta_segura(a.resumen)
        except ErrorSonar as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        print(resumen_markdown(json.loads(archivo.read_text(encoding="utf-8"))))
        return 0
    token = os.environ.get("SONAR_TOKEN", "")
    if not a.proyecto:
        print("Falta la clave del proyecto: usa --proyecto o la variable SONAR_PROJECT_KEY.", file=sys.stderr)
        return 2
    if not token:
        print("Aviso: sin SONAR_TOKEN solo funciona con proyectos públicos.", file=sys.stderr)
    try:
        d = generar(Cliente(token, a.proyecto, a.rama, a.pr), a.salida)  # valida el host https
    except ErrorSonar as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    estado = d["puerta"].get("status", "NONE")
    print(f"Reporte en {a.salida}/reporte.html · puerta de calidad: {ESTADO_PUERTA.get(estado, estado)} · "
          f"{len(d['issues'])} issues · {len(d['hotspots'])} hotspots · cobertura {d['metricas'].get('coverage', '—')} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
