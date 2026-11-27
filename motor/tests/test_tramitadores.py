"""Pruebas de detección de tramitadores y sanción progresiva (T22, S8).

Porte/adaptación del TDD de Hackaton al paquete `motor` de sentinel. Cubre:
(a) la muestra `--generar`: 3 tramitadores con 60/40/25 reservas en un mismo
día detectados, 400 dispositivos legítimos con hasta 12 filas NO detectados y
determinismo byte a byte; (b) perfiles normal ≤6 / familiar ≤12 / tramitador
25–100 con el umbral `umbral_reservas_dispositivo_dia: 10` de
config/sanciones.yaml; (c) sanción progresiva SOLO sobre el dispositivo
emisor: 1h → 4h → 24h → 72h con ventana de 30 días, bloqueo activo → HTTP 423
en el simulador sin registrar telemetría, apelación registrada; (d) el módulo
motor.sanciones no expone ninguna función con `id_cita`: jamás se tocan citas
ya reservadas de terceros.
"""
from __future__ import annotations

import csv
import importlib
import inspect
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from motor.sanciones import Sancionador, candidatos, cargar_config, detectar_tramitadores, perfil
from motor.simulador.backend import crear_simulador

REPO = Path(__file__).resolve().parents[2]          # raíz del repositorio sentinel
SCRIPT = REPO / "scripts" / "simulador_chatbot.py"
CONFIG_YAML = REPO / "config" / "sanciones.yaml"

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

TRAMITADORES = (60, 40, 25)
TOPE_LEGITIMO = 12
N_LEGITIMOS = 400
DIA_TRAMITADORES = "2026-10-19"

PETICION = {
    "id_cita": "CIT-SIM-0001",
    "accion": "reservar",
    "canal": "app",
    "referencia_paciente": "PAC-SIM-0001",
    "device_id": "DEV-0123456789abcdef",
    "senal_tecnica": "JA4T_001122334455",
}


def _leer_csv(ruta: Path) -> list[dict[str, str]]:
    with open(ruta, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _generar(out: Path) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--generar", "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, check=False)
    assert proc.returncode == 0, f"--generar falló ({proc.returncode}): {proc.stderr}"
    return proc


