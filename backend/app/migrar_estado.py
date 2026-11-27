"""Migración de estado/ (JSONL/JSON de solo agregar) a estado/sentinel.db (SQLite).

Uso (desde backend/):   ../.venv/bin/python -m app.migrar_estado

- Antes de escribir en la base, copia los archivos de datos a estado/respaldo-antes-de-migrar/
  (una sola vez; si no hay datos no se crea el respaldo).
- Los originales quedan intactos: la migración solo los lee, nunca los borra ni los reescribe.
- Idempotente: correrla dos veces deja la base en el mismo estado, sin duplicar ni perder filas
  (cada línea migrada guarda la ordinal de su archivo de origen y la segunda pasada la ignora).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import almacen, config

RESPALDO = "respaldo-antes-de-migrar"


def archivos_datos(carpeta: Path) -> list[Path]:
    """Archivos de estado que migra: *.jsonl y *.json de la raíz + analisis/<id>/meta.json."""
    raiz = sorted([*carpeta.glob("*.jsonl"), *carpeta.glob("*.json")])
    analisis = sorted((carpeta / "analisis").glob("*/meta.json")) if (carpeta / "analisis").exists() else []
    return raiz + analisis


def respaldar(carpeta: Path) -> Path | None:
    """Copia previa de los datos a <carpeta>/respaldo-antes-de-migrar/, una sola vez."""
    destino = carpeta / RESPALDO
    if destino.exists():
        return None
    fuentes = archivos_datos(carpeta)
    if not fuentes:
        return None
    for f in fuentes:
        rel = f.relative_to(carpeta)
        (destino / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, destino / rel)
    return destino


def migrar(carpeta: Path | None = None, db_ruta: Path | None = None) -> dict[str, int]:
    """Migra los JSONL/JSON de `carpeta` a su base SQLite. Devuelve cuántas filas insertó por fuente."""
    origen = Path(carpeta) if carpeta else config.estado()
    respaldar(origen)                                    # copia de seguridad previa, antes de escribir
    destino = Path(db_ruta) if db_ruta else origen / "sentinel.db"
    db = almacen.abrir(destino)
    insertadas: dict[str, int] = {}

    for f in sorted(origen.glob("*.jsonl")):
        n = 0
        for ordinal, linea in enumerate(f.read_text(encoding="utf-8").splitlines()):
            if not linea.strip():
                continue
            reg = json.loads(linea)
            if f.stem == "bitacora":
                ok = almacen.agregar_bitacora(db, reg, migrado_origen=f.name, migrado_ord=ordinal, ignorar=True)
            else:
                ok = almacen.agregar_registro(db, f.stem, reg, migrado_ord=ordinal, ignorar=True)
            n += int(ok)
        insertadas[f.stem] = insertadas.get(f.stem, 0) + n

    usuarios = origen / "usuarios.json"
    if usuarios.exists():
        n = 0
        datos = json.loads(usuarios.read_text(encoding="utf-8"))
        for usuario, u in datos.items():
            cur = db.execute("INSERT OR IGNORE INTO usuarios (usuario, nombre, rol, sal, hash) VALUES (?, ?, ?, ?, ?)",
                             (usuario, u.get("nombre", ""), u.get("rol", ""), u.get("sal", ""), u.get("hash", "")))
            n += int(cur.rowcount)
        db.commit()
        insertadas["usuarios"] = insertadas.get("usuarios", 0) + n

    for f in sorted(origen.glob("*.json")):               # cualquier otro JSON superior (usuarios ya cargado)
        if f.name == "usuarios.json":
            continue
        cur = db.execute("INSERT OR IGNORE INTO archivos_json (nombre, datos) VALUES (?, ?)",
                         (f.name, f.read_text(encoding="utf-8")))
        db.commit()
        insertadas[f.stem] = insertadas.get(f.stem, 0) + int(cur.rowcount)

    carpeta_an = origen / "analisis"
    if carpeta_an.exists():
        n = 0
        for m in sorted(carpeta_an.glob("*/meta.json")):
            cur = db.execute("INSERT OR IGNORE INTO analisis (id, datos) VALUES (?, ?)",
                             (m.parent.name, m.read_text(encoding="utf-8")))
            n += int(cur.rowcount)
        db.commit()
        insertadas["analisis"] = insertadas.get("analisis", 0) + n

    db.close()
    return insertadas


def main() -> None:
    origen = config.estado()
    insertadas = migrar(origen)
    resumen = ", ".join(f"{k}={v}" for k, v in sorted(insertadas.items())) or "sin datos que migrar"
    print(f"Migración a {origen / 'sentinel.db'}: {resumen}.")
    print(f"Originales intactos en {origen}; respaldo previo en {origen / RESPALDO} (si había datos).")


if __name__ == "__main__":
    main()
