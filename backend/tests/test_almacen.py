"""Persistencia SQLite de la consola (S4): ciclo de vida de alertas, bitácora append-only y migración idempotente.

Correr desde backend/:  pytest -q
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from app import almacen, migrar_estado

RAIZ = Path(__file__).resolve().parents[2]          # sentinel/
ESTADO_REAL = RAIZ / "backend" / "estado"



@pytest.fixture(autouse=True)
def _solo_sqlite(monkeypatch):
    """Estas pruebas revisan el archivo SQLite por dentro: siempre corren sobre SQLite."""
    monkeypatch.delenv("SENTINEL_DB_URL", raising=False)

@pytest.fixture()
def db(tmp_path):
    return almacen.abrir(tmp_path / "sentinel.db")


def _volcado(ruta: Path) -> dict:
    """Todo el contenido de la base, en orden, para comparar dos ejecuciones de la migración."""
    c = sqlite3.connect(ruta)
    c.row_factory = sqlite3.Row
    tablas = [f[0] for f in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    out = {t: [tuple(f) for f in c.execute(f'SELECT * FROM "{t}" ORDER BY 1')] for t in tablas}
    c.close()
    return out


def _estado_fixture(base: Path) -> Path:
    """Carpeta estado/ con los tipos de archivo que migra: bitacora, telegram, analisis y usuarios."""
    c = base / "estado"
    (c / "analisis" / "AN-TEST-0001").mkdir(parents=True)
    (c / "bitacora.jsonl").write_text(
        '{"id": "B-00001", "fecha": "2026-01-05T08:00:00", "actor": "ana", "rol": "SOC", '
        '"accion": "Ingreso a la consola", "objetivo": "consola", "detalle": "Sesión de 8 horas"}\n'
        '{"id": "B-00002", "fecha": "2026-01-05T08:05:00", "actor": "ana", "rol": "SOC", '
        '"accion": "Caso confirmado", "objetivo": "C3", "detalle": "Coincide con el registro de accesos"}\n',
        encoding="utf-8")
    (c / "telegram.jsonl").write_text(
        '{"clave": "AN-TEST-0001:C3", "enviada": false, "fecha": "2026-01-05T08:06:00", "modo": "simulación"}\n',
        encoding="utf-8")
    (c / "analisis.jsonl").write_text(
        '{"id": "AN-TEST-0001", "estado": "listo", "autor": "ana"}\n', encoding="utf-8")
    (c / "usuarios.json").write_text(json.dumps(
        {"analista": {"nombre": "Ana", "rol": "analista", "sal": "aa", "hash": "bb"}}, ensure_ascii=False),
        encoding="utf-8")
    (c / "analisis" / "AN-TEST-0001" / "meta.json").write_text(
        json.dumps({"id": "AN-TEST-0001", "estado": "listo", "autor": "ana"}), encoding="utf-8")
    return c


# ---------- ciclo de vida de alertas ----------

def test_transiciones_validas_del_ciclo_de_vida(db):
    almacen.crear_alerta(db, "AL-1", caso_id="C3", titulo="Posible fuga de datos")
    assert almacen.obtener_alerta(db, "AL-1")["estado"] == "nueva"

    primera = almacen.registrar_decision(db, "AL-1", "confirmada", "ana", "Coincide con el registro de accesos")
    assert almacen.obtener_alerta(db, "AL-1")["estado"] == "confirmada"

    segunda = almacen.registrar_decision(db, "AL-1", "contenida", "ti", "Cuenta comprometida bloqueada")
    assert almacen.obtener_alerta(db, "AL-1")["estado"] == "contenida"
    assert segunda > primera

    almacen.crear_alerta(db, "AL-2", caso_id="C4", titulo="Cuenta fantasma")
    almacen.registrar_decision(db, "AL-2", "descartada", "ana", "Actividad autorizada por jefatura")
    assert almacen.obtener_alerta(db, "AL-2")["estado"] == "descartada"

    # la traza queda en decisiones (append-only) y en la bitácora, en orden
    filas = [tuple(f) for f in db.execute(
        "SELECT alerta_id, estado_anterior, estado_nuevo, usuario, motivo FROM decisiones ORDER BY id")]
    assert filas == [
        ("AL-1", "nueva", "confirmada", "ana", "Coincide con el registro de accesos"),
        ("AL-1", "confirmada", "contenida", "ti", "Cuenta comprometida bloqueada"),
        ("AL-2", "nueva", "descartada", "ana", "Actividad autorizada por jefatura"),
    ]
    acciones = [f["accion"] for f in db.execute("SELECT accion FROM bitacora ORDER BY seq")]
    assert acciones == ["Decisión de ciclo de vida"] * 3
    assert [a["id"] for a in almacen.listar_alertas(db, estado="contenida")] == ["AL-1"]


def test_transicion_invalida_rechaza_salto_directo_y_motivo_vacio(db):
    almacen.crear_alerta(db, "AL-9", caso_id="C1", titulo="Fuerza bruta")

    with pytest.raises(ValueError) as falla:
        almacen.registrar_decision(db, "AL-9", "contenida", "ana", "Se bloqueó el origen del ataque")
    assert "nueva -> contenida" in str(falla.value)

    with pytest.raises(ValueError) as falla:
        almacen.registrar_decision(db, "AL-9", "confirmada", "ana", "   ")
    assert "motivo" in str(falla.value).lower()

    with pytest.raises(ValueError) as falla:
        almacen.registrar_decision(db, "AL-9", "confirmada", "ana", None)
    assert "motivo" in str(falla.value).lower()

    with pytest.raises(ValueError) as falla:
        almacen.registrar_decision(db, "NO-EXISTE", "confirmada", "ana", "Motivo suficiente para la prueba")
    assert "desconocida" in str(falla.value)

    # nada de lo rechazado tocó la base: sigue en nueva, sin decisiones y sin eventos nuevos
    assert almacen.obtener_alerta(db, "AL-9")["estado"] == "nueva"
    assert db.execute("SELECT COUNT(*) FROM decisiones").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM bitacora").fetchone()[0] == 0

    # descartada es terminal: no admite más transiciones
    almacen.crear_alerta(db, "AL-10", caso_id="C2", titulo="Escaneo de servicios")
    almacen.registrar_decision(db, "AL-10", "descartada", "ana", "Actividad autorizada por jefatura")
    with pytest.raises(ValueError) as falla:
        almacen.registrar_decision(db, "AL-10", "confirmada", "ana", "Motivo suficiente para la prueba")
    assert "terminal" in str(falla.value)
    assert almacen.obtener_alerta(db, "AL-10")["estado"] == "descartada"
    assert db.execute("SELECT COUNT(*) FROM decisiones").fetchone()[0] == 1


def test_bitacora_y_decisiones_son_solo_append(db):
    almacen.crear_alerta(db, "AL-1", caso_id="C3", titulo="Posible fuga de datos")
    almacen.registrar_decision(db, "AL-1", "confirmada", "ana", "Coincide con el registro de accesos")
    almacen.registrar_evento(db, "ana", "SOC", "Análisis iniciado", "AN-TEST-0001", "con datos de ejemplo")
    almacen.agregar_registro(db, "decisiones", {"clave": "AN-TEST-0001:C3", "estado": "confirmado"})

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE bitacora SET accion = 'editado' WHERE seq = 1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM bitacora WHERE seq = 1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE decisiones SET motivo = 'editado' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM decisiones WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE registros SET datos = '{}' WHERE seq = 1")

    # las líneas siguen intactas y el orden de lectura es el de inserción
    assert [b["accion"] for b in almacen.leer_bitacora(db)] == ["Decisión de ciclo de vida", "Análisis iniciado"]
    assert db.execute("SELECT motivo FROM decisiones WHERE id = 1").fetchone()[0] == "Coincide con el registro de accesos"
    assert [d["estado"] for d in almacen.leer_registros(db, "decisiones")] == ["confirmado"]


# ---------- migración JSONL/JSON -> SQLite ----------

def test_migracion_carga_bitacora_telegram_analisis_y_usuarios(tmp_path):
    carpeta = _estado_fixture(tmp_path)
    originales = {f.relative_to(carpeta): f.read_bytes() for f in migrar_estado.archivos_datos(carpeta)}

    insertadas = migrar_estado.migrar(carpeta)

    assert insertadas == {"bitacora": 2, "telegram": 1, "analisis": 2, "usuarios": 1}

    # los originales quedaron intactos (solo se leyeron)
    assert {f.relative_to(carpeta): f.read_bytes() for f in migrar_estado.archivos_datos(carpeta)} == originales

    # copia de seguridad previa, con todos los archivos, antes de escribir la base
    respaldo = carpeta / migrar_estado.RESPALDO
    assert respaldo.is_dir()
    for rel, contenido in originales.items():
        assert (respaldo / rel).read_bytes() == contenido

    c = sqlite3.connect(carpeta / "sentinel.db")
    c.row_factory = sqlite3.Row
    assert [b["id"] for b in almacen.leer_bitacora(c)] == ["B-00001", "B-00002"]
    assert [r["clave"] for r in almacen.leer_registros(c, "telegram")] == ["AN-TEST-0001:C3"]
    assert [a["estado"] for a in almacen.leer_registros(c, "analisis")] == ["listo"]
    assert tuple(c.execute("SELECT usuario, nombre, rol, sal, hash FROM usuarios").fetchone()) == \
        ("analista", "Ana", "analista", "aa", "bb")
    assert tuple(c.execute("SELECT id FROM analisis").fetchone()) == ("AN-TEST-0001",)
    c.close()


def test_migracion_es_idempotente_correr_dos_veces(tmp_path):
    carpeta = _estado_fixture(tmp_path)

    primera = migrar_estado.migrar(carpeta)
    assert sum(primera.values()) > 0
    volcado_1 = _volcado(carpeta / "sentinel.db")

    segunda = migrar_estado.migrar(carpeta)
    volcado_2 = _volcado(carpeta / "sentinel.db")

    assert all(v == 0 for v in segunda.values()), segunda   # la segunda no vuelve a insertar
    assert volcado_1 == volcado_2                           # mismo resultado, sin pérdida
    assert volcado_1["bitacora"] and volcado_1["registros"] and volcado_1["usuarios"] and volcado_1["analisis"]


def test_respaldo_previo_se_hace_una_sola_vez(tmp_path):
    carpeta = _estado_fixture(tmp_path)
    migrar_estado.migrar(carpeta)
    respaldo = carpeta / migrar_estado.RESPALDO / "telegram.jsonl"
    antes = respaldo.read_bytes()

    # la app anterior siguió escribiendo el JSONL después del primer respaldo
    with open(carpeta / "telegram.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"clave": "AN-TEST-0001:C4", "enviada": False,
                            "fecha": "2026-01-05T09:00:00", "modo": "simulación"}, ensure_ascii=False) + "\n")

    insertadas = migrar_estado.migrar(carpeta)

    assert respaldo.read_bytes() == antes                  # una sola vez: el respaldo no se rehace
    assert insertadas["telegram"] == 1                     # la línea nueva sí se migra (sin pérdida)
    c = sqlite3.connect(carpeta / "sentinel.db")
    assert c.execute("SELECT COUNT(*) FROM registros WHERE nombre = 'telegram'").fetchone()[0] == 2
    c.close()


def test_migracion_desde_los_jsonl_reales_del_estado(tmp_path):
    fuentes = migrar_estado.archivos_datos(ESTADO_REAL)
    if not fuentes:
        pytest.skip("backend/estado/ no contiene datos en esta copia de trabajo")
    destino = tmp_path / "estado"
    destino.mkdir()
    for f in fuentes:
        copia = destino / f.relative_to(ESTADO_REAL)
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, copia)
    originales = {f.relative_to(ESTADO_REAL): f.read_bytes() for f in fuentes}

    migrar_estado.migrar(destino)
    primera = _volcado(destino / "sentinel.db")
    migrar_estado.migrar(destino)
    segunda = _volcado(destino / "sentinel.db")

    assert primera == segunda
    # los archivos reales de backend/estado/ solo se leyeron: siguen byte a byte iguales
    assert {f.relative_to(ESTADO_REAL): f.read_bytes() for f in fuentes} == originales
    assert (destino / migrar_estado.RESPALDO).is_dir()
    real_bitacora = ESTADO_REAL / "bitacora.jsonl"
    if real_bitacora.exists():
        lineas = [l for l in real_bitacora.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(primera["bitacora"]) == len(lineas)      # la bitácora existente se conservó entera
