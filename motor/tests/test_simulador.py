"""Pruebas del simulador de chatbot y del fingerprint de dispositivo (T21, S8).

Porte/adaptación del TDD de Hackaton (`tests/test_simulador.py`, RED allí) al
paquete `motor` de sentinel. Cubre: (a) fingerprint — un dict fijo de señal
produce un id determinista con formato DEV-<16hex> y señales distintas producen
ids distintos; (b) backend — POST /reservar registra telemetría con las 9
columnas, el verificador de bloqueo inyectable responde 423 con motivo sin
registrar la petición, un verificador que devuelve None acepta y sin
verificador siempre se acepta; (c) página estática en web/simulador/ servida en
local, sin CDN; (d) CLI --generar — device_id válido en cada fila, salida por
defecto fuera de datos/, y las muestras existentes de datos_ejemplo/ quedan
byte-idénticas tras ejecutarlo.

IzyBot (chatbot real del IESS) no se toca: esto es una SIMULACIÓN propia.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]          # raíz del repositorio sentinel
SCRIPT = REPO / "scripts" / "simulador_chatbot.py"
MUESTRAS_EXISTENTES = sorted((REPO / "datos_ejemplo").glob("*.csv"))
MUESTRA_NUEVA = REPO / "motor" / "datos_ejemplo" / "chatbot_tramitadores_oct2026.csv"

COLUMNAS = [
    "id_evento",
    "id_cita",
    "fecha_hora",
    "accion",
    "canal",
    "referencia_paciente",
    "id_sesion",
    "senal_tecnica",
    "device_id",
]

# Señal fija del fingerprint: mismo dict -> mismo id, orden irrelevante.
SENAL_FIJA = {
    "canvas": "9f86d081884c7d659a2feaa0c55ad015",
    "devicePixelRatio": 1,
    "screen": "1920x1080x24",
    "timezone": -300,
    "userAgent": "Mozilla/5.0 (X11; Linux x86_64) SentinelSim/1.0",
    "webgl": "Intel(R) UHD Graphics 620",
}

PETICION = {
    "id_cita": "CIT-SIM-0001",
    "accion": "reservar",
    "canal": "app",
    "referencia_paciente": "PAC-SIM-0001",
    "device_id": "DEV-0123456789abcdef",
    "senal_tecnica": "JA4T_001122334455",
}

PATRON_DEVICE = re.compile(r"DEV-[0-9a-f]{16}")


def reloj_fijo() -> datetime:
    """Reloj inyectable: la telemetría debe registrar exactamente este instante."""
    return datetime(2026, 10, 19, 8, 30, 0)


def _leer_csv(ruta: Path) -> list[dict[str, str]]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------- fingerprint


def test_fingerprint_dict_fijo_es_determinista_y_tiene_formato():
    from motor.simulador.fingerprint import device_id

    primero = device_id(SENAL_FIJA)
    invertido = dict(reversed(list(SENAL_FIJA.items())))
    assert primero == device_id(invertido)
    assert primero == device_id(dict(SENAL_FIJA))
    assert PATRON_DEVICE.fullmatch(primero), primero
    assert primero == "DEV-" + hashlib.sha256(
        json.dumps(SENAL_FIJA, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def test_fingerprint_senales_distintas_producen_ids_distintos():
    from motor.simulador.fingerprint import device_id

    base = device_id(SENAL_FIJA)
    assert device_id(dict(SENAL_FIJA, timezone=300)) != base
    assert device_id(dict(SENAL_FIJA, canvas="0" * 16)) != base
    assert device_id({k: v for k, v in SENAL_FIJA.items() if k != "webgl"}) != base


# -------------------------------------------------------------------- backend


def _app(ruta: Path, verificador=None):
    from motor.simulador.backend import crear_simulador

    return crear_simulador(ruta, verificador_bloqueo=verificador, reloj=reloj_fijo)


def test_reservar_registra_telemetria_con_las_nueve_columnas(tmp_path):
    ruta = tmp_path / "telemetria.csv"
    client = TestClient(_app(ruta))

    primera = client.post("/reservar", json=PETICION)
    assert primera.status_code == 200
    assert primera.json() == {"aceptada": True}

    # senal_tecnica es opcional en el contrato del payload.
    segunda = client.post(
        "/reservar", json={k: v for k, v in PETICION.items() if k != "senal_tecnica"}
    )
    assert segunda.status_code == 200

    filas = _leer_csv(ruta)
    assert list(filas[0]) == COLUMNAS
    assert len(filas) == 2
    fila = filas[0]
    assert fila["id_evento"] == "EV-SIM-000001"
    assert fila["id_cita"] == "CIT-SIM-0001"
    assert fila["fecha_hora"] == "2026-10-19T08:30:00"
    assert fila["accion"] == "reservar"
    assert fila["canal"] == "app"
    assert fila["referencia_paciente"] == "PAC-SIM-0001"
    assert fila["id_sesion"].startswith("SES-SIM-")
    assert fila["senal_tecnica"] == "JA4T_001122334455"
    assert fila["device_id"] == PETICION["device_id"]
    assert filas[1]["senal_tecnica"] == ""
    assert filas[1]["id_evento"] == "EV-SIM-000002"


def test_verificador_de_bloqueo_responde_423_sin_registrar(tmp_path):
    ruta = tmp_path / "telemetria.csv"
    hasta = datetime(2026, 10, 19, 9, 30, 0).isoformat()
    llamadas: list[tuple[str, datetime]] = []

    def verificador(device_id: str, ahora: datetime) -> str | None:
        llamadas.append((device_id, ahora))
        return hasta

    client = TestClient(_app(ruta, verificador=verificador))
    resp = client.post("/reservar", json=PETICION)
    assert resp.status_code == 423
    assert resp.json() == {
        "aceptada": False,
        "motivo": "dispositivo_bloqueado",
        "bloqueado_hasta": hasta,
    }
    assert llamadas == [(PETICION["device_id"], reloj_fijo())]
    # la petición rechazada no deja telemetría
    assert not ruta.exists()


def test_verificador_que_devuelve_none_acepta(tmp_path):
    ruta = tmp_path / "telemetria.csv"

    def verificador(device_id: str, ahora: datetime) -> str | None:
        return None

    client = TestClient(_app(ruta, verificador=verificador))
    resp = client.post("/reservar", json=PETICION)
    assert resp.status_code == 200
    assert resp.json() == {"aceptada": True}
    assert len(_leer_csv(ruta)) == 1


def test_sin_verificador_inyectado_siempre_acepta(tmp_path):
    ruta = tmp_path / "telemetria.csv"
    client = TestClient(_app(ruta))
    for _ in range(3):
        resp = client.post("/reservar", json=PETICION)
        assert resp.status_code == 200
        assert resp.json() == {"aceptada": True}
    assert len(_leer_csv(ruta)) == 3


def test_telemetria_tambien_se_puede_registrar_en_jsonl(tmp_path):
    ruta = tmp_path / "telemetria.jsonl"
    client = TestClient(_app(ruta))
    assert client.post("/reservar", json=PETICION).json() == {"aceptada": True}
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 1
    fila = json.loads(lineas[0])
    assert list(fila) == COLUMNAS
    assert fila["device_id"] == PETICION["device_id"]


# ------------------------------------------------- página estática en local


def test_pagina_del_simulador_se_sirve_en_local(tmp_path):
    client = TestClient(_app(tmp_path / "telemetria.csv"))
    resp = client.get("/simulador/")
    assert resp.status_code == 200
    assert "fingerprint.js" in resp.text
    js = client.get("/simulador/fingerprint.js")
    assert js.status_code == 200
    assert "DEV-" in js.text


def test_pagina_sin_cdn_ni_dependencias_externas():
    """S8: fingerprint en JS local, sin CDN (nada de http(s):// en la página)."""
    web = REPO / "web" / "simulador"
    pagina = (web / "index.html").read_text(encoding="utf-8")
    script = (web / "fingerprint.js").read_text(encoding="utf-8")
    assert "fingerprint.js" in pagina
    for texto in (pagina, script):
        assert not re.search(r"https?://", texto), "la página no debe cargar nada de la red"
        assert "cdn" not in texto.lower()


# ----------------------------------------------------------------------- CLI


def _generar(out: Path) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--generar", "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, check=False)
    assert proc.returncode == 0, f"--generar falló ({proc.returncode}): {proc.stderr}"
    return proc


