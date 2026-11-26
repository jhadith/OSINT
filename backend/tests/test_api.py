"""Pruebas de punta a punta del backend: acceso por rol, carga de datos con el motor real, vistas, denuncias y privacidad.
Correr desde backend/:  pytest -q
"""
import importlib.util
import io
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROYECTO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROYECTO / "motor"))


def _modulo(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = _modulo("gen_motor", PROYECTO / "motor" / "tests" / "generador.py")
gen_citas = _modulo("gen_citas", PROYECTO / "motor" / "tests" / "generador_citas.py")


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    base = tmp_path_factory.mktemp("sentinel")
    datos = base / "datos"
    gen.generar(datos, 60_000, 50_000)                      # fw.csv y med.csv sintéticos con los 4 ataques
    gen_citas.generar(datos / "agendamiento.csv", afiliados=800)
    mp = pytest.MonkeyPatch()
    mp.setenv("SENTINEL_ESTADO", str(base / "estado"))
    mp.setenv("SENTINEL_DATOS", str(datos))
    from app.main import app
    cli = TestClient(app)
    yield cli
    mp.undo()


def ingresar(cli, usuario, clave="demo2026"):
    r = cli.post("/api/acceso/ingresar", json={"usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def analista(entorno):
    return ingresar(entorno, "analista")


@pytest.fixture(scope="module")
def con_analisis(entorno, analista):
    cli = entorno
    # denuncia ciudadana previa sobre el contacto de un tramitador (patrón HG-07)
    r = cli.post("/api/publico/denuncias", json={"tipo": "venta_de_citas", "medio": "whatsapp",
                                                  "contacto_sospechoso": "SIM-TRAMITE-02",
                                                  "descripcion": "Me cobraron por una cita de pediatría",
                                                  "acepta_privacidad": True})
    assert r.status_code == 200
    r = cli.post("/api/analisis/desde-carpeta", headers=analista,
                 data={"fw_origen": "datos", "fw": "fw.csv", "med_origen": "datos", "med": "med.csv",
                       "citas_origen": "datos", "citas": "agendamiento.csv"})
    assert r.status_code == 200, r.text
    i = r.json()["id"]
    for _ in range(240):
        m = cli.get(f"/api/analisis/{i}", headers=analista).json()
        if m["estado"] != "en_curso":
            break
        time.sleep(0.5)
    assert m["estado"] == "listo", m
    return m


def test_ingreso_y_bloqueo(entorno):
    for _ in range(4):
        assert entorno.post("/api/acceso/ingresar", json={"usuario": "auditor", "clave": "mala"}).status_code == 401
    assert entorno.post("/api/acceso/ingresar", json={"usuario": "auditor", "clave": "mala"}).status_code == 423
    r = entorno.post("/api/acceso/ingresar", json={"usuario": "auditor", "clave": "demo2026"})
    assert r.status_code == 423 and "bloqueada" in r.text


def test_permisos_por_rol(entorno, con_analisis):
    salud = ingresar(entorno, "salud")
    assert entorno.get("/api/casos", headers=salud).status_code == 403
    assert entorno.post("/api/verificar/enlace", json={"url": "https://www.espe.edu.ec"}, headers=salud).status_code == 200
    jefe = ingresar(entorno, "jefe")
    assert entorno.get("/api/ejecutivo", headers=jefe).status_code == 200
    assert entorno.post("/api/casos/C1/decision", json={"estado": "confirmado", "motivo": "x" * 12},
                        headers=jefe).status_code == 403
    assert entorno.get("/api/casos").status_code == 401


def test_pasos_visibles_del_analisis(con_analisis):
    estados = {p["id"]: p["estado"] for p in con_analisis["pasos"]}
    assert all(v in ("listo", "omitido") for v in estados.values()), estados
    datos = {p["id"]: p["datos"] for p in con_analisis["pasos"]}
    assert datos["validacion"]["filas_firewall"] > 0 and datos["proteccion"]["seudonimos_generados"] > 0
    assert datos["cruce"]["ataques_confirmados_en_ambas_fuentes"] == 4


def test_vista_ejecutiva(entorno, analista, con_analisis):
    e = entorno.get("/api/ejecutivo", headers=analista).json()
    assert e["incidentes"] == 4 and e["criticos"] == 2
    assert [h["titulo"] for h in e["historia"]][0] == "Posible fuga de datos"
    assert e["agendamiento"]["origenesEnRevision"] >= 3 and len(e["pulso"]) > 700


def test_casos_y_matriz_dinamica(entorno, analista, con_analisis):
    titulos = {c["id"]: c["titulo"] for c in entorno.get("/api/casos", headers=analista).json()}
    assert titulos == {"C1": "Fuerza bruta", "C2": "Escaneo de servicios", "C3": "Posible fuga de datos",
                       "C4": "Cuenta fantasma"}
    antes = {r["id"]: r for r in entorno.get("/api/riesgos", headers=analista).json()["riesgos"]}
    assert antes["R2"]["probabilidad"] == 5 and "C3" in antes["R2"]["casos"]
    assert antes["R4"]["probabilidad"] == 4 and antes["R7"]["casos"] == ["C2"]
    r = entorno.post("/api/casos/C1/decision", json={"estado": "descartado", "motivo": "Prueba de carga autorizada"},
                     headers=analista)
    assert r.status_code == 200
    despues = {r["id"]: r for r in entorno.get("/api/riesgos", headers=analista).json()["riesgos"]}
    assert despues["R4"]["probabilidad"] == 1 and despues["R4"]["evidencia"] == ["Sin evidencia en este análisis"]


def test_agendamiento_hbvf_y_denuncia_vinculada(entorno, analista, con_analisis):
    a = entorno.get("/api/agendamiento", headers=analista).json()
    prioritarios = [c for c in a["casos"] if c["status"] == "Revisión prioritaria"]
    assert prioritarios and any("HG-07" in c["pattern_ids"] for c in prioritarios)
    assert any(c["denuncias_vinculadas"] for c in a["casos"])
    assert all("contactos_ref" not in c for c in a["casos"])
    assert a["evaluacion"]["matriz"]["fp"] == 0
    bandeja = entorno.get("/api/denuncias", headers=analista).json()
    assert any(d["origenesAgendamiento"] for d in bandeja)
    assert all("SIM-TRAMITE" not in str(d) for d in bandeja)       # el contacto solo sale enmascarado


def test_denuncia_publica_y_seguimiento(entorno, analista):
    r = entorno.post("/api/publico/denuncias", json={"tipo": "enlace_sospechoso", "enlace": "http://secure-login-portal.xyz/a",
                                                     "acepta_privacidad": True})
    cod = r.json()["codigo"]
    assert entorno.get(f"/api/publico/denuncias/{cod}").json()["estado"] == "Recibida"
    g = entorno.post(f"/api/denuncias/{cod}/gestion", headers=analista,
                     json={"estado": "atendida", "respuesta_publica": "Bloqueamos el enlace. Gracias por avisar."})
    assert g.status_code == 200
    assert entorno.get(f"/api/publico/denuncias/{cod}").json()["respuesta"].startswith("Bloqueamos")
    assert entorno.post("/api/publico/denuncias", json={"tipo": "otro", "acepta_privacidad": False}).status_code == 400


def test_reidentificar_y_bitacora(entorno, analista, con_analisis):
    c = entorno.get("/api/casos/C4", headers=analista).json()
    assert entorno.post("/api/reidentificar", json={"seudonimo": c["seudonimo"], "motivo": "corto"},
                        headers=analista).status_code == 422
    r = entorno.post("/api/reidentificar", json={"seudonimo": c["seudonimo"], "motivo": "Investigación autorizada del caso C4"},
                     headers=analista)
    assert r.status_code == 200 and r.json()["nombre"]
    auditor = ingresar(entorno, "jefe")
    acciones = {b["accion"] for b in entorno.get("/api/bitacora", headers=auditor).json()}
    assert {"Reidentificación", "Ingreso a la consola", "Análisis terminado", "Alerta crítica simulada",
            "Intento de ingreso fallido", "Denuncia recibida", "Cuenta bloqueada", "Acceso denegado"} <= acciones


def test_exportes_y_verificar(entorno, analista, con_analisis):
    assert entorno.get("/api/exportes/sigma", headers=analista).content[:2] == b"PK"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = entorno.post("/api/verificar/imagen", headers=analista, files={"imagen": ("a.png", io.BytesIO(png), "image/png")})
    assert r.json()["veredicto"] == "seguro"


def test_sin_datos_personales_y_cabeceras(entorno, analista, con_analisis):
    rutas = ["/api/ejecutivo", "/api/casos", "/api/grafo", "/api/agendamiento", "/api/denuncias", "/api/inteligencia",
             "/api/anomalias?fuente=firewall", "/api/anomalias?fuente=sistema_medico"] + [f"/api/casos/C{n}" for n in range(1, 5)]
    texto = "".join(entorno.get(r, headers=analista).text for r in rutas)
    for usuario, nombre, _, _ in gen.ATACANTES.values():
        assert usuario not in texto and nombre not in texto
    assert "IESS" not in texto.upper()
    r = entorno.get("/api/casos", headers=analista)
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
