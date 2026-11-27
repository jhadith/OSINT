"""Persistencia SQLite de fuentes, patrones y decisiones (T4/S5, informe 14.4)."""
import json
import sqlite3

from motor import agendamiento, config
from motor.hbvf import almacen
from tests import generador_citas as gc

CASO = {
    "case_id": "AG-TEST01",
    "status": "Revisión prioritaria",
    "risk_score": 20,
    "review_required": True,
    "recommendations": [{"id": "revision", "texto": "Revisión conjunta del SOC y el área de agendamiento."}],
    "dataset_origin": "prueba.csv",
}


def _conexion(ruta):
    conn = almacen.abrir(ruta)
    almacen.crear_esquema(conn)
    return conn


def test_crea_sus_tablas(tmp_path):
    conn = _conexion(tmp_path / "hbvf.sqlite3")
    try:
        tablas = {f[0] for f in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"fuentes", "patrones", "decisiones"} <= tablas
    finally:
        conn.close()


def test_registra_una_decision(tmp_path):
    conn = _conexion(tmp_path / "hbvf.sqlite3")
    try:
        almacen.guardar_decisiones(conn, [CASO])
        conn.commit()
        fila = conn.execute(
            "SELECT case_id, status, risk_score, review_required, dataset_origin FROM decisiones"
        ).fetchone()
        assert fila == ("AG-TEST01", "Revisión prioritaria", 20, 1, "prueba.csv")
        guardadas = json.loads(conn.execute("SELECT recommendations FROM decisiones").fetchone()[0])
        assert guardadas == CASO["recommendations"]
    finally:
        conn.close()


def test_analizar_persiste_fuente_patrones_y_decisiones(tmp_path_factory):
    base = tmp_path_factory.mktemp("hbvf")
    ruta = gc.generar(base / "citas.csv")
    db = base / "hbvf.sqlite3"
    salida = agendamiento.analizar(
        ruta, config.REDES, {agendamiento.referencia_contacto("SIM-TRAMITE-02")}, ruta_db=db
    )
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM fuentes").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM patrones").fetchone()[0] == 7
        assert {r[0] for r in conn.execute("SELECT id FROM patrones")} == {f"HG-0{i}" for i in range(1, 8)}
        assert conn.execute("SELECT COUNT(*) FROM decisiones").fetchone()[0] == len(salida["casos"])
        assert conn.execute("SELECT COUNT(*) FROM fuentes WHERE filas > 0 AND length(sha256) = 64").fetchone()[0] == 1
    finally:
        conn.close()
