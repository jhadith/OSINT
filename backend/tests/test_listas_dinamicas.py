"""Listas dinámicas del SOC (S15/T17a): repositorio SQLite con semilla desde fijos/listas.json,
ediciones en caliente sin reiniciar, solicitudes con motivo y conflicto blanca/negra.

Correr desde backend/:  pytest -q tests/test_listas_dinamicas.py

Ninguna prueba toca el repositorio: la base vive en tmp vía SENTINEL_ESTADO.
"""
from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import pytest

FIJOS = Path(__file__).resolve().parents[1] / "app" / "fijos" / "listas.json"



@pytest.fixture(autouse=True)
def _solo_sqlite(monkeypatch):
    """Estas pruebas revisan el archivo SQLite por dentro: siempre corren sobre SQLite."""
    monkeypatch.delenv("SENTINEL_DB_URL", raising=False)

@pytest.fixture()
def listas(tmp_path, monkeypatch):
    """Módulo con base propia en tmp; el primer acceso siembra desde fijos/listas.json."""
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    from app import listas as m
    m.listas()                      # abre (y siembra si hace falta) con esta base
    return m


# ---------- semilla ----------

def test_semilla_desde_json(listas):
    semilla = json.loads(FIJOS.read_text(encoding="utf-8"))
    datos = listas.listas()
    assert set(semilla["blanca"]) <= set(datos["blanca"]), datos
    assert set(semilla["negra"]) <= set(datos["negra"]), datos
    assert listas.listar(), "la semilla deja indicadores activos"


def test_semilla_idempotente(listas):
    antes, n = listas.listas(), len(listas.listar())
    importlib.reload(listas)        # "reinicio": no duplica ni pierde la semilla
    assert len(listas.listar()) == n and listas.listas() == antes


def test_el_json_es_solo_semilla(listas):
    for ind in listas.listar():
        listas.quitar(ind["id"])
    assert listas.listas() == {"blanca": [], "negra": []}
    importlib.reload(listas)        # tras el "reinicio" el JSON NO vuelve a sembrar: la base manda
    assert listas.listas() == {"blanca": [], "negra": []}


# ---------- edición en caliente (sin reiniciar) ----------

def test_anadir_se_ve_sin_reiniciar(listas):
    from app import verificar
    listas.añadir("blanca", "nuevo.sindicato.gob.ec", "Alta de TI")
    listas.añadir("negra", "PHISH-Portal.EC/robar", "Confirmado por el SOC")
    # misma sesión, misma caché refrescada por la escritura: nada de reinicio
    assert "nuevo.sindicato.gob.ec" in listas.listas()["blanca"]
    assert "phish-portal.ec/robar" in listas.listas()["negra"]
    assert verificar.enlace("https://nuevo.sindicato.gob.ec/historias")["clasificacion"] == "blanca"
    assert verificar.enlace("http://phish-portal.ec/robar/x")["clasificacion"] == "negra"


def test_quitar_se_ve_sin_reiniciar(listas):
    ind = listas.añadir("blanca", "fuera.gob.ec", "se retira")
    listas.quitar(ind["id"])
    assert not any(i["id"] == ind["id"] for i in listas.listar())
    assert "fuera.gob.ec" not in listas.listas()["blanca"]
    # volver a dar de alta el mismo valor no rompe el UNIQUE (reactiva la fila)
    alta = listas.añadir("blanca", "fuera.gob.ec", "otra vez")
    assert alta["id"] == ind["id"] and alta["activo"] == 1
    assert listas.listas()["blanca"].count("fuera.gob.ec") == 1


def test_listar_dinamico(listas):
    ind = listas.añadir("negra", "dinamico.xyz", "alta en caliente", quien="ana.ti")
    assert ind["tipo"] == "negra" and ind["valor"] == "dinamico.xyz" and ind["activo"] == 1
    assert any(i["id"] == ind["id"] for i in listas.listar())
    assert all(i["activo"] == 1 for i in listas.listar())
    listas.quitar(ind["id"])
    assert not any(i["id"] == ind["id"] for i in listas.listar())


def test_normalizacion_tipo_aware(listas):
    from app import verificar
    listas.añadir("blanca", "HTTPS://Demo.GOB.EC/Ruta?x=1#f", "")
    listas.añadir("negra", "http://Phish.EC/login?u=1", "")
    assert "demo.gob.ec" in listas.listas()["blanca"]          # la blanca vive en el host
    assert "phish.ec/login" in listas.listas()["negra"]        # la negra conserva la ruta (como la semilla)
    assert verificar.enlace("https://demo.gob.ec/cualquiera")["clasificacion"] == "blanca"
    assert verificar.enlace("http://phish.ec/login/x")["clasificacion"] == "negra"
    with pytest.raises(ValueError):
        listas.añadir("blanca", "   ", "sin valor")
    with pytest.raises(ValueError):
        listas.añadir("telefonos", "0987654321", "tipo inválido")


# ---------- solicitudes ----------

