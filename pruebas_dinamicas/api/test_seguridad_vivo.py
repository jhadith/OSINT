"""Pruebas dinámicas de seguridad contra el servidor en ejecución (caja negra).

Requieren Sentinel Salud corriendo en SENTINEL_URL (por defecto http://127.0.0.1:8010).
Solo se permiten direcciones locales: estas pruebas nunca se lanzan contra sistemas reales.
"""
import os
from urllib.parse import urlparse

import httpx
import pytest

BASE = os.environ.get("SENTINEL_URL", "http://127.0.0.1:8010").rstrip("/")
CLAVE = os.environ.get("SENTINEL_CLAVE_DEMO", "demo2026")

if urlparse(BASE).hostname not in ("127.0.0.1", "localhost"):
    pytest.exit(f"Por seguridad, estas pruebas solo corren contra localhost (SENTINEL_URL={BASE}).", returncode=2)


@pytest.fixture(scope="session")
def cli():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        try:
            c.get("/api/acceso/roles").raise_for_status()
        except httpx.HTTPError as e:
            pytest.exit(f"El servidor no responde en {BASE}: {e}", returncode=2)
        yield c


def token(cli, usuario):
    r = cli.post("/api/acceso/ingresar", json={"usuario": usuario, "clave": CLAVE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------- cabeceras y respuestas ----------
@pytest.mark.parametrize("ruta", ["/", "/denuncia", "/api/acceso/roles"])
def test_cabeceras_de_seguridad(cli, ruta):
    h = cli.get(ruta).headers
    assert "default-src 'self'" in h.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in h.get("content-security-policy", "")
    assert h.get("x-frame-options") == "DENY"
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("referrer-policy") == "no-referrer"
    assert "server" not in {k.lower() for k in h if h[k].lower().startswith("uvicorn/")}


def test_api_inexistente_sin_traza(cli):
    r = cli.get("/api/no-existe")
    assert r.status_code == 404
    assert "Traceback" not in r.text and "File \"" not in r.text


def test_validacion_sin_traza(cli):
    r = cli.post("/api/acceso/ingresar", json={"usuario": "x" * 500, "clave": "y"})
    assert r.status_code in (400, 422)
    assert "Traceback" not in r.text


# ---------- autenticación ----------
@pytest.mark.parametrize("ruta", ["/api/casos", "/api/ejecutivo", "/api/bitacora", "/api/denuncias", "/api/analisis/fuentes",
                                  "/api/avisos", "/api/panorama-salud"])
def test_sin_sesion_responde_401(cli, ruta):
    assert cli.get(ruta).status_code == 401


def test_token_inventado_responde_401(cli):
    assert cli.get("/api/casos", headers={"Authorization": "Bearer inventado-1234567890"}).status_code == 401


def test_salir_invalida_el_token(cli):
    h = token(cli, "jefe")
    assert cli.get("/api/acceso/yo", headers=h).status_code == 200
    cli.post("/api/acceso/salir", headers=h)
    assert cli.get("/api/acceso/yo", headers=h).status_code == 401


# ---------- autorización por rol (mínimo privilegio) ----------
@pytest.mark.parametrize(("usuario", "metodo", "ruta", "cuerpo"), [
    ("salud", "GET", "/api/casos", None),
    ("salud", "GET", "/api/bitacora", None),
    ("ti", "GET", "/api/denuncias", None),
    ("auditor", "GET", "/api/casos", None),
    ("jefe", "POST", "/api/casos/C1/decision", {"estado": "confirmado", "motivo": "intento sin permiso"}),
    ("auditor", "POST", "/api/reidentificar", {"seudonimo": "P-000000", "motivo": "intento sin permiso de auditoría"}),
])
def test_rol_sin_permiso_responde_403(cli, usuario, metodo, ruta, cuerpo):
    r = cli.request(metodo, ruta, headers=token(cli, usuario), json=cuerpo)
    assert r.status_code == 403, (usuario, ruta, r.status_code, r.text)


# ---------- entradas maliciosas ----------
@pytest.mark.parametrize("ruta", [
    "/..%2f..%2f..%2fetc%2fpasswd",
    "/%2e%2e/%2e%2e/backend/app/config.py",
    "/assets/../../backend/app/config.py",
    "/....//....//etc/passwd",
])
def test_path_traversal_no_expone_archivos(cli, ruta):
    r = cli.get(ruta)
    assert "root:x:" not in r.text
    assert "CLAVE_DEMO" not in r.text and "import os" not in r.text


def test_subida_que_no_es_csv_se_rechaza(cli):
    h = token(cli, "analista")
    archivos = {
        "firewall": ("malicioso.sh", b"#!/bin/sh\necho pwned\n", "text/plain"),
        "sistema_medico": ("datos.csv", b"a,b\n1,2\n", "text/csv"),
    }
    r = cli.post("/api/analisis/subir", headers=h, files=archivos)
    assert r.status_code == 400


def test_fuente_fuera_de_las_carpetas_permitidas(cli):
    h = token(cli, "analista")
    r = cli.post("/api/analisis/desde-carpeta", headers=h,
                 data={"fw_origen": "datos", "fw": "../../etc/passwd", "med_origen": "datos", "med": "../backend/app/config.py"})
    assert r.status_code == 400


def test_denuncia_publica_sin_sesion_y_sin_datos_tecnicos(cli):
    r = cli.post("/api/publico/denuncias", json={"tipo": "venta_de_citas", "descripcion": "Prueba dinámica de seguridad",
                                                  "acepta_privacidad": True})
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {"codigo"}
    assert "ip" not in {k.lower() for k in r.json()}


def test_cors_no_acepta_origenes_ajenos(cli):
    r = cli.options("/api/acceso/roles", headers={"Origin": "https://sitio-malicioso.example",
                                                   "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") not in ("*", "https://sitio-malicioso.example")


def test_portal_publico_limita_el_envio_masivo(cli):
    """Anti-spam: un mismo equipo no puede inundar el canal de denuncias (máximo 5 cada 10 minutos)."""
    codigos = [cli.post("/api/publico/denuncias", json={"tipo": "otro", "descripcion": f"envío masivo {i}",
                                                         "acepta_privacidad": True}).status_code for i in range(7)]
    assert 429 in codigos, codigos
    assert codigos[-1] == 429


# ---------- protección contra fuerza bruta (va al final: bloquea la cuenta 'ti') ----------
def test_bloqueo_tras_cinco_intentos(cli):
    for _ in range(4):
        assert cli.post("/api/acceso/ingresar", json={"usuario": "ti", "clave": "equivocada"}).status_code == 401
    assert cli.post("/api/acceso/ingresar", json={"usuario": "ti", "clave": "equivocada"}).status_code == 423
    r = cli.post("/api/acceso/ingresar", json={"usuario": "ti", "clave": CLAVE})
    assert r.status_code == 423, "Con la cuenta bloqueada no debe entrar ni con la clave correcta."
