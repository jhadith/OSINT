"""Capa de base de datos (app/bd.py) y migración a PostgreSQL (app/migrar_postgres.py).

Complementa tests/test_postgres.py. Las pruebas con base real necesitan SENTINEL_TEST_PG_URL; en local:
    docker run -d --rm -e POSTGRES_PASSWORD=clave -e POSTGRES_DB=sentinel_test -p 127.0.0.1:55432:5432 postgres:16-alpine
    SENTINEL_TEST_PG_URL=postgresql://postgres:clave@127.0.0.1:55432/sentinel_test pytest -q
"""
import os
import sqlite3
import uuid

import pytest
from app import almacen, bd

PG_URL = os.environ.get("SENTINEL_TEST_PG_URL") or os.environ.get("SENTINEL_DB_URL", "")
con_pg = pytest.mark.skipif(not PG_URL.startswith("postgresql"), reason="sin PostgreSQL configurado")


@pytest.fixture(autouse=True)
def _estado_limpio(monkeypatch):
    monkeypatch.setattr(bd, "_pg_caido_hasta", 0.0)
    monkeypatch.setattr(bd, "_esquemas_pg", set())


# ---------- sin PostgreSQL ----------
@pytest.mark.parametrize(("sqlite", "postgres"), [
    ("INSERT OR REPLACE INTO usuarios (usuario, nombre, rol) VALUES (?, ?, ?);",
     "INSERT INTO usuarios (usuario, nombre, rol) VALUES (%s, %s, %s) ON CONFLICT (usuario) DO UPDATE SET "
     "nombre = EXCLUDED.nombre, rol = EXCLUDED.rol"),
    ("INSERT OR REPLACE INTO otra (k, v) VALUES (?, ?)",
     "INSERT INTO otra (k, v) VALUES (%s, %s) ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v"),
    ("INSERT INTO decisiones (x) VALUES (?) RETURNING id", "INSERT INTO decisiones (x) VALUES (%s) RETURNING id"),
    ("SELECT * FROM alertas WHERE id = ?", "SELECT * FROM alertas WHERE id = %s"),
])
def test_traducir_mas_casos(sqlite, postgres):
    assert bd.traducir(sqlite) == postgres


def test_fila_se_lee_por_posicion_y_por_nombre():
    f = bd.Fila(["id", "titulo"], ("A-1", "Fuga"))
    assert f[0] == "A-1" and f["titulo"] == "Fuga" and f.keys() == ["id", "titulo"]
    assert dict(f) == {"id": "A-1", "titulo": "Fuga"}


def test_esquema_pg_segun_la_carpeta_de_estado(monkeypatch, tmp_path):
    monkeypatch.delenv("SENTINEL_DB_SCHEMA", raising=False)
    monkeypatch.delenv("SENTINEL_ESTADO", raising=False)
    assert bd.esquema_pg_para(tmp_path / "sentinel.db") == "public"
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    sch = bd.esquema_pg_para(tmp_path / "sentinel.db")
    assert sch.startswith("st_") and sch == bd.esquema_pg_para(tmp_path / "otra.db")
    monkeypatch.setenv("SENTINEL_DB_SCHEMA", "mi-esquema; DROP")
    assert bd.esquema_pg_para(tmp_path / "x.db") == "mi_esquema__DROP"          # sin caracteres peligrosos


def test_solo_agregar_ignora_nombres_invalidos():
    ddl = bd.solo_agregar_pg(["bitacora", "x; DROP TABLE y"])
    assert "bitacora_solo_agregar" in ddl and "DROP TABLE y" not in ddl


def test_sin_url_usa_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("SENTINEL_DB_URL", raising=False)
    db = bd.conectar(tmp_path / "a" / "x.db", "CREATE TABLE t (v TEXT);", "CREATE TABLE t (v TEXT);", "prueba")
    assert isinstance(db, sqlite3.Connection)
    assert bd.ULTIMO_MOTOR == {"motor": "sqlite", "detalle": "SENTINEL_DB_URL no configurado"}
    db.close()


