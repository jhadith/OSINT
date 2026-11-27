"""Pruebas del resumen de GitHub Actions: lectura del JSON y permisos del endpoint."""
import json
from pathlib import Path

import pytest
from app import ci, config
from fastapi.testclient import TestClient


@pytest.fixture
def rutas(tmp_path, monkeypatch):
    raiz = tmp_path / "proyecto"
    dist = raiz / "web" / "dist"
    public = raiz / "web" / "public"
    dist.mkdir(parents=True)
    public.mkdir(parents=True)
    monkeypatch.setattr(config, "WEB_DIST", dist)
    monkeypatch.setattr(config, "PROYECTO", raiz)
    return dist, public


def escribir(ruta: Path, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def resumen(**extra):
    base = {"generado": "2026-11-27T06:00:00Z", "ejecucion": "42", "rama": "main",
            "commit": "abc1234", "origen": "github-actions"}
    base.update(extra)
    return base


def test_prefiere_la_web_compilada_y_sanea_los_checks(rutas):
    dist, public = rutas
    escribir(public / ci.ARCHIVO, resumen(checks=[{"id": "otro", "nombre": "Otro", "resultado": "success"}]))
    escribir(dist / ci.ARCHIVO, resumen(checks=[
        {"id": "secretos", "nombre": "Gitleaks", "resultado": "success", "detalle": "limpio"},
        {"id": "python", "nombre": "pytest", "resultado": "failure", "detalle": "x" * 250},
        {"id": "web", "nombre": "Vitest", "resultado": "cancelled"},
        {"id": "dast", "nombre": "ZAP", "resultado": "skipped"},
        {"id": "raro", "nombre": "Desconocido", "resultado": "otro"},
        "esto no es un check",
        {"id": "largo", "resultado": "success"},
    ]))
    d = ci.estado()
    assert d["disponible"] is True
    assert d["estado"] == "fallido"
    assert d["origen"] == "github-actions"
    assert [c["resultado"] for c in d["checks"]] == ["success", "failure", "cancelled", "skipped", "skipped", "success"]
    assert d["checks"][0]["detalle"] == "limpio"
    assert len(d["checks"][1]["detalle"]) == 200
    assert d["checks"][-1]["nombre"] == ""


def test_usa_el_json_de_origen_si_no_esta_en_dist(rutas):
    _, public = rutas
    escribir(public / ci.ARCHIVO, resumen(checks=[{"id": "lint", "nombre": "Lint", "resultado": "success"}]))
    d = ci.estado()
    assert d["disponible"] is True
    assert d["estado"] == "correcto"
    assert d["checks"][0]["id"] == "lint"


def test_sin_archivo_devuelve_estado_vacio(rutas):
    d = ci.estado()
    assert d == {"disponible": False, "generado": "", "ejecucion": "", "rama": "", "commit": "",
                 "origen": "", "estado": "sin_datos", "checks": []}


@pytest.mark.parametrize("contenido", ["{mal", "[]"])
def test_archivo_no_legible_devuelve_estado_vacio(rutas, contenido):
    _, public = rutas
    (public / ci.ARCHIVO).write_text(contenido, encoding="utf-8")
    assert ci.estado()["disponible"] is False


def test_checks_omitidos_dan_estado_parcial(rutas):
    _, public = rutas
    escribir(public / ci.ARCHIVO, resumen(checks=[{"id": "sonarqube", "resultado": "skipped"}]))
    assert ci.estado()["estado"] == "parcial"


def test_sin_checks_da_estado_sin_datos(rutas):
    _, public = rutas
    escribir(public / ci.ARCHIVO, resumen(checks=[]))
    d = ci.estado()
    assert d["disponible"] is True
    assert d["estado"] == "sin_datos"


def test_endpoint_solo_para_ti(rutas, tmp_path, monkeypatch):
    _, public = rutas
    escribir(public / ci.ARCHIVO, resumen(checks=[{"id": "python", "nombre": "pytest", "resultado": "success"}]))
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path / "estado"))
    from app.main import app

    cli = TestClient(app)
    assert cli.get("/api/ci/estado").status_code == 401

    def token_de(usuario):
        return cli.post("/api/acceso/ingresar", json={"usuario": usuario, "clave": "demo2026"}).json()["token"]

    ti = token_de("ti")
    r = cli.get("/api/ci/estado", headers={"Authorization": f"Bearer {ti}"})
    assert r.status_code == 200
    assert r.json()["checks"][0]["id"] == "python"

    # El analista tiene el permiso "tecnico", pero no "ver_ci": no debe ver este panel.
    for usuario in ("analista", "salud", "jefe"):
        r = cli.get("/api/ci/estado", headers={"Authorization": f"Bearer {token_de(usuario)}"})
        assert r.status_code == 403