@pytest.fixture(scope="module")
def generado(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("tramitadores") / "chatbot_tramitadores_oct2026.csv"
    _generar(out)
    return out


def _filas_dispositivo(device_id: str, reservas: int, dia: str) -> list[dict[str, str]]:
    """filas sintéticas: `reservas` peticiones de `reservar` para un mismo dispositivo/día."""
    filas = []
    for i in range(reservas):
        filas.append({
            "id_evento": f"EV-SINT-{i:06d}",
            "id_cita": f"CIT-SINT-{i:06d}",
            "fecha_hora": f"{dia}T09:{i % 60:02d}:00",
            "accion": "reservar",
            "canal": "app",
            "referencia_paciente": f"PAC-SINT-{i:06d}",
            "id_sesion": "SES-SINT-01",
            "senal_tecnica": "JA4T_sintetica",
            "device_id": device_id,
        })
    return filas


# ---------------------------------------------------------- detección (T22)


def test_tres_tramitadores_60_40_25_en_un_mismo_dia_detectados(generado):
    filas = _leer_csv(generado)
    detectados = detectar_tramitadores(filas)
    assert len(detectados) == 3, detectados
    assert sorted((d["reservas"] for d in detectados), reverse=True) == list(TRAMITADORES)
    assert len({d["fecha"] for d in detectados}) == 1, "los 3 comparten un mismo día"
    for d in detectados:
        assert d["fecha"] == DIA_TRAMITADORES
        assert d["perfil"] == "tramitador"
        assert d["pacientes"] > 20, "un tramitador reserva para pacientes distintos"


def test_dispositivos_legitimos_hasta_12_filas_no_detectados(generado):
    filas = _leer_csv(generado)
    conteos: dict[str, int] = {}
    for fila in filas:
        conteos[fila["device_id"]] = conteos.get(fila["device_id"], 0) + 1
    legitimos = {dev for dev, n in conteos.items() if n <= TOPE_LEGITIMO}
    assert len(legitimos) == N_LEGITIMOS, "faltan dispositivos legítimos"
    assert max(conteos[dev] for dev in legitimos) == TOPE_LEGITIMO

    assert not (legitimos & {d["device_id"] for d in detectar_tramitadores(filas)})
    # además: ningún legítimo cruza siquiera el umbral de 10 reservas/dispositivo/día
    assert not (legitimos & {c["device_id"] for c in candidatos(filas)})


def test_muestra_determinista_byte_a_byte(generado, tmp_path):
    otra = tmp_path / "repeticion.csv"
    _generar(otra)
    assert otra.read_bytes() == generado.read_bytes()


def test_perfiles_normal_familiar_tramitador():
    """Bandas del informe 14.6: normal ≤6, familiar ≤12, tramitador 25–100."""
    assert perfil(0) == "normal"
    assert perfil(6) == "normal"
    assert perfil(7) == "familiar"
    assert perfil(12) == "familiar"
    assert perfil(13) == "observacion"
    assert perfil(24) == "observacion"
    assert perfil(25) == "tramitador"
    assert perfil(100) == "tramitador"


def test_umbral_detecta_candidatos_pero_solo_el_banda_tramitador_se_detecta():
    """El umbral 10 marca candidatos; un dispositivo familiar (≤12/día) no es tramitador."""
    dev_familiar = "DEV-fam111111111111"
    filas = _filas_dispositivo(dev_familiar, reservas=12, dia=DIA_TRAMITADORES)
    assert [c["device_id"] for c in candidatos(filas)] == [dev_familiar]
    assert [c["perfil"] for c in candidatos(filas)] == ["familiar"]
    assert detectar_tramitadores(filas) == []

    dev_normal = "DEV-nor222222222222"
    filas_normales = _filas_dispositivo(dev_normal, reservas=6, dia=DIA_TRAMITADORES)
    assert candidatos(filas_normales) == []

    dev_tram = "DEV-tra333333333333"
    filas_tram = _filas_dispositivo(dev_tram, reservas=25, dia=DIA_TRAMITADORES)
    det = detectar_tramitadores(filas_tram)
    assert [d["device_id"] for d in det] == [dev_tram]
    assert det[0]["reservas"] == 25 and det[0]["fecha"] == DIA_TRAMITADORES


# ------------------------------------------------------- sanción progresiva


def test_sancion_progresiva_1_4_24_72_con_ventana_30_dias(tmp_path):
    sanc = Sancionador(tmp_path / "sanciones.sqlite3")
    dev = "DEV-progressive0001"
    t0 = datetime(2026, 10, 1, 8, 0, 0)
    for paso, horas in enumerate((1, 4, 24, 72)):
        desde = t0 + timedelta(days=paso)
        hasta = sanc.registrar_ofensa(dev, motivo="reserva masiva", ahora=desde)
        assert datetime.fromisoformat(hasta) - desde == timedelta(hours=horas), \
            f"ofensa {paso + 1}: se esperaban {horas} h exactas"
    # quinta ofensa dentro de la ventana: se queda en el tope de 72 h
    desde5 = t0 + timedelta(days=4)
    hasta5 = sanc.registrar_ofensa(dev, motivo="reserva masiva", ahora=desde5)
    assert datetime.fromisoformat(hasta5) - desde5 == timedelta(hours=72)

    filas = sanc.bloqueos(dev)
    assert [f["horas"] for f in filas] == [1, 4, 24, 72, 72]
    assert [f["nivel"] for f in filas] == [1, 2, 3, 4, 5]
    # activo mientras dure; expirado → None
    assert sanc.bloqueo_activo(dev, ahora=desde5 + timedelta(hours=1)) is not None
    assert sanc.bloqueo_activo(dev, ahora=desde5 + timedelta(days=4)) is None


def test_ventana_de_30_dias_reinicia_el_nivel(tmp_path):
    sanc = Sancionador(tmp_path / "sanciones.sqlite3")
    dev = "DEV-window00000001"
    t0 = datetime(2026, 10, 1, 8, 0, 0)
    primera = sanc.registrar_ofensa(dev, motivo="reserva masiva", ahora=t0)
    assert datetime.fromisoformat(primera) - t0 == timedelta(hours=1)
    # 31 días después la ofensa anterior queda fuera de la ventana: vuelve a 1 h
    segunda = sanc.registrar_ofensa(dev, motivo="reserva masiva",
                                    ahora=t0 + timedelta(days=31))
    assert datetime.fromisoformat(segunda) - (t0 + timedelta(days=31)) == timedelta(hours=1)
    assert sanc.ofensas_en_ventana(dev, ahora=t0 + timedelta(days=31)) == 1


def test_bloqueo_activo_responde_423_sin_registrar(tmp_path):
    sanc = Sancionador(tmp_path / "sanciones.sqlite3")
    t0 = datetime(2026, 10, 19, 8, 0, 0)
    hasta = sanc.registrar_ofensa(PETICION["device_id"], motivo="reserva masiva", ahora=t0)

    ruta = tmp_path / "telemetria.csv"
    client = TestClient(crear_simulador(ruta, verificador_bloqueo=sanc.verificador,
                                        reloj=lambda: datetime(2026, 10, 19, 8, 30, 0)))
    resp = client.post("/reservar", json=PETICION)
    assert resp.status_code == 423
    assert resp.json() == {
        "aceptada": False,
        "motivo": "dispositivo_bloqueado",
        "bloqueado_hasta": hasta,
    }
    assert not ruta.exists(), "la petición bloqueada no deja telemetría"

    # expirado el bloqueo (1 h exactas) el mismo dispositivo vuelve a poder reservar
    tarde = TestClient(crear_simulador(ruta, verificador_bloqueo=sanc.verificador,
                                       reloj=lambda: t0 + timedelta(hours=2)))
    resp2 = tarde.post("/reservar", json=PETICION)
    assert resp2.status_code == 200
    assert len(_leer_csv(ruta)) == 1


def test_tramitador_detectado_queda_bloqueado_en_el_simulador(tmp_path, generado):
    filas = _leer_csv(generado)
    detectados = detectar_tramitadores(filas)
    assert len(detectados) == 3

    sanc = Sancionador(tmp_path / "sanciones.sqlite3")
    t0 = datetime(2026, 10, 19, 12, 0, 0)
    for d in detectados:
        sanc.registrar_ofensa(d["device_id"], motivo="reserva masiva", ahora=t0)

    ruta = tmp_path / "telemetria.csv"
    client = TestClient(crear_simulador(ruta, verificador_bloqueo=sanc.verificador,
                                        reloj=lambda: t0))
    bloqueado = client.post("/reservar", json=dict(PETICION, device_id=detectados[0]["device_id"]))
    assert bloqueado.status_code == 423

    legitimo = next(dev for dev in {f["device_id"] for f in filas}
                    if not any(d["device_id"] == dev for d in detectados))
    libre = client.post("/reservar", json=dict(PETICION, device_id=legitimo))
    assert libre.status_code == 200, "la sanción solo afecta al dispositivo emisor"


def test_apelacion_registrada(tmp_path):
    sanc = Sancionador(tmp_path / "sanciones.sqlite3")
    dev = "DEV-appeal00000001"
    t0 = datetime(2026, 10, 19, 8, 0, 0)
    sanc.registrar_ofensa(dev, motivo="reserva masiva", ahora=t0)

    ap = sanc.apelar(dev, motivo="compartía el equipo con su hermana", ahora=t0 + timedelta(minutes=30))
    assert ap["device_id"] == dev and ap["estado"] == "pendiente"
    guardadas = sanc.apelaciones(dev)
    assert len(guardadas) == 1
    assert guardadas[0]["motivo"] == "compartía el equipo con su hermana"
    assert guardadas[0]["fecha"] == (t0 + timedelta(minutes=30)).isoformat()

    tipos = [b["tipo"] for b in sanc.bitacora(dev)]
    assert "ofensa" in tipos and "bloqueo" in tipos and "apelacion" in tipos
    assert "aviso_dispositivo_compartido" in tipos, "bitácora debe avisar del equipo compartido"
    # la apelación registrada no levanta el bloqueo sola: requiere revisión humana
    assert sanc.bloqueo_activo(dev, ahora=t0 + timedelta(minutes=40)) is not None


def test_esquema_append_only(tmp_path):
    """ofensas/bloqueos/apelaciones/bitácora: solo-agregado (triggers abortan UPDATE/DELETE)."""
    ruta = tmp_path / "sanciones.sqlite3"
    sanc = Sancionador(ruta)
    t0 = datetime(2026, 10, 19, 8, 0, 0)
    dev = "DEV-append00000001"
    sanc.registrar_ofensa(dev, motivo="reserva masiva", ahora=t0)
    sanc.apelar(dev, motivo="error de digitación", ahora=t0)

    conn = sqlite3.connect(ruta)
    try:
        for tabla in ("ofensas", "bloqueos", "apelaciones", "bitacora"):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f"UPDATE {tabla} SET rowid = rowid")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f"DELETE FROM {tabla}")
    finally:
        conn.close()


