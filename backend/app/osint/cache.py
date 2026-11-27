"""Caché OSINT en estado/osint.db (sqlite3 puro, sin dependencias nuevas).

Guarda los ítems normalizados por fuente con su `fetched_at` y su TTL:
- `origen` es el id de la fuente del registro (clave de TTL y de reemplazo); `fuente` es el
  nombre visible que va en cada ítem (CISA, NVD, Exploit-DB…).
- TTL por defecto 6 h; CISA KEV 24 h (TTL_H).
- `guardar()` reemplaza SOLO los ítems de esa fuente: el sync parcial conserva las demás.
- `registrar_fallo()` no toca fetched_at ni los ítems: si una fuente falla, su caché previa
  sigue disponible hasta que venza el TTL y se reintente.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .. import config
from . import recoletores

TTL_DEFECTO_H = 6
TTL_H = {"cisa_kev": 24}          # el catálogo KEV cambia poco: 24 h
_lock = threading.RLock()

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS fuentes (
    origen     TEXT PRIMARY KEY,
    fuente     TEXT NOT NULL DEFAULT '',
    fetched_at TEXT,
    items      INTEGER NOT NULL DEFAULT 0,
    error      TEXT
);
CREATE TABLE IF NOT EXISTS items (
    origen           TEXT NOT NULL,
    fuente           TEXT NOT NULL DEFAULT '',
    tipo             TEXT NOT NULL,
    id_externo       TEXT NOT NULL,
    titulo           TEXT NOT NULL DEFAULT '',
    resumen          TEXT NOT NULL DEFAULT '',
    cvss             REAL,
    kev              INTEGER NOT NULL DEFAULT 0,
    exploit_publico  INTEGER NOT NULL DEFAULT 0,
    enlace           TEXT NOT NULL DEFAULT '',
    fecha            TEXT,
    tags             TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (origen, id_externo)
);
"""


def ruta() -> Path:
    return config.estado() / "osint.db"


@contextmanager
def abriendo():
    ruta().parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ruta(), timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(_ESQUEMA)
        db.commit()
        yield db
    finally:
        db.close()


def ttl_horas(origen: str) -> int:
    return TTL_H.get(origen, TTL_DEFECTO_H)


def fresca(origen: str, ahora: dt.datetime | None = None) -> bool:
    """¿Los datos de esta fuente siguen dentro de su TTL?"""
    ahora = ahora or dt.datetime.now()
    with abriendo() as db:
        fila = db.execute("SELECT fetched_at FROM fuentes WHERE origen = ?", (origen,)).fetchone()
    if not fila or not fila["fetched_at"]:
        return False
    antiguedad = ahora - dt.datetime.fromisoformat(fila["fetched_at"])
    return antiguedad < dt.timedelta(hours=ttl_horas(origen))


def guardar(origen: str, items: list[dict], fetched_at: str) -> None:
    """Reemplaza los ítems de UNA fuente y sella su fetched_at; las demás fuentes no se tocan."""
    nombre = items[0]["fuente"] if items else ""
    with _lock, abriendo() as db:
        db.execute("DELETE FROM items WHERE origen = ?", (origen,))
        db.executemany(
            "INSERT OR REPLACE INTO items (origen, fuente, tipo, id_externo, titulo, resumen, cvss, kev,"
            " exploit_publico, enlace, fecha, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(origen, i["fuente"], i["tipo"], i["id_externo"], i["titulo"], i["resumen"], i["cvss"],
              int(i["kev"]), int(i["exploit_publico"]), i["enlace"], i["fecha"],
              json.dumps(i["tags"], ensure_ascii=False)) for i in items])
        db.execute(
            "INSERT INTO fuentes (origen, fuente, fetched_at, items, error) VALUES (?, ?, ?, ?, NULL)"
            " ON CONFLICT(origen) DO UPDATE SET fuente = excluded.fuente,"
            " fetched_at = excluded.fetched_at, items = excluded.items, error = NULL",
            (origen, nombre, fetched_at, len(items)))
        db.commit()


def registrar_fallo(origen: str, error: str) -> None:
    """Solo anota el error: fetched_at, nombre e ítems previos quedan como estaban."""
    with _lock, abriendo() as db:
        db.execute(
            "INSERT INTO fuentes (origen, fuente, fetched_at, items, error) VALUES (?, '', NULL, 0, ?)"
            " ON CONFLICT(origen) DO UPDATE SET error = excluded.error",
            (origen, error))
        db.commit()


def leer() -> list[dict]:
    """Todos los ítems normalizados de la caché (`fuente` es el nombre visible; tags, lista)."""
    with abriendo() as db:
        filas = db.execute("SELECT * FROM items ORDER BY origen, id_externo").fetchall()
    return [{**{k: fila[k] for k in fila.keys() if k not in ("origen", "tags")},
             "kev": bool(fila["kev"]), "exploit_publico": bool(fila["exploit_publico"]),
             "tags": json.loads(fila["tags"] or "[]")} for fila in filas]


def resumen() -> list[dict]:
    """Estado por fuente: nombre visible, fetched_at, cuántos ítems hay y el último error."""
    nombres = {f["id"]: f["nombre"] for f in recoletores.fuentes()}
    with abriendo() as db:
        filas = db.execute("SELECT origen, fuente, fetched_at, items, error FROM fuentes"
                           " ORDER BY origen").fetchall()
    return [{"fuente": nombres.get(f["origen"], f["fuente"] or f["origen"]), "origen": f["origen"],
             "fetched_at": f["fetched_at"], "items": f["items"], "error": f["error"]} for f in filas]


def sincronizado_en() -> str | None:
    """Último fetched_at de toda la caché (la frescura real de los datos)."""
    with abriendo() as db:
        fila = db.execute("SELECT MAX(fetched_at) AS ts FROM fuentes").fetchone()
    return fila["ts"]