def test_postgres_caido_no_se_reintenta_enseguida(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_DB_URL", "postgresql://nadie:clave@127.0.0.1:1/no_existe")
    db = bd.conectar(tmp_path / "x.db", "CREATE TABLE t (v TEXT);", "CREATE TABLE t (v TEXT);", "prueba")
    assert isinstance(db, sqlite3.Connection) and "respaldo SQLite" in bd.ULTIMO_MOTOR["detalle"]
    assert bd._pg_caido_hasta > 0
    db.close()


def test_migrar_sin_url(monkeypatch):
    from app import migrar_postgres
    monkeypatch.delenv("SENTINEL_DB_URL", raising=False)
    with pytest.raises(SystemExit, match="Falta SENTINEL_DB_URL"):
        migrar_postgres.migrar()


# ---------- con PostgreSQL real ----------
@pytest.fixture
def esquema_aislado(monkeypatch, tmp_path):
    """Esquema propio por prueba, que se borra al terminar."""
    import psycopg
    esquema = f"prueba_{uuid.uuid4().hex[:10]}"
    monkeypatch.setenv("SENTINEL_DB_URL", PG_URL)
    monkeypatch.setenv("SENTINEL_DB_SCHEMA", esquema)
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    yield tmp_path, esquema
    with psycopg.connect(PG_URL, autocommit=True) as c:
        c.execute(f'DROP SCHEMA IF EXISTS "{esquema}" CASCADE')


@con_pg
def test_conexion_pg_con_esquema_propio(esquema_aislado):
    tmp, esquema = esquema_aislado
    db = almacen.abrir(tmp / "sentinel.db")
    assert isinstance(db, bd.ConexionPG)
    assert "***@" in bd.ULTIMO_MOTOR["detalle"]                                   # la clave no sale en pantalla
    assert db.execute("SELECT current_schema()").fetchone()[0] == esquema
    db.execute("INSERT OR REPLACE INTO usuarios (usuario, nombre, rol, sal, hash) VALUES (?, ?, ?, ?, ?)",
               ("jefe", "Jefe", "jefe", "s", "h"))
    db.execute("INSERT OR REPLACE INTO usuarios (usuario, nombre, rol, sal, hash) VALUES (?, ?, ?, ?, ?)",
               ("jefe", "Jefe de seguridad", "jefe", "s", "h"))
    assert [f["nombre"] for f in db.execute("SELECT nombre FROM usuarios")] == ["Jefe de seguridad"]
    assert db.execute("UPDATE alertas SET titulo = ? WHERE id = ?", ("x", "nada")).fetchone() is None
    assert db.execute("UPDATE alertas SET titulo = ? WHERE id = ?", ("x", "nada")).fetchall() == []
    assert db.execute("INSERT INTO registros (nombre, datos) VALUES (?, ?)", ("r", "{}")).lastrowid >= 1
    db.commit()
    db.close()
    otra = almacen.abrir(tmp / "sentinel.db")                                     # el esquema ya existe: no se recrea
    assert isinstance(otra, bd.ConexionPG)
    otra.close()


@con_pg
def test_migrar_de_sqlite_a_postgres_sin_duplicar(esquema_aislado, monkeypatch):
    import psycopg
    from app import migrar_postgres
    tmp, esquema = esquema_aislado
    monkeypatch.delenv("SENTINEL_DB_URL")                                         # primero el SQLite de siempre
    db = almacen.abrir(tmp / "sentinel.db")
    almacen.registrar_evento(db, "Analista", "SOC", "Ingreso", "consola", "")
    almacen.agregar_registro(db, "casos", {"id": "C1"})
    db.close()
    monkeypatch.setenv("SENTINEL_DB_URL", PG_URL)
    monkeypatch.setenv("PGOPTIONS", f"-c search_path={esquema}")
    with psycopg.connect(PG_URL, autocommit=True) as c:
        c.execute(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"')
    copiadas = migrar_postgres.migrar()
    assert copiadas["bitacora"] == 1 and copiadas["registros"] == 1
    assert migrar_postgres.migrar()["bitacora"] == 0                              # ya hay datos: no copia
    assert migrar_postgres.migrar(forzar=True)["bitacora"] == 1                   # forzar: ON CONFLICT evita duplicar
    with psycopg.connect(PG_URL) as c:
        assert c.execute(f'SELECT COUNT(*) FROM "{esquema}".bitacora').fetchone()[0] == 1
