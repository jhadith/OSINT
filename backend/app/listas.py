"""Repositorio DINÁMICO de listas blancas y negras (S15/T17a).

La fuente de verdad es `estado/listas.sqlite3` (sqlite3 puro, mismo patrón que app.almacen,
sin SQLAlchemy): el SOC añade, quita y resuelve solicitudes desde la interfaz y el cambio se ve
SIN reiniciar el servidor. `fijos/listas.json` solo siembra la base la primera vez que está
vacía; después queda ignorado como fuente (nunca se vuelve a leer para decidir clasificaciones).

La caché en memoria se reconstruye en CADA escritura, no al importar: `listas()` sirve la
instantánea vigente y las altas/bajas de `añadir`, `quitar` y `resolver` la refrescan.

API pública:
    listas()                -> {"blanca": [...], "negra": [...]}  (valores activos normalizados)
    listar()                -> indicadores activos [{id, tipo, valor, etiqueta, activo}]
    añadir(tipo, valor, etiqueta="", quien="SOC")
    quitar(id, quien="SOC")
    solicitar(tipo, valor, justificacion, fuente="", quien="SOC")
    solicitudes(estado_solicitud=None)
    resolver(id, aprobar, motivo, quien)   # PENDIENTE -> APROBADA | RECHAZADA, siempre con motivo

Cada cambio deja evento en `estado.bitacora` (gestión de listas, rol TI). Si la bitácora no
está disponible sin romper la operación, el cambio no se pierde y queda en la tabla
`auditoria` propia de esta base.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path

from . import bd, config, estado

_log = logging.getLogger(__name__)

TIPOS_LISTA = ("blanca", "negra")
ESTADOS_SOLICITUD = ("PENDIENTE", "APROBADA", "RECHAZADA")
_ALIASES_TIPO = {"blanca": "blanca", "blancas": "blanca", "negra": "negra", "negras": "negra"}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS indicadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    valor_normalizado TEXT NOT NULL,
    etiqueta TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL,
    UNIQUE (tipo, valor_normalizado)
);
CREATE TABLE IF NOT EXISTS solicitudes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    valor TEXT NOT NULL,
    justificacion TEXT NOT NULL,
    fuente TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
    resolucion TEXT NOT NULL DEFAULT '',
    creado_en TEXT NOT NULL,
    resuelto_en TEXT,
    resuelto_por TEXT,
    CHECK (estado IN ('PENDIENTE', 'APROBADA', 'RECHAZADA'))
);
CREATE TABLE IF NOT EXISTS auditoria (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    actor TEXT NOT NULL,
    accion TEXT NOT NULL,
    objetivo TEXT NOT NULL,
    detalle TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""

_lock = threading.RLock()
_cache: dict[str, list[str]] | None = None
_ruta_cache: Path | None = None


def _ruta() -> Path:
    return config.estado() / "listas.sqlite3"


ESQUEMA_PG = """
CREATE TABLE IF NOT EXISTS indicadores (
    id BIGSERIAL PRIMARY KEY, tipo TEXT NOT NULL, valor_normalizado TEXT NOT NULL, etiqueta TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1, creado_en TEXT NOT NULL, UNIQUE (tipo, valor_normalizado));
CREATE TABLE IF NOT EXISTS solicitudes (
    id BIGSERIAL PRIMARY KEY, tipo TEXT NOT NULL, valor TEXT NOT NULL, justificacion TEXT NOT NULL,
    fuente TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'PENDIENTE', resolucion TEXT NOT NULL DEFAULT '',
    creado_en TEXT NOT NULL, resuelto_en TEXT, resuelto_por TEXT,
    CHECK (estado IN ('PENDIENTE', 'APROBADA', 'RECHAZADA')));
