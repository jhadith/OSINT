"""Muestra determinista del simulador de chatbot: 400 dispositivos legítimos y 3 tramitadores."""
import csv
from collections import Counter

from motor.simulador import COLUMNAS, generador


def test_filas_deterministas_y_ordenadas():
    a, b = generador.generar_filas(), generador.generar_filas()
    assert a == b
    claves = [(f["fecha_hora"], f["device_id"], f["id_sesion"], f["id_cita"]) for f in a]
    assert claves == sorted(claves)


def test_legitimos_bajo_el_umbral_y_tramitadores_encima():
    filas = generador.generar_filas()
    reservas = Counter((f["device_id"], f["fecha_hora"][:10]) for f in filas if f["accion"] == "reservar")
    tram = {f["device_id"] for f in filas if f["id_sesion"].startswith("SES-SIM-TRAM")}
    assert len(tram) == len(generador.TRAMITADORES)
    for (dev, _dia), n in reservas.items():
        assert n >= 25 if dev in tram else n <= 6
    pacientes_tram = [f["referencia_paciente"] for f in filas if f["device_id"] in tram]
    assert len(pacientes_tram) == len(set(pacientes_tram)) == sum(generador.TRAMITADORES)
    assert {f["accion"] for f in filas} >= {"reservar", "confirmar", "modificar", "cancelar", "no_show"}


def test_generar_muestra_escribe_el_csv_con_las_columnas(tmp_path):
    ruta = tmp_path / "sub" / "muestra.csv"
    n = generador.generar_muestra(ruta)
    with open(ruta, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert n == len(filas) > 400
    assert list(filas[0]) == COLUMNAS and filas[0]["id_evento"] == "EV-SIM-000001"
    assert all(r["device_id"] for r in filas)
