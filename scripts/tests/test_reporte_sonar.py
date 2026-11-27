"""Pruebas del generador de reportes de SonarQube Cloud con la API simulada (sin red ni token)."""
import csv
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "reporte_sonar.py"
spec = importlib.util.spec_from_file_location("reporte_sonar", RUTA)
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

RESPUESTAS = {
    "/api/qualitygates/project_status": {"projectStatus": {"status": "ERROR", "conditions": [
        {"status": "ERROR", "metricKey": "new_coverage", "comparator": "LT", "errorThreshold": "80", "actualValue": "71.5"},
        {"status": "OK", "metricKey": "new_security_rating", "comparator": "GT", "errorThreshold": "1", "actualValue": "1"},
    ]}},
    "/api/measures/component": {"component": {"name": "Sentinel Salud", "measures": [
        {"metric": "coverage", "value": "97.1"}, {"metric": "bugs", "value": "0"},
        {"metric": "security_rating", "value": "1.0"}, {"metric": "new_coverage", "period": {"value": "71.5"}},
    ]}},
    "/api/issues/search": {"paging": {"total": 2}, "issues": [
        {"type": "VULNERABILITY", "severity": "MAJOR", "rule": "githubactions:S7637", "line": 61,
         "component": "jhadith_osit:.github/workflows/devsecops.yml", "message": "Use full commit SHA <hash>"},
        {"type": "CODE_SMELL", "severity": "MINOR", "rule": "python:S1481", "line": 3,
         "component": "jhadith_osit:backend/app/main.py", "message": "Remove the unused local variable"},
    ]},
    "/api/hotspots/search": {"paging": {"total": 1}, "hotspots": [
        {"securityCategory": "others", "vulnerabilityProbability": "LOW", "status": "TO_REVIEW", "line": 87,
         "component": "jhadith_osit:.github/workflows/devsecops.yml", "message": "Omitting --ignore-scripts", "ruleKey": "x"},
    ]},
    "/api/measures/component_tree": {"paging": {"total": 1}, "components": [
        {"path": "backend/app/main.py", "measures": [{"metric": "coverage", "value": "98.0"},
                                                     {"metric": "uncovered_lines", "value": "6"}]},
    ]},
}


class ClienteFalso(rs.Cliente):
    def __init__(self, *a, **k):
        super().__init__("token-secreto", "jhadith_osit", *a, **k)
        self.llamadas = []

    def get(self, ruta, **params):
        self.llamadas.append((ruta, params))
        return RESPUESTAS[ruta]


def test_genera_html_csv_y_json(tmp_path):
    datos = rs.generar(ClienteFalso(rama="dev"), tmp_path)
    assert datos["metricas"]["new_coverage"] == "71.5"           # las métricas de código nuevo vienen en "period"
    html = (tmp_path / "reporte.html").read_text(encoding="utf-8")
    assert "No aprobada" in html and "Sentinel Salud" in html and "branch: dev" in html
    assert "&lt;hash&gt;" in html                                   # el texto de SonarQube se escapa
    assert "token-secreto" not in html and "token-secreto" not in (tmp_path / "datos.json").read_text()
    with open(tmp_path / "issues.csv", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert filas[0]["archivo"] == ".github/workflows/devsecops.yml" and filas[0]["linea"] == "61"
    assert (tmp_path / "hotspots.csv").read_text().count("\n") == 2
    assert "backend/app/main.py,98.0,6" in (tmp_path / "cobertura.csv").read_text()


def test_alcance_por_pull_request():
    c = ClienteFalso(pr="27")
    assert c.alcance == {"pullRequest": "27"}


def test_notas_y_valores():
    assert rs._valor("security_rating", "1.0") == "A"
    assert rs._valor("security_rating", "5") == "E"
    assert rs._valor("coverage", None) == "—"


def test_resumen_markdown(tmp_path):
    rs.generar(ClienteFalso(), tmp_path)
    texto = rs.resumen_markdown(json.loads((tmp_path / "datos.json").read_text()))
    assert "**Puerta de calidad:** No aprobada" in texto and "| Cobertura (%) | 97.1 |" in texto


def test_paginacion_recorre_todas_las_paginas():
    class Paginado(rs.Cliente):
        def get(self, ruta, **params):
            p = params["p"]
            return {"paging": {"total": 3}, "issues": [{"n": p}] if p <= 3 else []}
    c = Paginado("", "x")
    assert [i["n"] for i in c.paginas("/api/issues/search", "issues")] == [1, 2, 3]


def test_error_http_se_explica(monkeypatch):
    def falla(*a, **k):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    monkeypatch.setattr(rs.urllib.request, "urlopen", falla)
    with pytest.raises(rs.ErrorSonar, match="403"):
        rs.Cliente("t", "x").get("/api/issues/search")


def test_main_sin_proyecto_y_con_resumen(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SONAR_PROJECT_KEY", raising=False)
    assert rs.main(["--salida", str(tmp_path)]) == 2
    rs.generar(ClienteFalso(), tmp_path)
    assert rs.main(["--resumen", str(tmp_path / "datos.json")]) == 0
    assert "Puerta de calidad" in capsys.readouterr().out


def test_solo_acepta_https():
    with pytest.raises(rs.ErrorSonar, match="https"):
        rs.Cliente("t", "x", host="file:///etc/passwd")