CREATE TABLE IF NOT EXISTS auditoria (
    seq BIGSERIAL PRIMARY KEY, fecha TEXT NOT NULL, actor TEXT NOT NULL, accion TEXT NOT NULL, objetivo TEXT NOT NULL,
    detalle TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
"""


def _conexion() -> sqlite3.Connection:
    ruta = _ruta()
    if bd.url_pg():
        db = bd.conectar(ruta, ESQUEMA, ESQUEMA_PG, "listas")
        if not isinstance(db, sqlite3.Connection):
            return db
    ruta.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ruta, timeout=5)
    db.row_factory = sqlite3.Row
    db.executescript(ESQUEMA)
    db.commit()
    return db


def _normalizar_tipo(tipo) -> str:
    t = str(tipo or "").strip().lower()
    if t not in _ALIASES_TIPO:
        raise ValueError(f"tipo de lista inválido: {tipo!r} (use 'blanca' o 'negra')")
    return _ALIASES_TIPO[t]


def _normalizar_valor(tipo: str, valor) -> str:
    """Minúsculas, sin esquema/consulta/fragmento; la blanca vive en el host, la negra conserva la ruta."""
    v = str(valor or "").strip().lower()
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v)
    v = v.split("#", 1)[0].split("?", 1)[0]
    if tipo == "blanca":
        v = v.split("/", 1)[0]
    v = v.rstrip("/")
    if not v or " " in v:
        raise ValueError(f"valor de indicador inválido: {valor!r}")
    return v


def _sembrar(db: sqlite3.Connection) -> None:
    """Semilla idempotente: solo la primera vez que la base está vacía; después el JSON queda ignorado."""
    if db.execute("SELECT 1 FROM meta WHERE clave = 'semilla'").fetchone():
        return
    if db.execute("SELECT COUNT(*) FROM indicadores").fetchone()[0] == 0:
        try:
            datos = json.loads((config.FIJOS / "listas.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _log.exception("no se pudo leer la semilla fijos/listas.json; la base queda sin sembrar")
            datos = {}
        for tipo in TIPOS_LISTA:
            for valor in datos.get(tipo, []):
                try:
                    normal = _normalizar_valor(tipo, valor)
                except ValueError:
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO indicadores (tipo, valor_normalizado, etiqueta, activo, creado_en) "
                    "VALUES (?, ?, ?, 1, ?)", (tipo, normal, "semilla: fijos/listas.json", estado.ahora()))
    db.execute("INSERT OR REPLACE INTO meta (clave, valor) VALUES ('semilla', ?)", (estado.ahora(),))
    db.commit()


def _reconstruir(db: sqlite3.Connection) -> None:
    """Caché en memoria: se reconstruye en cada escritura (nunca al importar el módulo)."""
    global _cache
    filas = db.execute(
        "SELECT tipo, valor_normalizado FROM indicadores WHERE activo = 1 ORDER BY id").fetchall()
    cache = {"blanca": [], "negra": []}
    for f in filas:
        cache[f["tipo"]].append(f["valor_normalizado"])
    _cache = {k: sorted(v) for k, v in cache.items()}


def _abrir() -> dict[str, list[str]]:
    """(Re)abre la base con la ruta vigente, siembra si hace falta y reconstruye la caché."""
    global _cache, _ruta_cache
    with _lock:
        db = _conexion()
        try:
            _sembrar(db)
            _reconstruir(db)
        finally:
            db.close()
        _ruta_cache = _ruta()
        return {"blanca": list(_cache["blanca"]), "negra": list(_cache["negra"])}


def _asegurar() -> None:
    with _lock:
        if _cache is None or _ruta_cache != _ruta():
            _abrir()


def _escribir(operacion):
    """Aplica una escritura, commitea, reconstruye la caché y devuelve el resultado de `operacion`."""
    with _lock:
        _asegurar()
        db = _conexion()
        try:
            resultado = operacion(db)
            db.commit()
            _reconstruir(db)
        finally:
            db.close()
        _ruta_cache = _ruta()
        return resultado


def _auditar(actor, accion, objetivo, detalle) -> None:
    """Evento en estado.bitacora; si esa bitácora no está disponible, en la auditoria propia."""
    try:
        estado.bitacora(str(actor), "TI", accion, str(objetivo), str(detalle))
    except Exception:
        try:
            db = _conexion()
            try:
                db.execute(
                    "INSERT INTO auditoria (fecha, actor, accion, objetivo, detalle) VALUES (?, ?, ?, ?, ?)",
                    (estado.ahora(), str(actor), str(accion), str(objetivo), str(detalle)))
                db.commit()
            finally:
                db.close()
        except Exception:
            _log.exception("no se pudo auditar %s sobre %s", accion, objetivo)


def _indicador_dict(f) -> dict:
    return {"id": f["id"], "tipo": f["tipo"], "valor": f["valor_normalizado"],
            "etiqueta": f["etiqueta"], "activo": f["activo"]}


def _solicitud_dict(f) -> dict:
    return {"id": f["id"], "tipo": f["tipo"], "valor": f["valor"], "justificacion": f["justificacion"],
            "fuente": f["fuente"], "estado": f["estado"], "resolucion": f["resolucion"],
            "creado_en": f["creado_en"], "resuelto_en": f["resuelto_en"], "resuelto_por": f["resuelto_por"]}


# ---------- lectura ----------

def listas() -> dict[str, list[str]]:
    """Instantánea vigente de las listas (la caché se reconstruye en cada escritura)."""
    _asegurar()
    with _lock:
        return {"blanca": list(_cache["blanca"]), "negra": list(_cache["negra"])}


def listar() -> list[dict]:
    """Indicadores activos, en orden de alta."""
    _asegurar()
    db = _conexion()
    try:
        filas = db.execute("SELECT * FROM indicadores WHERE activo = 1 ORDER BY id").fetchall()
    finally:
        db.close()
    return [_indicador_dict(f) for f in filas]


def solicitudes(estado_solicitud: str | None = None) -> list[dict]:
    """Solicitudes, todas o filtradas por PENDIENTE | APROBADA | RECHAZADA."""
    if estado_solicitud is not None:
        estado_solicitud = str(estado_solicitud).upper()
        if estado_solicitud not in ESTADOS_SOLICITUD:
            raise ValueError(f"estado de solicitud inválido: {estado_solicitud!r}")
    _asegurar()
    db = _conexion()
    try:
        if estado_solicitud is None:
            filas = db.execute("SELECT * FROM solicitudes ORDER BY id").fetchall()
        else:
            filas = db.execute("SELECT * FROM solicitudes WHERE estado = ? ORDER BY id",
                               (estado_solicitud,)).fetchall()
    finally:
        db.close()
    return [_solicitud_dict(f) for f in filas]


# ---------- escritura ----------

def añadir(tipo: str, valor: str, etiqueta: str = "", *, quien: str = "SOC") -> dict:
    """Da de alta (o reactive) un indicador y refresca la caché: visible al instante, sin reiniciar."""
    t = _normalizar_tipo(tipo)
    normal = _normalizar_valor(t, valor)
    etiqueta = str(etiqueta or "").strip()

    def _op(db):
        db.execute(
            "INSERT INTO indicadores (tipo, valor_normalizado, etiqueta, activo, creado_en) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT (tipo, valor_normalizado) DO UPDATE SET etiqueta = excluded.etiqueta, activo = 1",
            (t, normal, etiqueta, estado.ahora()))
        fila = db.execute(
            "SELECT * FROM indicadores WHERE tipo = ? AND valor_normalizado = ?", (t, normal)).fetchone()
        return _indicador_dict(fila)

    reg = _escribir(_op)
    _auditar(quien, f"Indicador de lista {t} añadido", reg["valor"], reg["etiqueta"])
    return reg


def quitar(id, *, quien: str = "SOC") -> dict:
    """Baja del indicador (activo = 0): la caché lo deja de servir en el mismo acto."""
    def _op(db):
        fila = db.execute("SELECT * FROM indicadores WHERE id = ?", (id,)).fetchone()
        if fila is None:
            raise ValueError(f"indicador desconocido: {id}")
        if fila["activo"]:
            db.execute("UPDATE indicadores SET activo = 0 WHERE id = ?", (id,))
            return {"id": fila["id"], "tipo": fila["tipo"], "valor": fila["valor_normalizado"],
                    "etiqueta": fila["etiqueta"], "activo": 0}
        return _indicador_dict(fila)

    reg = _escribir(_op)
    _auditar(quien, f"Indicador de lista {reg['tipo']} quitado", reg["valor"], "")
    return reg


def solicitar(tipo: str, valor: str, justificacion: str, fuente: str = "", quien: str = "SOC") -> dict:
    """Pide un indicador: queda PENDIENTE hasta que alguien lo resuelva con motivo."""
    t = _normalizar_tipo(tipo)
    normal = _normalizar_valor(t, valor)
    just = str(justificacion or "").strip()
    if not just:
        raise ValueError("toda solicitud necesita una justificación")

    def _op(db):
        viva = db.execute(
            "SELECT id FROM solicitudes WHERE tipo = ? AND valor = ? AND estado IN ('PENDIENTE', 'APROBADA')",
            (t, normal)).fetchone()
        if viva:
            raise ValueError(f"ya existe una solicitud viva para {normal!r}")
        cur = db.execute(
            "INSERT INTO solicitudes (tipo, valor, justificacion, fuente, estado, resolucion, creado_en) "
            "VALUES (?, ?, ?, ?, 'PENDIENTE', '', ?)",
            (t, normal, just, str(fuente or "").strip(), estado.ahora()))
        fila = db.execute("SELECT * FROM solicitudes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _solicitud_dict(fila)

    reg = _escribir(_op)
    _auditar(quien, "Solicitud de lista nueva", reg["valor"], reg["justificacion"])
    return reg


def resolver(id, aprobar: bool, motivo: str, quien: str) -> dict:
    """PENDIENTE -> APROBADA (y activa el indicador) o RECHAZADA. Siempre con motivo y quién."""
    mot = str(motivo or "").strip()
    if not mot:
        raise ValueError("toda resolución necesita un motivo")
    actor = str(quien or "").strip() or "Sistema"
    nuevo = "APROBADA" if aprobar else "RECHAZADA"

    def _op(db):
        fila = db.execute("SELECT * FROM solicitudes WHERE id = ?", (id,)).fetchone()
        if fila is None:
            raise ValueError(f"solicitud desconocida: {id}")
        if fila["estado"] != "PENDIENTE":
            raise ValueError(f"la solicitud {id} ya fue resuelta ({fila['estado']})")
        cur = db.execute(
            "UPDATE solicitudes SET estado = ?, resolucion = ?, resuelto_en = ?, resuelto_por = ? "
            "WHERE id = ? AND estado = 'PENDIENTE'",
            (nuevo, mot, estado.ahora(), actor, id))
        if cur.rowcount != 1:
            raise ValueError(f"la solicitud {id} ya fue resuelta")
        if aprobar:
            db.execute(
                "INSERT INTO indicadores (tipo, valor_normalizado, etiqueta, activo, creado_en) "
                "VALUES (?, ?, ?, 1, ?) "
                "ON CONFLICT (tipo, valor_normalizado) DO UPDATE SET etiqueta = excluded.etiqueta, activo = 1",
                (fila["tipo"], fila["valor"], f"solicitud #{id}", estado.ahora()))
        return _solicitud_dict(db.execute("SELECT * FROM solicitudes WHERE id = ?", (id,)).fetchone())

    reg = _escribir(_op)
    _auditar(actor, f"Solicitud de lista {nuevo.lower()}", reg["valor"], mot)
    return reg