def test_solicitud_aprobada_agrega_el_indicador(listas):
    s = listas.solicitar("blanca", "nuevo.sind.gob.ec", "Lo pidió la dirección de TI", fuente="TI")
    assert s["estado"] == "PENDIENTE" and s["fuente"] == "TI"
    assert "nuevo.sind.gob.ec" not in listas.listas()["blanca"]   # pendiente todavía no es lista
    r = listas.resolver(s["id"], True, "Dominio verificado con el responsable", "ana.ti")
    assert r["estado"] == "APROBADA"
    assert r["resolucion"] == "Dominio verificado con el responsable"
    assert r["resuelto_por"] == "ana.ti" and r["resuelto_en"]
    assert "nuevo.sind.gob.ec" in listas.listas()["blanca"]       # se ve sin reiniciar


def test_solicitud_rechazada_no_agrega_nada(listas):
    s = listas.solicitar("negra", "dudoso-portal.xyz", "Lo vi en un mensaje raro")
    r = listas.resolver(s["id"], False, "No hay evidencia suficiente", "ana.ti")
    assert r["estado"] == "RECHAZADA" and r["resolucion"] == "No hay evidencia suficiente"
    assert "dudoso-portal.xyz" not in listas.listas()["negra"]
    assert not any(i["valor"] == "dudoso-portal.xyz" for i in listas.listar())


def test_motivo_obligatorio_y_estados(listas):
    s = listas.solicitar("blanca", "x.gob.ec", "justificación válida")
    with pytest.raises(ValueError):
        listas.resolver(s["id"], True, "   ", "ana.ti")          # sin motivo no se resuelve
    with pytest.raises(ValueError):
        listas.resolver(s["id"], False, "", "ana.ti")
    listas.resolver(s["id"], True, "Todo en orden", "ana.ti")
    with pytest.raises(ValueError):
        listas.resolver(s["id"], True, "ya resuelta", "ana.ti")  # solo PENDIENTE se resuelve
    with pytest.raises(ValueError):
        listas.solicitar("blanca", "y.gob.ec", "   ")            # sin justificación no entra
    s2 = listas.solicitar("blanca", "z.gob.ec", "primera")
    with pytest.raises(ValueError):
        listas.solicitar("blanca", "z.gob.ec", "duplicada")      # no hay dos solicitudes vivas
    listas.resolver(s2["id"], False, "no corresponde", "ana.ti")
    listas.solicitar("blanca", "z.gob.ec", "reintento tras rechazo")   # tras rechazo sí se puede volver a pedir


def test_bandeja_de_solicitudes(listas):
    s = listas.solicitar("blanca", "bandeja.gob.ec", "Lo pidió operaciones", fuente="operaciones")
    assert [x["id"] for x in listas.solicitudes("PENDIENTE")] == [s["id"]]
    listas.resolver(s["id"], False, "Sin confirmación", "ana.ti")
    assert [x["id"] for x in listas.solicitudes("PENDIENTE")] == []
    assert [x["id"] for x in listas.solicitudes("RECHAZADA")] == [s["id"]]
    assert [x["id"] for x in listas.solicitudes()] == [s["id"]]


# ---------- conflicto (blanca y negra a la vez) ----------

def test_conflicto_si_esta_en_ambas(listas):
    from app import verificar
    # secure-login-portal.xyz ya viene en la negra por la semilla; estar también en la blanca es CONFLICTO
    listas.añadir("blanca", "secure-login-portal.xyz", "Caso en revisión")
    assert "secure-login-portal.xyz" in listas.listas()["blanca"]
    assert "secure-login-portal.xyz" in listas.listas()["negra"]
    r = verificar.enlace("http://secure-login-portal.xyz/a")
    assert r["clasificacion"] == "conflicto"
    assert r["veredicto"] == "sospechoso", r      # no se da por bueno ni por malo: revisión humana
    assert r["tecnicas"] == [], r


# ---------- auditoría ----------

def test_cada_cambio_queda_en_bitacora(listas):
    from app import estado
    listas.añadir("blanca", "auditado.gob.ec", "alta con auditoría", quien="ana.ti")
    listas.solicitar("blanca", "solicitado.gob.ec", "justificación", fuente="operaciones")
    eventos = estado.leer("bitacora")
    assert any(e["actor"] == "ana.ti" and "auditado.gob.ec" in (e["objetivo"] + e["detalle"]) for e in eventos)
    assert any("solicitado.gob.ec" in (e["objetivo"] + e["detalle"]) for e in eventos)


def test_auditoria_propia_si_bitacora_no_disponible(listas, monkeypatch):
    from app import config, estado

    def _caida(*args, **kwargs):
        raise RuntimeError("bitácora no disponible")

    monkeypatch.setattr(estado, "bitacora", _caida)
    listas.añadir("blanca", "sinbitacora.gob.ec", "", quien="ana.ti")   # la operación no se pierde
    assert "sinbitacora.gob.ec" in listas.listas()["blanca"]
    db = sqlite3.connect(config.estado() / "listas.sqlite3")
    try:
        filas = db.execute("SELECT actor, objetivo FROM auditoria").fetchall()
    finally:
        db.close()
    assert any(f[1] == "sinbitacora.gob.ec" for f in filas), filas