# ------------------------------------------------------------- configuración


def test_config_leida_de_config_sanciones_yaml():
    archivo = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))
    cfg = cargar_config()
    assert archivo["umbral_reservas_dispositivo_dia"] == cfg.umbral_reservas_dispositivo_dia == 10
    assert tuple(archivo["bloqueo_horas"]) == cfg.bloqueo_horas == (1, 4, 24, 72)
    assert archivo["ventana_ofensas_dias"] == cfg.ventana_ofensas_dias == 30
    assert cfg.normal_max_reservas_dia == 6
    assert cfg.familiar_max_reservas_dia == 12
    assert cfg.tramitador_min_reservas_dia == 25
    assert cfg.tramitador_max_reservas_dia == 100


def test_cero_funciones_con_id_cita():
    """S8: el módulo de sanciones jamás expone funciones con `id_cita`
    (nada de sancionar sobre citas ya reservadas de terceros)."""
    import motor.sanciones as pkg

    base = Path(pkg.__file__).parent
    for py in sorted(base.glob("*.py")):
        mod = importlib.import_module(f"motor.sanciones.{py.stem}")
        fuente = Path(mod.__file__).read_text(encoding="utf-8")
        assert "id_cita" not in fuente, f"{mod.__name__} menciona id_cita"

        def _sin_id_cita(obj, etiqueta):
            if isinstance(obj, (staticmethod, classmethod)):
                obj = obj.__func__
            if inspect.isfunction(obj):
                assert "id_cita" not in inspect.signature(obj).parameters, \
                    f"{mod.__name__}.{etiqueta} expone id_cita"

        for nombre, obj in vars(mod).items():
            if getattr(obj, "__module__", None) != mod.__name__:
                continue
            _sin_id_cita(obj, nombre)
            if inspect.isclass(obj):
                for mnombre, mobj in vars(obj).items():
                    _sin_id_cita(mobj, f"{obj.__name__}.{mnombre}")
