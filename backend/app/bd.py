"""Conexión a la base de datos: PostgreSQL si está configurado, SQLite como respaldo.

- Con SENTINEL_DB_URL=postgresql://usuario:clave@host:5432/sentinel el estado vive en PostgreSQL.
- Sin esa variable, o si PostgreSQL no responde, se usa el archivo SQLite de siempre (la demo no se cae).

El resto del código sigue escribiendo SQL al estilo sqlite3 (marcadores «?», INSERT OR IGNORE,
INSERT OR REPLACE); este módulo lo traduce a PostgreSQL y entrega filas que se leen por posición o
por nombre, igual que sqlite3.Row.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

_log = logging.getLogger("sentinel.bd")
_lock = threading.Lock()
_pg_caido_hasta = 0.0
_esquemas_pg: set[str] = set()
ULTIMO_MOTOR = {"motor": "sqlite", "detalle": "SENTINEL_DB_URL no configurado"}


def url_pg() -> str:
    return os.environ.get("SENTINEL_DB_URL", "").strip()


class Fila(tuple):
    """Fila que se lee por posición (fila[0]) o por nombre (fila["id"]), como sqlite3.Row."""

    def __new__(cls, nombres, valores):
        f = super().__new__(cls, valores)
        f._nombres = nombres
        return f

    def __getitem__(self, k):
        if isinstance(k, str):
            return tuple.__getitem__(self, self._nombres.index(k))
        return tuple.__getitem__(self, k)

    def keys(self):
        return list(self._nombres)


def _fabrica_filas(cursor):
    nombres = [c.name for c in cursor.description] if cursor.description else []
    return lambda valores: Fila(nombres, valores)


# Tablas con clave autoincremental: el INSERT devuelve esa columna para lastrowid.
CLAVES = {"registros": "seq", "bitacora": "seq", "decisiones": "id", "indicadores": "id", "solicitudes": "id",
          "auditoria": "seq"}
# INSERT OR REPLACE: columna que define el conflicto en cada tabla.
REEMPLAZO = {"meta": "clave", "archivos_json": "nombre", "analisis": "id", "usuarios": "usuario"}


def traducir(sql: str) -> str:
    s = sql.strip().rstrip(";")
    m = re.match(r"INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO\s+(\w+)\s*\(([^)]*)\)", s, re.I)
    if m:
        modo, tabla, cols = m.group(1).upper(), m.group(2), [c.strip() for c in m.group(3).split(",")]
        s = re.sub(r"INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO", "INSERT INTO", s, count=1, flags=re.I)
        if modo == "IGNORE":
            s += " ON CONFLICT DO NOTHING"
        else:
            clave = REEMPLAZO.get(tabla, cols[0])
            otros = [c for c in cols if c != clave]
            s += f" ON CONFLICT ({clave}) DO UPDATE SET " + ", ".join(  # nosec B608 - columnas del propio código
                f"{c} = EXCLUDED.{c}" for c in otros)
    m = re.match(r"INSERT\s+INTO\s+(\w+)", s, re.I)
    if m and m.group(1) in CLAVES and "RETURNING" not in s.upper():
        s += f" RETURNING {CLAVES[m.group(1)]}"
    return s.replace("?", "%s")


class _Cursor:
    def __init__(self, cur, lastrowid=None):
        self._cur, self.lastrowid = cur, lastrowid
        self.rowcount = cur.rowcount

    def fetchone(self):
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur.description else []

    def __iter__(self):
        return iter(self.fetchall())


class ConexionPG:
    """Subconjunto de la interfaz de sqlite3.Connection que usa la consola."""

    motor = "postgresql"

    def __init__(self, conn):
        self._c = conn

    def execute(self, sql: str, params=()):
        cur = self._c.cursor(row_factory=_fabrica_filas)
        q = traducir(sql)
        cur.execute(q, tuple(params) if params else None)
        lastrowid = None
        if "RETURNING" in q.upper() and cur.description:
            filas = cur.fetchall()
            lastrowid = filas[0][0] if filas else None
            envoltura = _Cursor(cur, lastrowid)
            envoltura.rowcount = len(filas)
            return envoltura
        return _Cursor(cur, lastrowid)

    def executescript(self, script: str):
        with self._c.cursor() as cur:
            cur.execute(script)

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        self._c.close()


def esquema_pg_para(ruta_sqlite: Path) -> str:
    """Esquema de PostgreSQL: «public» para la carpeta de estado normal; uno propio por carpeta si
    SENTINEL_ESTADO apunta a otra (pruebas, análisis aislados), para que nunca se mezclen."""
    if os.environ.get("SENTINEL_DB_SCHEMA"):
        return re.sub(r"\W", "_", os.environ["SENTINEL_DB_SCHEMA"])
    if not os.environ.get("SENTINEL_ESTADO"):
        return "public"
    import hashlib
    return "st_" + hashlib.sha1(str(ruta_sqlite.parent.resolve()).encode(), usedforsecurity=False).hexdigest()[:12]


def conectar(ruta_sqlite: Path, esquema_sqlite: str, esquema_pg: str | None, nombre: str):
    """Devuelve una conexión a PostgreSQL (si SENTINEL_DB_URL está y responde) o a SQLite."""
    global _pg_caido_hasta
    url = url_pg()
    if url and esquema_pg is not None and time.time() >= _pg_caido_hasta:
        try:
            import psycopg
            conn = psycopg.connect(url, connect_timeout=3)
            db = ConexionPG(conn)
            sch = esquema_pg_para(ruta_sqlite)
            if sch != "public":
                db.executescript(f'CREATE SCHEMA IF NOT EXISTS "{sch}"; SET search_path TO "{sch}"')
            with _lock:
                if (nombre, sch) not in _esquemas_pg:
                    db.executescript(esquema_pg)
                    db.commit()
                    _esquemas_pg.add((nombre, sch))
            ULTIMO_MOTOR.update(motor="postgresql", detalle=re.sub(r"//[^@]*@", "//***@", url))
            return db
        except Exception as e:  # PostgreSQL caído o mal configurado: respaldo en SQLite
            _pg_caido_hasta = time.time() + 30
            ULTIMO_MOTOR.update(motor="sqlite", detalle=f"PostgreSQL no disponible ({type(e).__name__}); respaldo SQLite")
            _log.warning("PostgreSQL no disponible, se usa SQLite: %s", e)
    ruta_sqlite.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ruta_sqlite, timeout=5)
    db.row_factory = sqlite3.Row
    db.executescript(esquema_sqlite)
    db.commit()
    if not url:
        ULTIMO_MOTOR.update(motor="sqlite", detalle="SENTINEL_DB_URL no configurado")
    return db


_FUNCION_SOLO_AGREGAR = """CREATE OR REPLACE FUNCTION sentinel_solo_agregar() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% append-only: no se permite modificar ni borrar', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;"""
_TRIGGER = """DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'TABLA_solo_agregar' AND tgrelid = 'TABLA'::regclass) THEN
        CREATE TRIGGER TABLA_solo_agregar BEFORE UPDATE OR DELETE ON TABLA
        FOR EACH ROW EXECUTE FUNCTION sentinel_solo_agregar();
    END IF;
END $$;"""


def solo_agregar_pg(tablas: list[str]) -> str:
    """DDL de PostgreSQL que impide UPDATE y DELETE en las tablas dadas (control de repudio)."""
    return "\n".join([_FUNCION_SOLO_AGREGAR] + [_TRIGGER.replace("TABLA", t) for t in tablas if t.isidentifier()])
