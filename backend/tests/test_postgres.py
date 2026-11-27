"""PostgreSQL: las pruebas con base real corren si SENTINEL_TEST_PG_URL (o SENTINEL_DB_URL) apunta a una base
de prueba; el pipeline levanta una como service container. Las demás corren siempre."""
import os
import sqlite3

import pytest
from app import almacen, bd

URL = os.environ.get("SENTINEL_TEST_PG_URL") or os.environ.get("SENTINEL_DB_URL", "")
con_pg = pytest.mark.skipif(not URL.startswith("postgresql"), reason="sin PostgreSQL configurado")


@pytest.fixture
def pg(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DB_URL", URL)
    monkeypatch.setattr(bd, "_pg_caido_hasta", 0.0)
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    db = almacen.abrir(tmp_path / "sentinel.db")
    yield db
    db.close()


@con_pg
def test_usa_postgres_y_no_sqlite(pg):
    assert isinstance(pg, bd.ConexionPG) and bd.ULTIMO_MOTOR["motor"] == "postgresql"


@con_pg
def test_bitacora_solo_agregar_en_postgres(pg):
    import psycopg
    almacen.registrar_evento(pg, "ana", "Analista", "Prueba", "X", "detalle")
    assert almacen.leer_bitacora(pg)[-1]["accion"] == "Prueba"
    with pytest.raises(psycopg.errors.RaiseException):
        pg.execute("DELETE FROM bitacora")
    pg.rollback()
    with pytest.raises(psycopg.errors.RaiseException):
        pg.execute("UPDATE bitacora SET actor = 'otro'")
    pg.rollback()


@con_pg
def test_registros_y_decisiones(pg):
    assert almacen.agregar_registro(pg, "tickets", {"codigo": "TK-1"})
    assert almacen.leer_registros(pg, "tickets") == [{"codigo": "TK-1"}]
    almacen.crear_alerta(pg, "AL-1", caso_id="C1", titulo="Fuerza bruta")
    assert almacen.registrar_decision(pg, "AL-1", "confirmada", "ana", "Motivo suficiente") >= 1
    assert almacen.obtener_alerta(pg, "AL-1")["estado"] == "confirmada"


def test_respaldo_sqlite_si_postgres_no_responde(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DB_URL", "postgresql://nadie@127.0.0.1:1/nada")
    monkeypatch.setattr(bd, "_pg_caido_hasta", 0.0)
    db = almacen.abrir(tmp_path / "sentinel.db")
    assert isinstance(db, sqlite3.Connection) and bd.ULTIMO_MOTOR["motor"] == "sqlite"
    db.close()


def test_traduccion_sql():
    assert bd.traducir("INSERT OR IGNORE INTO estados (desde, hasta) VALUES (?, ?)").endswith("ON CONFLICT DO NOTHING")
    assert "ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor" in bd.traducir(
        "INSERT OR REPLACE INTO meta (clave, valor) VALUES ('semilla', ?)")
    assert bd.traducir("INSERT INTO registros (nombre, datos) VALUES (?, ?)").endswith("RETURNING seq")
