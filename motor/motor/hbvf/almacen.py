"""Persistencia SQLite de fuentes, patrones y decisiones del módulo HBVF (informe 14.4).

SQLite almacena fuentes, patrones y decisiones. La ruta de la base es inyectable para
que las pruebas usen directorios temporales fuera del repositorio. Solo sqlite3 de la
biblioteca estándar: sin dependencias nuevas. Este módulo solo agrega bitácora de
revisión humana: nunca modifica citas ni expone acciones automáticas (S10).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ESQUEMA = """
CREATE TABLE IF NOT EXISTS fuentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta TEXT NOT NULL,
    tipo TEXT NOT NULL,
    filas INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patrones (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    familia TEXT NOT NULL,
    fuente TEXT,
    contenido TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    review_required INTEGER NOT NULL,
    recommendations TEXT NOT NULL,
    dataset_origin TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
"""


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def hash_archivo(ruta: Path | str) -> str:
    """SHA-256 del archivo fuente (trazabilidad del dataset ingerido)."""
    digest = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(65536), b""):
            digest.update(bloque)
    return digest.hexdigest()


def abrir(ruta_db: Path | str) -> sqlite3.Connection:
    """Abre (creando si hace falta) la base en la ruta inyectada."""
    ruta = Path(ruta_db)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(ruta)


def crear_esquema(conn: sqlite3.Connection) -> None:
    """Crea las tablas fuentes, patrones y decisiones si no existen (idempotente)."""
    conn.executescript(ESQUEMA)


def guardar_fuente(conn: sqlite3.Connection, *, ruta: Path | str, tipo: str, filas: int, sha256: str) -> None:
    """Registra el dataset ingerido con su hash para trazabilidad."""
    conn.execute(
        "INSERT INTO fuentes (ruta, tipo, filas, sha256, creado_en) VALUES (?, ?, ?, ?, ?)",
        (str(ruta), tipo, int(filas), sha256, _ahora()),
    )


def guardar_patrones(conn: sqlite3.Connection, catalogo: dict[str, Any]) -> None:
    """Persiste el catálogo completo (un patrón por fila, contenido en JSON)."""
    for patron in catalogo["patrones"]:
        conn.execute(
            "INSERT OR REPLACE INTO patrones (id, nombre, familia, fuente, contenido, creado_en) VALUES (?, ?, ?, ?, ?, ?)",
            (patron["id"], patron["nombre"], patron["familia"], patron.get("fuente"),
             json.dumps(patron, ensure_ascii=False, sort_keys=True), _ahora()),
        )


def guardar_decisiones(conn: sqlite3.Connection, casos: list[dict[str, Any]]) -> None:
    """Una fila de decisión por caso (ciclo de vida para revisión humana; no ejecuta nada)."""
    conn.executemany(
        "INSERT OR REPLACE INTO decisiones "
        "(case_id, status, risk_score, review_required, recommendations, dataset_origin, creado_en) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(caso["case_id"], caso["status"], int(caso["risk_score"]), 1 if caso["review_required"] else 0,
          json.dumps(caso["recommendations"], ensure_ascii=False), caso["dataset_origin"], _ahora())
         for caso in casos],
    )
