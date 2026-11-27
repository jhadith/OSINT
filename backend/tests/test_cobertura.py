"""Casos de borde y caminos de error del backend que el flujo principal no recorre.

Cada prueba verifica un comportamiento concreto: errores de la API sin análisis activo, subida de archivos
inválidos, un análisis que falla en el motor, activación de análisis, envío de alertas, sesiones vencidas
y señales de phishing. Correr desde backend/:  pytest -q
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

PROYECTO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROYECTO / "motor"))


def _modulo(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = _modulo("gen_motor_cob", PROYECTO / "motor" / "tests" / "generador.py")
gen_citas = _modulo("gen_citas_cob", PROYECTO / "motor" / "tests" / "generador_citas.py")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    b = tmp_path_factory.mktemp("cobertura")
    datos = b / "datos"
    gen.generar(datos, 40_000, 30_000)
    gen_citas.generar(datos / "agendamiento.csv", afiliados=600)
    (datos / "otra_cosa.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    return b


@pytest.fixture(scope="module")
def cli(base):
    mp = pytest.MonkeyPatch()
    mp.setenv("SENTINEL_ESTADO", str(base / "estado"))
    mp.setenv("SENTINEL_DATOS", str(base / "datos"))
    from app import denuncias
    denuncias._ventana.clear()          # el límite anti-spam es por proceso: se reinicia para este módulo
    from app.main import app
    yield TestClient(app)
    mp.undo()


def ingresar(cli, usuario):
    r = cli.post("/api/acceso/ingresar", json={"usuario": usuario, "clave": "demo2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def analista(cli):
    return ingresar(cli, "analista")


@pytest.fixture(scope="module")
def jefe(cli):
    return ingresar(cli, "jefe")


def esperar(cli, h, i, segundos=240):
    for _ in range(segundos * 2):
        m = cli.get(f"/api/analisis/{i}", headers=h).json()
        if m["estado"] != "en_curso":
            return m
        time.sleep(0.5)
    raise AssertionError(f"El análisis {i} no terminó a tiempo")


# ---------- 1. Sin análisis activo ----------
def test_sin_analisis_la_api_responde_409_y_no_se_cae(cli, analista, jefe):
    for ruta in ("/api/serie", "/api/grafo", "/api/resumen", "/api/casos", "/api/agendamiento"):
        r = cli.get(ruta, headers=analista)
        assert r.status_code == 409, (ruta, r.status_code)
    seud = {"seudonimo": "P-ABC123", "motivo": "Investigación sin análisis cargado"}
    assert cli.post("/api/reidentificar", json=seud, headers=analista).status_code == 409
    assert cli.post("/api/agendamiento/AG-ABC123/revision", headers=analista,
                    json={"decision": "en_revision", "nota": "Sin análisis todavía"}).status_code == 409
    assert cli.get("/api/denuncias", headers=jefe).status_code == 200     # la bandeja funciona sin análisis
    from app import main
    main._al_terminar("AN-20260101-000000-0000")                         # sin casos: no lanza la excepción


def test_acceso_roles_yo_y_salir(cli):
    roles = cli.get("/api/acceso/roles").json()
    assert {r["rol"] for r in roles} == {"jefe", "analista", "ti", "salud", "auditor"}
    h = ingresar(cli, "salud")
    assert cli.get("/api/acceso/yo", headers=h).json()["rol"] == "salud"
    assert cli.post("/api/acceso/salir", headers=h).json() == {"ok": True}
    assert cli.get("/api/acceso/yo", headers=h).status_code == 401


def test_sesion_vencida_se_rechaza(cli):
    from app import seguridad
    h = ingresar(cli, "ti")
    token = h["Authorization"].removeprefix("Bearer ")
    seguridad._sesiones[token].vence = time.time() - 1
    assert cli.get("/api/acceso/yo", headers=h).status_code == 401
    assert token not in seguridad._sesiones


# ---------- 2. Fuentes y subida de archivos ----------
def test_fuentes_y_tipos_de_archivo(cli, analista):
    f = cli.get("/api/analisis/fuentes", headers=analista).json()
    tipos = {a["nombre"]: a["tipo"] for a in f["archivos"] if a["origen"] == "datos"}
    assert tipos["fw.csv"] == "firewall" and tipos["med.csv"] == "sistema_medico"
    assert tipos["agendamiento.csv"] == "agendamiento" and tipos["otra_cosa.csv"] == "otro"
    assert any(a["origen"] == "ejemplo" for a in f["archivos"])
    malo = {"fw_origen": "datos", "fw": "no_existe.csv", "med_origen": "datos", "med": "med.csv"}
    assert cli.post("/api/analisis/desde-carpeta", headers=analista, data=malo).status_code == 400
    raro = {"fw_origen": "otra_carpeta", "fw": "fw.csv", "med_origen": "datos", "med": "med.csv"}
    assert cli.post("/api/analisis/desde-carpeta", headers=analista, data=raro).status_code == 400


def test_subida_rechaza_archivos_que_no_son_csv(cli, analista):
    archivos = {"firewall": ("fw.txt", b"x", "text/plain"), "sistema_medico": ("med.csv", b"a\n1\n", "text/csv")}
    assert cli.post("/api/analisis/subir", headers=analista, files=archivos).status_code == 400


def test_subida_que_supera_el_maximo(cli, analista, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_SUBIDA", 10)
    archivos = {"firewall": ("fw.csv", b"a" * 50, "text/csv"), "sistema_medico": ("med.csv", b"a\n1\n", "text/csv")}
    r = cli.post("/api/analisis/subir", headers=analista, files=archivos)
    assert r.status_code == 400 and "tamaño máximo" in r.text


def test_no_se_lanza_un_segundo_analisis_si_hay_uno_en_curso(cli, analista, monkeypatch):
    from app import analisis
    monkeypatch.setattr(analisis, "ocupado", lambda: True)
    archivos = {"firewall": ("fw.csv", b"a\n1\n", "text/csv"), "sistema_medico": ("med.csv", b"a\n1\n", "text/csv")}
    assert cli.post("/api/analisis/subir", headers=analista, files=archivos).status_code == 400
    with pytest.raises(RuntimeError):
        analisis.lanzar("AN-x", "prueba", Path("a.csv"), Path("b.csv"), None, [], lambda i: None)


# ---------- 3. Un análisis que falla en el motor ----------
def test_archivos_con_columnas_equivocadas_terminan_en_error_y_no_se_activan(cli, analista):
    archivos = {"firewall": ("fw_mal.csv", b"col1,col2\n1,2\n", "text/csv"),
                "sistema_medico": ("med_mal.csv", b"x,y\n3,4\n", "text/csv")}
    r = cli.post("/api/analisis/subir", headers=analista, files=archivos)
    assert r.status_code == 200, r.text
    m = esperar(cli, analista, r.json()["id"])
    assert m["estado"] == "error" and "columnas" in m["error"]
    assert cli.post(f"/api/analisis/{m['id']}/activar", headers=analista).status_code == 400
    assert cli.post("/api/analisis/AN-20990101-000000-ffff/activar", headers=analista).status_code == 404
    assert cli.get("/api/analisis/no-es-un-id", headers=analista).status_code == 404


# ---------- 4. Análisis real subido sin citas y otro desde carpeta con citas ----------
@pytest.fixture(scope="module")
def sin_citas(cli, analista, base):
    d = base / "datos"
    archivos = {"firewall": ("fw.csv", (d / "fw.csv").read_bytes(), "text/csv"),
                "sistema_medico": ("med.csv", (d / "med.csv").read_bytes(), "text/csv")}
    r = cli.post("/api/analisis/subir", headers=analista, files=archivos)
    assert r.status_code == 200, r.text
    m = esperar(cli, analista, r.json()["id"])
    assert m["estado"] == "listo", m
    return m


def test_analisis_sin_citas(cli, analista, sin_citas):
    lista = cli.get("/api/analisis", headers=analista).json()
    assert lista["activo"] == sin_citas["id"] and not lista["ocupado"]
    assert any(a["id"] == sin_citas["id"] and a["activo"] for a in lista["analisis"])
    assert cli.get("/api/agendamiento", headers=analista).status_code == 409   # este análisis no trae citas
    assert cli.post("/api/agendamiento/AG-ABC123/revision", headers=analista,
                    json={"decision": "en_revision", "nota": "No hay citas en este análisis"}).status_code == 404
    r = cli.get("/api/resumen", headers=analista).json()
    assert r["analisis"] == sin_citas["id"] and r["controlesConBrecha"] > 0
    assert cli.get("/api/serie", headers=analista).status_code == 200
    assert cli.get("/api/threatpulse", headers=analista).json()["tendencias"]
    assert cli.get("/api/casos/C99", headers=analista).status_code == 404
    seud = {"seudonimo": "P-000000", "motivo": "Seudónimo que no existe en la tabla"}
    assert cli.post("/api/reidentificar", json=seud, headers=analista).status_code == 404


def test_exportes_stix_y_misp(cli, analista, sin_citas):
    for tipo in ("stix", "misp"):
        r = cli.get(f"/api/exportes/{tipo}", headers=analista)
        assert r.status_code == 200 and f"sentinel_{tipo}.json" in r.headers["content-disposition"]
        json.loads(r.content)


def test_reactivar_un_analisis_terminado(cli, analista, sin_citas):
    r = cli.post(f"/api/analisis/{sin_citas['id']}/activar", headers=analista)
    assert r.json() == {"ok": True}


def test_revision_de_agendamiento_con_citas(cli, analista, sin_citas):
    form = {"fw_origen": "datos", "fw": "fw.csv", "med_origen": "datos", "med": "med.csv",
            "citas_origen": "datos", "citas": "agendamiento.csv"}
    r = cli.post("/api/analisis/desde-carpeta", headers=analista, data=form)
    assert r.status_code == 200, r.text
    assert esperar(cli, analista, r.json()["id"])["estado"] == "listo"
    caso = cli.get("/api/agendamiento", headers=analista).json()["casos"][0]["case_id"]
    rev = cli.post(f"/api/agendamiento/{caso}/revision", headers=analista,
                   json={"decision": "en_revision", "nota": "Se revisa con el área de citas"})
    assert rev.status_code == 200 and rev.json()["decision"] == "en_revision"


# ---------- 5. Denuncias y verificación ----------
def test_denuncia_anonima_no_guarda_contacto_para_responder(cli, analista, jefe):
    # El canal es anónimo: aunque un cliente viejo mande «responder_a», no se guarda ni se muestra a nadie.
    r = cli.post("/api/publico/denuncias", json={"tipo": "otro", "responder_a": "persona@example.com",
                                                 "acepta_privacidad": True})
    cod = r.json()["codigo"]
    for quien in (jefe, analista):
        vista = cli.get("/api/denuncias", headers=quien)
        d = next(d for d in vista.json() if d["codigo"] == cod)
        assert "responder_a" not in d and "persona@example.com" not in vista.text
    assert cli.get("/api/publico/denuncias/DN-000000").status_code == 404


def test_reportar_contenido_crea_una_denuncia(cli):
    salud = ingresar(cli, "salud")
    r = cli.post("/api/verificar/reportar", headers=salud,
                 json={"entrada": "http://secure-login-portal.xyz/a", "veredicto": "malicioso", "comentario": "llegó por correo"})
    assert r.status_code == 200 and r.json()["codigo"].startswith("DN-")


def test_imagen_demasiado_grande(cli, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_IMAGEN", 100)
    salud = ingresar(cli, "salud")
    r = cli.post("/api/verificar/imagen", headers=salud, files={"imagen": ("a.png", b"\x89PNG" + b"0" * 200, "image/png")})
    assert r.status_code == 413


@pytest.mark.parametrize(("url", "senal"), [
    ("http://192.168.1.10/login", "dirección IP"),
    ("https://xn--pypal-4ve.com", "punycode"),
    ("https://a.b.c.d.ejemplo.com", "subdominios"),
    ("https://bit.ly/abc", "acortado"),
    ("https://usuario@ejemplo.com", "@"),
])
def test_senales_de_enlace(url, senal):
    from app import verificar
    assert any(senal in s["texto"] for s in verificar.enlace(url)["senales"])


def test_enlace_que_no_es_url():
    from app import verificar
    r = verificar.enlace("esto no es un enlace")
    assert r["veredicto"] == "sospechoso" and r["puntuacion"] == 50


@pytest.mark.parametrize(("nombre", "contenido", "senal"), [
    ("a.png", b"<svg onload=alert(1)>", "SVG/HTML"),
    ("a.png", b"texto plano", "formato de imagen conocido"),
    ("foto.gif", b"\x89PNG" + b"0" * 20, "no coincide"),
    ("codigo_qr.png", b"\x89PNG" + b"0" * 20, "QR"),
    ("factura.png", b"\x89PNG" + b"0" * 20, "gancho"),
    ("grande.png", b"\x89PNG" + b"0" * (8 * 1024 * 1024 + 1), "grande"),
])
def test_senales_de_imagen(nombre, contenido, senal):
    from app import verificar
    assert any(senal in s["texto"] for s in verificar.imagen(nombre, contenido)["senales"])


# ---------- 6. Alertas por Telegram (sin red) ----------
class _Respuesta:
    def __init__(self, ok):
        self._ok = ok

    def read(self):
        return json.dumps({"ok": self._ok}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_enviar_telegram_sin_credenciales(monkeypatch):
    from app import telegram
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError, match="faltan"):
        telegram._enviar("hola")


@pytest.mark.parametrize("ok", [True, False])
def test_enviar_telegram_con_api_simulada(monkeypatch, ok):
    from app import telegram
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-de-prueba")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    pedidos = []
    monkeypatch.setattr(telegram.urllib.request, "urlopen", lambda p, timeout: pedidos.append(p) or _Respuesta(ok))
    if ok:
        telegram._enviar("hola")
    else:
        with pytest.raises(RuntimeError, match="rechazó"):
            telegram._enviar("hola")
    assert pedidos[0].full_url.startswith("https://api.telegram.org/bot")


def test_avisar_criticos_en_modo_real_registra_el_fallo(cli, monkeypatch):
    from app import config, estado, telegram

    def falla(_):
        raise RuntimeError("sin red")
    monkeypatch.setattr(config, "TELEGRAM_ENVIAR", True)
    monkeypatch.setattr(telegram, "_enviar", falla)
    casos = [{"id": "C1", "gravedad": "alta", "alerta": {"texto": "x"}},
             {"id": "C9", "gravedad": "critica", "alerta": {"texto": "Caso crítico de prueba"}}]
    telegram.avisar_criticos("AN-prueba-real", casos)
    registro = estado.ultimo_por("telegram", "clave")
    assert "AN-prueba-real:C1" not in registro                     # solo los críticos generan aviso
    assert registro["AN-prueba-real:C9"]["enviada"] is False
    assert any("No se pudo enviar" in b["detalle"] for b in estado.leer("bitacora"))


# ---------- 7. Funciones internas ----------
def test_guardar_reintenta_si_el_archivo_esta_bloqueado(cli, monkeypatch):
    from app import analisis
    i = analisis.nuevo("prueba")
    llamadas = []

    def bloqueado(*a):
        llamadas.append(a)
        raise PermissionError
    monkeypatch.setattr(analisis.os, "replace", bloqueado)
    monkeypatch.setattr(analisis.time, "sleep", lambda s: None)
    analisis._guardar(i, {"id": i})
    assert len(llamadas) == 20
    assert json.loads((analisis.carpeta() / i / "meta.json").read_text(encoding="utf-8")) == {"id": i}
    analisis.borrar_entrada(i)
    assert not (analisis.carpeta() / i / "entrada").exists()


def test_al_terminar_ignora_errores_de_datos(monkeypatch):
    from app import datos, main

    def sin_datos():
        raise HTTPException(409, "sin datos")
    monkeypatch.setattr(datos, "casos", sin_datos)
    main._al_terminar("AN-cualquiera")
