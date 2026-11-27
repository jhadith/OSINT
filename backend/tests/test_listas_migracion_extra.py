"""Migración del estado JSON/JSONL a SQLite y casos de borde de las listas de comparación."""
import json

import pytest
from app import config, listas, migrar_estado


@pytest.fixture(autouse=True)
def _estado(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    monkeypatch.delenv("SENTINEL_DB_URL", raising=False)


# ---------- migrar_estado ----------
def _estado_viejo(carpeta):
    (carpeta / "bitacora.jsonl").write_text(
        json.dumps({"id": "B-00001", "fecha": "2026-10-07T13:00:00", "actor": "Analista", "rol": "SOC",
                    "accion": "Ingreso", "objetivo": "consola", "detalle": ""}) + "\n\n", encoding="utf-8")
    (carpeta / "decisiones.jsonl").write_text(json.dumps({"caso": "C3", "estado": "confirmado"}) + "\n", encoding="utf-8")
    (carpeta / "usuarios.json").write_text(json.dumps({"jefe": {"nombre": "Jefe", "rol": "jefe", "sal": "s", "hash": "h"}}),
                                           encoding="utf-8")
    (carpeta / "preferencias.json").write_text("{}", encoding="utf-8")
    (carpeta / "analisis" / "AN-1").mkdir(parents=True)
    (carpeta / "analisis" / "AN-1" / "meta.json").write_text('{"id": "AN-1"}', encoding="utf-8")


def test_migracion_completa_es_idempotente_y_respalda(tmp_path, capsys):
    _estado_viejo(tmp_path)
    primera = migrar_estado.migrar(tmp_path)
    assert primera == {"bitacora": 1, "decisiones": 1, "usuarios": 1, "preferencias": 1, "analisis": 1}
    assert (tmp_path / migrar_estado.RESPALDO / "bitacora.jsonl").exists()
    assert migrar_estado.respaldar(tmp_path) is None                         # el respaldo se hace una sola vez
    segunda = migrar_estado.migrar(tmp_path)
    assert set(segunda.values()) == {0}                                       # no duplica nada
    migrar_estado.main()
    assert "Migración a" in capsys.readouterr().out


def test_carpeta_vacia_no_crea_respaldo(tmp_path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    assert migrar_estado.respaldar(vacia) is None
    assert migrar_estado.migrar(vacia) == {}


# ---------- listas ----------
def test_estado_de_solicitud_invalido():
    with pytest.raises(ValueError, match="inválido"):
        listas.solicitudes("archivada")


def test_quitar_indicador_desconocido_y_ya_inactivo():
    with pytest.raises(ValueError, match="desconocido"):
        listas.quitar(999999)
    reg = listas.añadir("negra", "phishing-de-prueba.example", "prueba")
    assert listas.quitar(reg["id"])["activo"] == 0
    assert listas.quitar(reg["id"])["activo"] == 0                           # quitar dos veces no falla


def test_resolver_dos_veces_o_una_solicitud_inexistente():
    s = listas.solicitar("negra", "otro-phishing.example", "Llegó por correo a todo el servicio", quien="Salud")
    listas.resolver(s["id"], True, "Confirmado por el SOC", quien="Analista")
    with pytest.raises(ValueError, match="ya fue resuelta"):
        listas.resolver(s["id"], False, "Otra decisión distinta", quien="Analista")
    with pytest.raises(ValueError, match="desconocida"):
        listas.resolver(999999, True, "No existe esta solicitud", quien="Analista")


def test_semilla_ilegible_o_con_valores_invalidos(monkeypatch, tmp_path):
    fijos = tmp_path / "fijos"
    fijos.mkdir()
    monkeypatch.setattr(config, "FIJOS", fijos)                              # sin listas.json: la base queda vacía
    assert all(not v for v in listas.listas().values())


def test_semilla_con_valores_invalidos_se_salta(monkeypatch, tmp_path):
    fijos = tmp_path / "fijos2"
    fijos.mkdir()
    tipo = sorted(listas.TIPOS_LISTA)[0]
    (fijos / "listas.json").write_text(json.dumps({tipo: ["", "valido-de-prueba.example"]}), encoding="utf-8")
    monkeypatch.setattr(config, "FIJOS", fijos)
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path / "otra"))
    valores = listas.listas()[tipo]
    assert "valido-de-prueba.example" in valores and "" not in valores


def test_auditar_no_rompe_si_falla_la_base(monkeypatch):
    def rota():
        raise RuntimeError("base caída")
    monkeypatch.setattr(listas, "_conexion", rota)
    listas._auditar("Analista", "Prueba", "x", "")                            # solo deja el error en el log