@pytest.fixture(scope="module")
def generado(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("simulador") / MUESTRA_NUEVA.name
    _generar(out)
    return out


def test_generar_tiene_device_id_valido_en_cada_fila(generado):
    filas = _leer_csv(generado)
    assert filas, "el CSV generado está vacío"
    assert list(filas[0]) == COLUMNAS
    for fila in filas:
        assert PATRON_DEVICE.fullmatch(fila["device_id"]), fila


def test_cli_nunca_toca_las_muestras_existentes(tmp_path):
    """El CLI escribe su propia muestra; los CSV de datos_ejemplo/ quedan intactos."""
    assert MUESTRAS_EXISTENTES, "faltan los CSV de datos_ejemplo/"
    antes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in MUESTRAS_EXISTENTES}
    _generar(tmp_path / "aislada.csv")
    despues = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in MUESTRAS_EXISTENTES}
    assert antes == despues, "el CLI sobrescribió una muestra existente"
    texto = SCRIPT.read_text(encoding="utf-8")
    for p in MUESTRAS_EXISTENTES:
        assert p.name not in texto, f"el CLI no debe referenciar {p.name}"


def test_salida_por_defecto_fuera_de_datos():
    """--generar sin --out escribe en motor/datos_ejemplo (o motor/salidas), nunca en datos/."""
    spec = importlib.util.spec_from_file_location("simulador_chatbot_cli", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    salida = Path(modulo.DEFECTO_SALIDA).resolve()
    assert salida.name == MUESTRA_NUEVA.name
    en_permitido = salida.is_relative_to(REPO / "motor" / "datos_ejemplo") or \
        salida.is_relative_to(REPO / "motor" / "salidas")
    assert en_permitido, f"salida por defecto fuera de las carpetas permitidas: {salida}"
    assert not salida.is_relative_to(REPO / "datos"), "nunca en datos/ (CSVs del reto)"
    assert not salida.is_relative_to(REPO / "datos_ejemplo"), "no tocar las muestras de la raíz"
    assert MUESTRA_NUEVA != REPO / "datos_ejemplo" / MUESTRA_NUEVA.name


def test_cli_expone_generar_y_servir():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                          capture_output=True, text=True, cwd=REPO, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "--generar" in proc.stdout and "--servir" in proc.stdout
