"""Copia el estado de SQLite (estado/sentinel.db y estado/listas.sqlite3) a PostgreSQL.

Uso, desde backend/ y con el entorno activado:
    set SENTINEL_DB_URL=postgresql://postgres:clave@localhost:5432/sentinel
    python -m app.migrar_postgres

Conserva el orden de la bitácora y de cada registro. Si PostgreSQL ya tiene datos, no copia nada
(para no duplicar); con --forzar copia igual lo que falte.
"""
from __future__ import annotations

import sqlite3
import sys

from . import almacen, bd, config, listas

TABLAS = {
    "sentinel.db": (almacen.ESQUEMA_PG, ["alertas", "registros", "bitacora", "decisiones", "usuarios", "analisis",
                                         "archivos_json"]),
    "listas.sqlite3": (listas.ESQUEMA_PG, ["indicadores", "solicitudes", "auditoria", "meta"]),
}
AUTO = {"registros": "seq", "bitacora": "seq", "decisiones": "id", "indicadores": "id", "solicitudes": "id",
        "auditoria": "seq"}


def migrar(forzar: bool = False) -> dict[str, int]:
    url = bd.url_pg()
    if not url:
        raise SystemExit("Falta SENTINEL_DB_URL=postgresql://usuario:clave@host:5432/base")
    import psycopg
    copiadas: dict[str, int] = {}
    with psycopg.connect(url) as pg:
        for archivo, (esquema, tablas) in TABLAS.items():
            origen = config.estado() / archivo
            if not origen.exists():
                continue
            with pg.cursor() as c:
                c.execute(esquema)
            src = sqlite3.connect(origen)
            src.row_factory = sqlite3.Row
            for t in tablas:
                try:
                    filas = src.execute(f"SELECT * FROM {t}").fetchall()  # nosec B608 - nombres de tabla fijos
                except sqlite3.OperationalError:
                    continue
                with pg.cursor() as c:
                    c.execute(f"SELECT COUNT(*) FROM {t}")  # nosec B608
                    if c.fetchone()[0] and not forzar:
                        copiadas[t] = 0
                        continue
                    for f in filas:
                        cols = list(f.keys())
                        c.execute(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "  # nosec B608
                                  "ON CONFLICT DO NOTHING", tuple(f))
                    if t in AUTO and filas:
                        c.execute(f"SELECT setval(pg_get_serial_sequence('{t}', '{AUTO[t]}'), "  # nosec B608
                                  f"COALESCE((SELECT MAX({AUTO[t]}) FROM {t}), 1))")
                copiadas[t] = len(filas)
            src.close()
        pg.commit()
    return copiadas


if __name__ == "__main__":
    r = migrar("--forzar" in sys.argv)
    print("Copiado a PostgreSQL:", ", ".join(f"{t}: {n}" for t, n in r.items()) or "nada (no hay datos en SQLite)")
