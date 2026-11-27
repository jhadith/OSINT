"""Persistencia SQLite de la consola (S4): alertas con ciclo de vida, decisiones y bitácora solo-append.

Esquema inspirado en el diseño del proyecto Hackaton (storage/esquema.py), adaptado a los campos de
Sentinel Salud y ejecado con sqlite3 puro (sin dependencias nuevas):

- registros:   los streams que antes eran JSONL (decisiones, telegram, denuncias, ...), solo-append.
- bitacora:    registro de auditoría solo-append (triggers que abortan UPDATE y DELETE).
- alertas:     una fila por alerta, con el estado del ciclo de vida
               nueva -> confirmada | descartada -> contenida (descartada y contenida son terminales).
- estados:     grafo de transiciones permitidas; la validación vive en registrar_decision.
- decisiones:  cada decisión de ciclo de vida (quién, motivo, transición), solo-append.
- usuarios:    espejo de estado/usuarios.json, cargado por la migración.
- analisis:    espejo de estado/analisis/<id>/meta.json, cargado por la migración.
- archivos_json: cualquier otro archivo JSON superior de estado/, como respaldo.

La plataforma nunca cambia un estado por su cuenta: registrar_decision valida la transición contra
la tabla estados y exige motivo no vacío antes de tocar la base. La ruta de la base es siempre
inyectable para que las pruebas usen tmp_path y nunca escriban el default del repositorio.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from . import bd

ESQUEMA = """
CREATE TABLE IF NOT EXISTS registros (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    migrado_ord INTEGER,
    datos TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS registros_migrado
    ON registros (nombre, migrado_ord) WHERE migrado_ord IS NOT NULL;

CREATE TABLE IF NOT EXISTS bitacora (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    migrado_origen TEXT,
    migrado_ord INTEGER,
    id TEXT NOT NULL,
    fecha TEXT NOT NULL,
    actor TEXT NOT NULL,
    rol TEXT NOT NULL,
    accion TEXT NOT NULL,
    objetivo TEXT NOT NULL,
    detalle TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS bitacora_migrado
    ON bitacora (migrado_origen, migrado_ord) WHERE migrado_ord IS NOT NULL;

CREATE TABLE IF NOT EXISTS alertas (
    id TEXT PRIMARY KEY,
    caso_id TEXT NOT NULL,
    titulo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'nueva',
    creada TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estados (
    desde TEXT NOT NULL,
    hasta TEXT NOT NULL,
    PRIMARY KEY (desde, hasta)
);
INSERT OR IGNORE INTO estados (desde, hasta) VALUES
    ('nueva', 'confirmada'),
    ('nueva', 'descartada'),
    ('confirmada', 'contenida');

CREATE TABLE IF NOT EXISTS decisiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alerta_id TEXT NOT NULL REFERENCES alertas(id),
    estado_anterior TEXT NOT NULL,
    estado_nuevo TEXT NOT NULL,
    usuario TEXT NOT NULL,
    motivo TEXT NOT NULL,
    fecha TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    usuario TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL,
    sal TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analisis (
    id TEXT PRIMARY KEY,
    datos TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS archivos_json (
    nombre TEXT PRIMARY KEY,
    datos TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS bitacora_sin_update BEFORE UPDATE ON bitacora
BEGIN
    SELECT RAISE(ABORT, 'bitacora append-only: no se permite actualizar');
END;

CREATE TRIGGER IF NOT EXISTS bitacora_sin_delete BEFORE DELETE ON bitacora
BEGIN
    SELECT RAISE(ABORT, 'bitacora append-only: no se permite borrar');
END;

CREATE TRIGGER IF NOT EXISTS decisiones_sin_update BEFORE UPDATE ON decisiones
BEGIN
    SELECT RAISE(ABORT, 'decisiones append-only: no se permite actualizar');
END;

CREATE TRIGGER IF NOT EXISTS decisiones_sin_delete BEFORE DELETE ON decisiones
BEGIN
    SELECT RAISE(ABORT, 'decisiones append-only: no se permite borrar');
END;

CREATE TRIGGER IF NOT EXISTS registros_sin_update BEFORE UPDATE ON registros
BEGIN
    SELECT RAISE(ABORT, 'registros append-only: no se permite actualizar');
END;

CREATE TRIGGER IF NOT EXISTS registros_sin_delete BEFORE DELETE ON registros
BEGIN
    SELECT RAISE(ABORT, 'registros append-only: no se permite borrar');
END;
"""

# Mismo esquema en PostgreSQL (se usa cuando SENTINEL_DB_URL está configurado; ver app/bd.py).
_TABLAS_PG = """
CREATE TABLE IF NOT EXISTS registros (
    seq BIGSERIAL PRIMARY KEY, nombre TEXT NOT NULL, migrado_ord INTEGER, datos TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS registros_migrado ON registros (nombre, migrado_ord) WHERE migrado_ord IS NOT NULL;
CREATE INDEX IF NOT EXISTS registros_nombre ON registros (nombre, seq);
CREATE TABLE IF NOT EXISTS bitacora (
    seq BIGSERIAL PRIMARY KEY, migrado_origen TEXT, migrado_ord INTEGER, id TEXT NOT NULL, fecha TEXT NOT NULL,
    actor TEXT NOT NULL, rol TEXT NOT NULL, accion TEXT NOT NULL, objetivo TEXT NOT NULL, detalle TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS bitacora_migrado ON bitacora (migrado_origen, migrado_ord) WHERE migrado_ord IS NOT NULL;
CREATE TABLE IF NOT EXISTS alertas (
    id TEXT PRIMARY KEY, caso_id TEXT NOT NULL, titulo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'nueva',
    creada TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS estados (desde TEXT NOT NULL, hasta TEXT NOT NULL, PRIMARY KEY (desde, hasta));
INSERT INTO estados (desde, hasta) VALUES ('nueva', 'confirmada'), ('nueva', 'descartada'),
    ('confirmada', 'contenida') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS decisiones (
    id BIGSERIAL PRIMARY KEY, alerta_id TEXT NOT NULL REFERENCES alertas(id), estado_anterior TEXT NOT NULL,
    estado_nuevo TEXT NOT NULL, usuario TEXT NOT NULL, motivo TEXT NOT NULL, fecha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usuarios (
    usuario TEXT PRIMARY KEY, nombre TEXT NOT NULL, rol TEXT NOT NULL, sal TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analisis (id TEXT PRIMARY KEY, datos TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS archivos_json (nombre TEXT PRIMARY KEY, datos TEXT NOT NULL);
"""
ESQUEMA_PG = "\n".join([_TABLAS_PG, bd.solo_agregar_pg(["bitacora", "decisiones", "registros"])])

COLUMNAS_BITACORA = ("id", "fecha", "actor", "rol", "accion", "objetivo", "detalle")
_lock = threading.Lock()
_inicializadas: set[str] = set()


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def abrir(ruta: Path | str) -> sqlite3.Connection:
    """Abre (creando si hace falta) la base en `ruta` y garantiza el esquema. Idempotente.

    La base principal de la consola (sentinel.db) va a PostgreSQL si SENTINEL_DB_URL está configurado.
    """
    destino = Path(ruta)
    if destino.name == "sentinel.db" and bd.url_pg():
        db = bd.conectar(destino, ESQUEMA, ESQUEMA_PG, "almacen")
        if not isinstance(db, sqlite3.Connection):
            return db
    destino.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(destino, timeout=5)
    db.row_factory = sqlite3.Row
    with _lock:
        if str(destino) not in _inicializadas:
            db.executescript(ESQUEMA)
            db.commit()
            _inicializadas.add(str(destino))
    return db


@contextmanager
def abriendo(ruta: Path | str):
    """Conexión que se cierra sola (para lecturas y escrituras puntuales de un solo hilo)."""
    db = abrir(ruta)
    try:
        yield db
    finally:
        db.close()


# ---------- streams (los que antes eran JSONL) ----------

def agregar_registro(db: sqlite3.Connection, nombre: str, registro: dict, *,
                    migrado_ord: int | None = None, ignorar: bool = False) -> bool:
    """Agrega una línea al stream `nombre` (solo-append). Con `ignorar` la línea ya migrada no se
    vuelve a insertar: esa es la idempotencia de la migración. Devuelve True si se insertó."""
    sql = "INSERT OR IGNORE" if ignorar else "INSERT"
    cur = db.execute(f"{sql} INTO registros (nombre, migrado_ord, datos) VALUES (?, ?, ?)",
                     (nombre, migrado_ord, json.dumps(registro, ensure_ascii=False)))
    db.commit()
    return cur.rowcount > 0


def leer_registros(db: sqlite3.Connection, nombre: str) -> list[dict]:
    """Líneas del stream en orden de inserción (el orden de lectura del JSONL original)."""
    filas = db.execute("SELECT datos FROM registros WHERE nombre = ? ORDER BY seq", (nombre,))
    return [json.loads(f["datos"]) for f in filas]


# ---------- bitácora (append-only) ----------

def agregar_bitacora(db: sqlite3.Connection, registro: dict, *, migrado_origen: str | None = None,
                    migrado_ord: int | None = None, ignorar: bool = False) -> bool:
    """Agrega una línea a la bitácora; los triggers prohiben actualizarla o borrarla."""
    valores = [registro.get(c) if registro.get(c) is not None else "" for c in COLUMNAS_BITACORA]
    sql = "INSERT OR IGNORE" if ignorar else "INSERT"
    cur = db.execute(
        f"{sql} INTO bitacora (migrado_origen, migrado_ord, {', '.join(COLUMNAS_BITACORA)}) "
        f"VALUES (?, ?, {', '.join('?' * len(COLUMNAS_BITACORA))})",
        (migrado_origen, migrado_ord, *valores))
    db.commit()
    return cur.rowcount > 0


def leer_bitacora(db: sqlite3.Connection) -> list[dict]:
    """Todas las líneas de la bitácora en orden de inserción, con los campos del JSONL original."""
    # B608 es falso positivo: el SQL solo une COLUMNAS_BITACORA, tupla literal de constantes del módulo.
    filas = db.execute(f"SELECT {', '.join(COLUMNAS_BITACORA)} FROM bitacora ORDER BY seq")  # nosec B608
    return [dict(f) for f in filas]


def _siguiente_id_bitacora(db: sqlite3.Connection) -> str:
    n = db.execute("SELECT COUNT(*) FROM bitacora").fetchone()[0] + 1
    return f"B-{n:05d}"


def registrar_evento(db: sqlite3.Connection, actor: str, rol: str, accion: str,
                     objetivo: str, detalle: str) -> dict:
    """Agrega una línea a la bitácora con el id correlativo B-##### (el mismo invariant de siempre:
    el contador parte de las líneas ya migradas)."""
    reg = {"id": _siguiente_id_bitacora(db), "fecha": ahora(), "actor": actor, "rol": rol,
           "accion": accion, "objetivo": objetivo, "detalle": detalle}
    agregar_bitacora(db, reg)
    return reg


# ---------- ciclo de vida de alertas ----------

def crear_alerta(db: sqlite3.Connection, alerta_id: str, caso_id: str, titulo: str,
                 creada: str | None = None) -> dict:
    """Crea la alerta en estado `nueva`; solo registrar_decision la mueve de ahí."""
    db.execute("INSERT INTO alertas (id, caso_id, titulo, estado, creada) VALUES (?, ?, ?, 'nueva', ?)",
               (alerta_id, caso_id, titulo, creada or ahora()))
    db.commit()
    return obtener_alerta(db, alerta_id)


def obtener_alerta(db: sqlite3.Connection, alerta_id: str) -> dict[str, Any] | None:
    fila = db.execute("SELECT * FROM alertas WHERE id = ?", (alerta_id,)).fetchone()
    return None if fila is None else dict(fila)


def listar_alertas(db: sqlite3.Connection, estado: str | None = None) -> list[dict[str, Any]]:
    if estado is None:
        filas = db.execute("SELECT * FROM alertas ORDER BY id")
    else:
        filas = db.execute("SELECT * FROM alertas WHERE estado = ? ORDER BY id", (estado,))
    return [dict(f) for f in filas]


def registrar_decision(db: sqlite3.Connection, alerta_id: str, nuevo_estado: str,
                       usuario: str, motivo: str) -> int:
    """Registra una decisión de ciclo de vida: valida, actualiza y audita.

    Solo las transiciones permitidas por la tabla estados (la plataforma no actúa por su cuenta),
    motivo no vacío, y deja fila en decisiones y evento en bitácora — las tres tablas son
    append-only. Si algo falta, lanza ValueError sin tocar la base. Devuelve el id de la decisión.
    """
    if not str(motivo or "").strip():
        raise ValueError("motivo vacío: toda decisión de ciclo de vida debe justificarse")
    fila = db.execute("SELECT estado FROM alertas WHERE id = ?", (alerta_id,)).fetchone()
    if fila is None:
        raise ValueError(f"alerta desconocida: {alerta_id}")
    desde = fila["estado"]
    permitida = db.execute("SELECT 1 FROM estados WHERE desde = ? AND hasta = ?",
                           (desde, nuevo_estado)).fetchone()
    if permitida is None:
        salidas = [r["hasta"] for r in db.execute(
            "SELECT hasta FROM estados WHERE desde = ? ORDER BY hasta", (desde,))]
        detalle = f"desde {desde}: {', '.join(salidas)}" if salidas else f"{desde} es estado terminal"
        raise ValueError(f"transición no permitida: {desde} -> {nuevo_estado} ({detalle})")
    db.execute("UPDATE alertas SET estado = ? WHERE id = ?", (nuevo_estado, alerta_id))
    cur = db.execute(
        "INSERT INTO decisiones (alerta_id, estado_anterior, estado_nuevo, usuario, motivo, fecha) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (alerta_id, desde, nuevo_estado, str(usuario), str(motivo).strip(), ahora()))
    registrar_evento(db, str(usuario), "Ciclo de vida", "Decisión de ciclo de vida", alerta_id,
                     json.dumps({"de": desde, "a": nuevo_estado, "motivo": str(motivo).strip()},
                                ensure_ascii=False))
    db.commit()
    return int(cur.lastrowid)
