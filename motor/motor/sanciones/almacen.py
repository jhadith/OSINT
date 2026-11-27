"""Persistencia SQLite de sanciones (T22, S8): ofensas/bloqueos/apelaciones/bitácora.

Esquema tipo Hackaton ``storage/esquema.py`` adaptado a sentinel, con sqlite3
puro (sin dependencias nuevas). Las cuatro tablas son **append-only**: triggers
abortan UPDATE y DELETE; solo se inserta. La ruta de la base es siempre
inyectable para que las pruebas usen tmp_path y nunca escriban el default.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ofensas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    fecha TEXT NOT NULL,
    motivo TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bloqueos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    desde TEXT NOT NULL,
    hasta TEXT NOT NULL,
    nivel INTEGER NOT NULL,
    horas INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS apelaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    fecha TEXT NOT NULL,
    motivo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente'
);

CREATE TABLE IF NOT EXISTS bitacora (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL,
    device_id TEXT,
    detalle TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS ofensas_sin_update BEFORE UPDATE ON ofensas
BEGIN
    SELECT RAISE(ABORT, 'ofensas append-only: no se permite actualizar');
END;
CREATE TRIGGER IF NOT EXISTS ofensas_sin_delete BEFORE DELETE ON ofensas
BEGIN
    SELECT RAISE(ABORT, 'ofensas append-only: no se permite borrar');
END;

CREATE TRIGGER IF NOT EXISTS bloqueos_sin_update BEFORE UPDATE ON bloqueos
BEGIN
    SELECT RAISE(ABORT, 'bloqueos append-only: no se permite actualizar');
END;
CREATE TRIGGER IF NOT EXISTS bloqueos_sin_delete BEFORE DELETE ON bloqueos
BEGIN
    SELECT RAISE(ABORT, 'bloqueos append-only: no se permite borrar');
END;

CREATE TRIGGER IF NOT EXISTS apelaciones_sin_update BEFORE UPDATE ON apelaciones
BEGIN
    SELECT RAISE(ABORT, 'apelaciones append-only: no se permite actualizar');
END;
CREATE TRIGGER IF NOT EXISTS apelaciones_sin_delete BEFORE DELETE ON apelaciones
BEGIN
    SELECT RAISE(ABORT, 'apelaciones append-only: no se permite borrar');
END;

CREATE TRIGGER IF NOT EXISTS bitacora_sin_update BEFORE UPDATE ON bitacora
BEGIN
    SELECT RAISE(ABORT, 'bitacora append-only: no se permite actualizar');
END;
CREATE TRIGGER IF NOT EXISTS bitacora_sin_delete BEFORE DELETE ON bitacora
BEGIN
    SELECT RAISE(ABORT, 'bitacora append-only: no se permite borrar');
END;
"""


def crear_esquema(ruta: Path) -> None:
    """Crea el archivo y el esquema si no existen; idempotente."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ruta)
    try:
        conn.executescript(ESQUEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def abrir(ruta: Path) -> Iterator[sqlite3.Connection]:
    """Conexión efímera por operación (segura entre hilos de FastAPI) con commit."""
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(ESQUEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def insertar_ofensa(conn, device_id: str, fecha: str, motivo: str) -> int:
    cur = conn.execute(
        "INSERT INTO ofensas (device_id, fecha, motivo) VALUES (?, ?, ?)",
        (device_id, fecha, motivo),
    )
    return int(cur.lastrowid)


def ofensas(conn, device_id: str) -> list[dict]:
    filas = conn.execute(
        "SELECT * FROM ofensas WHERE device_id = ? ORDER BY id", (device_id,)
    ).fetchall()
    return [dict(f) for f in filas]


def ofensas_desde(conn, device_id: str, desde: str) -> list[dict]:
    filas = conn.execute(
        "SELECT * FROM ofensas WHERE device_id = ? AND fecha >= ? ORDER BY id",
        (device_id, desde),
    ).fetchall()
    return [dict(f) for f in filas]


def insertar_bloqueo(conn, device_id: str, desde: str, hasta: str,
                     nivel: int, horas: int) -> int:
    cur = conn.execute(
        "INSERT INTO bloqueos (device_id, desde, hasta, nivel, horas) "
        "VALUES (?, ?, ?, ?, ?)",
        (device_id, desde, hasta, nivel, horas),
    )
    return int(cur.lastrowid)


def bloqueos(conn, device_id: str) -> list[dict]:
    filas = conn.execute(
        "SELECT * FROM bloqueos WHERE device_id = ? ORDER BY id", (device_id,)
    ).fetchall()
    return [dict(f) for f in filas]


def bloqueo_activo(conn, device_id: str, ahora: str) -> dict | None:
    """El bloqueo vigente (hasta > ahora), si existe; None si no está bloqueado."""
    fila = conn.execute(
        "SELECT * FROM bloqueos WHERE device_id = ? AND hasta > ? "
        "ORDER BY hasta DESC LIMIT 1",
        (device_id, ahora),
    ).fetchone()
    return dict(fila) if fila else None


def insertar_apelacion(conn, device_id: str, fecha: str, motivo: str) -> dict:
    cur = conn.execute(
        "INSERT INTO apelaciones (device_id, fecha, motivo) VALUES (?, ?, ?)",
        (device_id, fecha, motivo),
    )
    return {
        "id": int(cur.lastrowid),
        "device_id": device_id,
        "fecha": fecha,
        "motivo": motivo,
        "estado": "pendiente",
    }


def apelaciones(conn, device_id: str) -> list[dict]:
    filas = conn.execute(
        "SELECT * FROM apelaciones WHERE device_id = ? ORDER BY id", (device_id,)
    ).fetchall()
    return [dict(f) for f in filas]


def insertar_bitacora(conn, fecha: str, tipo: str, device_id: str | None,
                      detalle: str) -> int:
    cur = conn.execute(
        "INSERT INTO bitacora (fecha, tipo, device_id, detalle) VALUES (?, ?, ?, ?)",
        (fecha, tipo, device_id, detalle),
    )
    return int(cur.lastrowid)


def bitacora(conn, device_id: str | None = None) -> list[dict]:
    if device_id is None:
        filas = conn.execute("SELECT * FROM bitacora ORDER BY id").fetchall()
    else:
        filas = conn.execute(
            "SELECT * FROM bitacora WHERE device_id = ? ORDER BY id", (device_id,)
        ).fetchall()
    return [dict(f) for f in filas]
