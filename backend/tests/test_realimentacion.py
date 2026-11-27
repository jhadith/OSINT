"""Realimentación (S9/T18): métricas precision/recall/F1, recalibración explícita de umbrales
en rules/*.yml y reentrenamiento con el histórico acumulado de ventanas.

Correr desde backend/:  pytest -q tests/test_realimentacion.py

Ninguna prueba escribe en el repositorio: estado/, rules/ y los CSV viven en tmp_path.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

PROYECTO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROYECTO / "motor"))

from motor import ml


def _modulo(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = _modulo("gen_realimentacion", PROYECTO / "motor" / "tests" / "generador.py")

# Títulos reales del catálogo del motor (motor/motor/priorizacion.py): sin IPs ni fechas.
TITULO_FB = "Fuerza bruta contra el servidor médico"
TITULO_INSEGUROS = "Servicios sin cifrado permitidos (Telnet, SMBv1, NetBIOS)"
ACCION_BITACORA = "Recalibración de umbrales"
ANALISIS_FALSO = "AN-20261125-090000-abcd"
MOTIVO = "Ajuste por falsos positivos revisados"


@pytest.fixture()
def realimentacion():
    """El módulo bajo prueba, importado en el momento de usarlo."""
    from app import realimentacion as m
    return m


@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    """Cliente con estado/, datos/ y rules/ aislados en tmp: nada de esto toca el repositorio."""
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path / "estado"))
    monkeypatch.setenv("SENTINEL_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("SENTINEL_RULES", str(tmp_path / "rules"))
    shutil.copytree(PROYECTO / "rules", tmp_path / "rules")
    from app.main import app
    return TestClient(app), tmp_path


def ingresar(cli, usuario="analista"):
    r = cli.post("/api/acceso/ingresar", json={"usuario": usuario, "clave": "demo2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _fp_descartada(titulo: str = TITULO_FB, caso: str = "C9", alerta: str = "AL-1"):
    """Falso positivo real del ciclo de vida: alerta creada y descartada por el analista."""
    from app import almacen, estado
    with almacen.abriendo(estado._ruta()) as db:
        almacen.crear_alerta(db, alerta, caso_id=caso, titulo=titulo)
        almacen.registrar_decision(db, alerta, "descartada", "ana",
                                   "Tráfico legítimo revisado con el equipo de TI")


def _analisis_falso(base: Path, alertas: list[dict]):
    """Análisis activo fabricado: solo los JSON que lee la API (alertas.json y consola/casos.json)."""
    d = base / "estado" / "analisis" / ANALISIS_FALSO
    (d / "salidas" / "consola").mkdir(parents=True, exist_ok=True)
    (d / "salidas" / "alertas.json").write_text(json.dumps(alertas, ensure_ascii=False), encoding="utf-8")
    (d / "salidas" / "consola" / "casos.json").write_text("[]", encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"id": ANALISIS_FALSO, "archivos": {
        "firewall": "fw.csv", "sistema_medico": "med.csv", "agendamiento": None}}), encoding="utf-8")
    (base / "estado" / "analisis" / "activo.txt").write_text(ANALISIS_FALSO, encoding="utf-8")


def _eventos_bitacora():
    from app import estado
    return [e for e in estado.leer("bitacora") if e["accion"] == ACCION_BITACORA]


def _reglas(base: Path) -> dict[str, bytes]:
    return {f.name: f.read_bytes() for f in sorted((base / "rules").glob("*.yml"))}


def _reglas_repo() -> dict[str, bytes]:
    return {f.name: f.read_bytes() for f in sorted((PROYECTO / "rules").glob("*.yml"))}


# ---------- métricas ----------

def test_metricas_precision_recall_y_f1(realimentacion, entorno):
    from app import almacen, estado
    with almacen.abriendo(estado._ruta()) as db:
        almacen.crear_alerta(db, "AL-1", caso_id="C1", titulo=TITULO_FB)
        almacen.registrar_decision(db, "AL-1", "confirmada", "ana", "Coincide con el registro de accesos")
        almacen.crear_alerta(db, "AL-2", caso_id="C2", titulo="Escaneo de servicios del servidor médico")
        almacen.registrar_decision(db, "AL-2", "descartada", "ana", "Escaneo autorizado del equipo de TI")
        almacen.crear_alerta(db, "AL-3", caso_id="C3", titulo="Posible fuga de datos por SSH")
        almacen.registrar_decision(db, "AL-3", "confirmada", "ana", "Reglas y modelo coinciden")
        m = realimentacion.metricas(db, [])
    assert m["precision"]["valor"] == pytest.approx(2 / 3)
    assert m["precision"]["confirmadas"] == 2 and m["precision"]["descartadas"] == 1
    assert "confirmadas" in m["precision"]["formula"]
    assert m["recall"]["valor"] == pytest.approx(2 / 3)
    assert m["recall"]["casosConocidos"] == 3
    assert m["recall"]["decididos"] == 3 and m["recall"]["confirmados"] == 2
    assert m["f1"]["valor"] == pytest.approx(2 / 3)
    assert [c["caso"] for c in m["casosConocidos"]] == ["C1", "C2", "C3"]
    assert {c["caso"]: c["estado"] for c in m["casosConocidos"]} == {
        "C1": "confirmada", "C2": "descartada", "C3": "confirmada"}
    assert all(m[k]["explicacion"] for k in ("precision", "recall", "f1"))


def test_metricas_sin_decisiones_no_inventa_numeros(realimentacion, entorno):
    from app import almacen, estado
    alertas_json = [{"caso": f"Caso {n}", "titulo": TITULO_FB, "regla": "fuerza_bruta"} for n in range(1, 5)]
    with almacen.abriendo(estado._ruta()) as db:
        m = realimentacion.metricas(db, alertas_json)
    # sin decisiones de analista la precisión no existe; sin casos de referencia decididos el
    # recall tampoco: se dice en la explicación en vez de inventar un número.
    assert m["precision"]["valor"] is None and m["precision"]["explicacion"]
    assert m["recall"]["valor"] is None and m["recall"]["decididos"] == 0 and m["recall"]["explicacion"]
    assert m["f1"]["valor"] is None and m["f1"]["explicacion"]
    assert len(m["casosConocidos"]) == 4


def test_metricas_cero_de_verdad_no_es_none(realimentacion, entorno):
    from app import almacen, estado
    _fp_descartada(caso="C1")
    with almacen.abriendo(estado._ruta()) as db:
        m = realimentacion.metricas(db, [])
    # todo descartado es precisión 0, no "sin datos"
    assert m["precision"]["valor"] == 0.0
    assert m["recall"]["valor"] == 0.0
    assert m["f1"]["valor"] == 0.0


def test_endpoint_realimentacion(entorno):
    cli, base = entorno
    assert cli.get("/api/realimentacion").status_code == 401
    salud = ingresar(cli, "salud")
    assert cli.get("/api/realimentacion", headers=salud).status_code == 403
    _analisis_falso(base, [{"caso": "Caso 1", "titulo": TITULO_FB, "regla": "fuerza_bruta"}])
    h = ingresar(cli, "analista")
    r = cli.get("/api/realimentacion", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert {"precision", "recall", "f1", "casosConocidos", "recalibraciones", "historico",
            "analisis"} <= set(d)
    assert d["analisis"] == ANALISIS_FALSO
    assert d["casosConocidos"] == [{"caso": "C1", "titulo": TITULO_FB, "estado": "pendiente"}]
    assert d["precision"]["valor"] is None      # nadie decidió todavía: no se inventa un número
    assert d["recalibraciones"] == []
    assert d["historico"] == {"firewall": 0, "sistema_medico": 0}


# ---------- recalibración ----------

def test_recalibrar_aplica_un_ajuste_es_idempotente_y_va_a_la_bitacora(realimentacion, entorno):
    _, base = entorno
    _fp_descartada()
    original = (base / "rules" / "firewall.yml").read_text(encoding="utf-8")
    r1 = realimentacion.recalibrar(motivo="Falsos positivos de la última revisión",
                                   actor="ana", rol="Analista del SOC")
    assert len(r1["cambios"]) == 1
    c = r1["cambios"][0]
    assert (c["archivo"], c["clave"], c["antes"], c["despues"], c["direccion"]) == (
        "firewall.yml", "FUERZA_BRUTA_PCT_NEGADO", 0.8, 0.88, "subir")
    texto = (base / "rules" / "firewall.yml").read_text(encoding="utf-8")
    assert "FUERZA_BRUTA_PCT_NEGADO: 0.88" in texto
    assert "# >= 80 %" in texto                       # los comentarios del YAML quedan intactos
    lineas = [i for i, (a, b) in enumerate(zip(original.splitlines(), texto.splitlines(), strict=False)) if a != b]
    assert len(lineas) == 1 and "FUERZA_BRUTA_PCT_NEGADO" in texto.splitlines()[lineas[0]]
    assert {k: v for k, v in _reglas(base).items() if k != "firewall.yml"} == {
        k: v for k, v in _reglas_repo().items() if k != "firewall.yml"}
    eventos = _eventos_bitacora()
    assert len(eventos) == 1 and eventos[0]["actor"] == "ana"
    det = json.loads(eventos[0]["detalle"])
    assert det["motivo"] == "Falsos positivos de la última revisión"
    assert det["fps"] == ["alerta:AL-1"]
    # segunda corrida con los mismos FP: ni el YAML ni la bitácora cambian
    r2 = realimentacion.recalibrar(motivo="Falsos positivos de la última revisión",
                                   actor="ana", rol="Analista del SOC")
    assert r2["cambios"] == []
    assert (base / "rules" / "firewall.yml").read_text(encoding="utf-8") == texto
    assert len(_eventos_bitacora()) == 1


def test_recalibrar_sin_falsos_positivos_no_cambia_nada(realimentacion, entorno):
    _, base = entorno
    antes = _reglas(base)
    r = realimentacion.recalibrar(motivo="Sin novedades que ajustar hoy",
                                  actor="ana", rol="Analista del SOC")
    assert r["cambios"] == []
    assert _reglas(base) == antes
    assert _eventos_bitacora() == []


def test_recalibrar_reporta_fp_sin_umbral_en_lugar_de_adivinar(realimentacion, entorno):
    _, base = entorno
    _fp_descartada(titulo=TITULO_INSEGUROS, caso="C5", alerta="AL-5")
    antes = _reglas(base)
    r = realimentacion.recalibrar(motivo="Falso positivo de servicios sin cifrar",
                                  actor="ana", rol="Analista del SOC")
    assert r["cambios"] == []
    assert r["sinUmbral"] and r["sinUmbral"][0]["fps"] == ["alerta:AL-5"]
    assert r["sinUmbral"][0]["nota"]
    assert _reglas(base) == antes                 # sin umbral numérico no se toca ningún archivo
    assert _eventos_bitacora() == []


def test_recalibrar_de_un_caso_descartado_usa_las_reglas_del_analisis(realimentacion, entorno):
    _, base = entorno
    _analisis_falso(base, [{"caso": "Caso 7", "titulo": "Escaneo de servicios del servidor médico",
                            "regla": "escaneo"}])
    from app import estado
    estado.agregar("decisiones", {"clave": f"{ANALISIS_FALSO}:C7", "casoId": "C7", "estado": "descartado",
                                  "motivo": "Escaneo autorizado por el equipo de TI", "analista": "ana",
                                  "fecha": estado.ahora()})
    r = realimentacion.recalibrar(motivo="El escaneo resultó ser inventario autorizado",
                                  actor="ana", rol="Analista del SOC")
    assert [(x["clave"], x["antes"], x["despues"]) for x in r["cambios"]] == [
        ("ESCANEO_PUERTOS_MIN", 3, 4)]
    assert r["cambios"][0]["fps"] == [f"caso:{ANALISIS_FALSO}:C7"]
    assert "ESCANEO_PUERTOS_MIN: 4" in (base / "rules" / "firewall.yml").read_text(encoding="utf-8")
    assert len(_eventos_bitacora()) == 1


def test_recalibrar_por_endpoint(entorno):
    cli, base = entorno
    _fp_descartada()
    assert cli.post("/api/realimentacion/recalibrar",
                    json={"motivo": MOTIVO}).status_code == 401
    salud = ingresar(cli, "salud")
    assert cli.post("/api/realimentacion/recalibrar", json={"motivo": MOTIVO},
                    headers=salud).status_code == 403
    h = ingresar(cli, "analista")
    assert cli.post("/api/realimentacion/recalibrar", json={"motivo": "corto"},
                    headers=h).status_code == 422
    r = cli.post("/api/realimentacion/recalibrar", json={"motivo": MOTIVO}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["cambios"], r.json()
    assert "FUERZA_BRUTA_PCT_NEGADO: 0.88" in (base / "rules" / "firewall.yml").read_text(encoding="utf-8")
    r2 = cli.post("/api/realimentacion/recalibrar", json={"motivo": MOTIVO}, headers=h)
    assert r2.json()["cambios"] == []
    g = cli.get("/api/realimentacion", headers=h).json()
    assert len(g["recalibraciones"]) == 1
    assert g["recalibraciones"][0]["motivo"] == MOTIVO
    assert g["recalibraciones"][0]["actor"]
    assert g["recalibraciones"][0]["cambios"][0]["clave"] == "FUERZA_BRUTA_PCT_NEGADO"


def test_recalibrar_acumula_el_historico_y_reentrena(entorno):
    cli, base = entorno
    gen.generar(base / "datos", 6000, 5000)
    _analisis_falso(base, [{"caso": "Caso 1", "titulo": TITULO_FB, "regla": "fuerza_bruta"}])
    _fp_descartada()
    h = ingresar(cli, "analista")
    r = cli.post("/api/realimentacion/recalibrar", json={"motivo": MOTIVO}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cambios"], d
    ren = d["reentrenamiento"]
    assert ren["firewall"]["ventanas"] > 0 and ren["sistema_medico"]["ventanas"] > 0
    assert ren["firewall"]["semilla"] == 42
    assert (base / "estado" / "historico" / "firewall.csv").exists()
    assert (base / "estado" / "historico" / "sistema_medico.csv").exists()
    g = cli.get("/api/realimentacion", headers=h).json()
    assert g["historico"]["firewall"] == ren["firewall"]["ventanas"]
    assert g["historico"]["sistema_medico"] == ren["sistema_medico"]["ventanas"]


# ---------- reentrenamiento con histórico (motor.motor.ml) ----------

def _fw(n=6000, semilla=7) -> pd.DataFrame:
    """Ventanas de firewall ya normalizadas (las columnas que consume ml.firewall)."""
    rng = np.random.default_rng(semilla)
    return pd.DataFrame({
        "u": [f"usuario{(i * 7) % 60:02d}" for i in range(n)],
        "s": rng.integers(0, 31 * 86400, n),
        "p": rng.choice([22, 80, 445, 3389, 8471], n),
        "neg": rng.random(n) < 0.3,
        "srv": rng.random(n) < 0.6,
        "ssh": rng.random(n) < 0.1,
        "seg": rng.random(n) < 0.05,
    })


def _med(n=6000, semilla=9) -> pd.DataFrame:
    """Ventanas del sistema médico ya normalizadas (las columnas que consume ml.sistema_medico)."""
    rng = np.random.default_rng(semilla)
    acciones = ["ACCESO FALLIDO", "DESCARGA EXITOSA", "TRANSFERENCIA EXITOSA", "INACTIVACION",
                "REACTIVACION", "ACTIVAR USUARIO", "ACTUALIZAR NIVEL", "INGRESO", "EXPORTAR"]
    return pd.DataFrame({
        "cuenta": [f"SIM{i % 40:07d}" for i in range(n)],
        "persona": [f"PERSONA{(i * 13) % 500}" for i in range(n)],
        "accion": rng.choice(acciones, n),
        "s": rng.integers(0, 31 * 86400, n),
        "ipmal": rng.random(n) < 0.01,
    })


def test_acumular_es_idempotente_y_agrega_solo_lo_nuevo(tmp_path):
    ruta = tmp_path / "historico.csv"
    f1 = ml.ventanas_firewall(_fw())
    f2 = ml.ventanas_firewall(_fw(semilla=18))
    ml.acumular(f1, "firewall", ruta)
    ml.acumular(f1, "firewall", ruta)      # la misma corrida no duplica
    ml.acumular(f2, "firewall", ruta)      # corrida distinta agrega solo sus ventanas nuevas
    h = pd.read_csv(ruta, float_precision="round_trip")
    assert list(h.columns[:2]) == ["entidad", "ventana"]
    claves = list(zip(h["entidad"].astype(str), h["ventana"], strict=False))
    assert len(claves) == len(set(claves))
    k1 = set(zip(f1.reset_index()["u"].astype(str), f1.reset_index()["v"], strict=False))
    k2 = set(zip(f2.reset_index()["u"].astype(str), f2.reset_index()["v"], strict=False))
    assert set(claves) == k1 | k2
    with pytest.raises(ValueError, match="fuente desconocida"):
        ml.acumular(f1, "correo", ruta)


@pytest.mark.parametrize("fuente,normalizar,modelo", [
    ("firewall", lambda d: ml.ventanas_firewall(d), lambda d: ml.firewall(d)),
    ("sistema_medico", lambda d: ml.ventanas_sistema_medico(d), lambda d: ml.sistema_medico(d)),
])
def test_reentrenar_es_determinista_y_mantiene_el_top(tmp_path, fuente, normalizar, modelo):
    datos = _fw() if fuente == "firewall" else _med()
    f = normalizar(datos)
    base = modelo(datos)                       # lo que corre el motor en cada análisis
    ruta = tmp_path / "historico.csv"
    ml.acumular(f, fuente, ruta)
    m1 = ml.reentrenar(fuente, ruta)
    m2 = ml.reentrenar(fuente, ruta)
    s1, s2 = ml.puntuar_modelo(m1, f), ml.puntuar_modelo(m2, f)
    assert np.array_equal(s1, s2)              # misma semilla → mismo modelo → mismos puntajes
    col = "u" if fuente == "firewall" else "cuenta"
    top_modelo = f.reset_index().iloc[np.argsort(-s1, kind="stable")][col].head(5).tolist()
    top_base = base.tabla.sort_values("puesto").head(5)[col].tolist()
    assert top_modelo == top_base              # mismos puestos top sobre el mismo dataset
    assert np.allclose(s1, base.tabla["puntaje"].to_numpy(), atol=0.06)


def test_reentrenar_sin_historico_falla_con_mensaje_claro(tmp_path):
    with pytest.raises(ValueError, match="histórico"):
        ml.reentrenar("firewall", tmp_path / "no-existe.csv")
