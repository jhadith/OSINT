"""Pruebas del motor. Corren sobre datos sintéticos generados al vuelo (tests/generador.py), nunca sobre los datasets.
  pytest -q
Para probar además con extractos reales en tu equipo:  set SENTINEL_EXTRACTOS=carpeta_con_fw.csv_y_med.csv
"""
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from motor import pipeline
from motor.correlacion import misma_persona
from motor.ventanas import episodios
from tests import generador as gen

CAMPOS = {"id": str, "caso": (str, type(None)), "regla": str, "titulo": str, "gravedad": str, "puntaje": int,
          "fuente": str, "inicio": str, "fin": str, "ip_origen": str, "cuenta": str, "usuario_firewall": str,
          "persona": str, "tecnicas": list, "eventos_firewall": int, "eventos_sistema_medico": int, "resumen": str,
          "acciones": list, "riesgo": str, "cid": list, "linea": list}


@pytest.fixture(scope="session")
def corrida(tmp_path_factory):
    base = tmp_path_factory.mktemp("motor")
    fw, med = gen.generar(base / "datos", 120_000, 100_000)
    r = pipeline.ejecutar(fw, med, base / "salidas", restringido=base / "restringido", tam=50_000)
    return base, r


def _por_titulo(alertas, texto):
    return [a for a in alertas if texto in a["titulo"]]


def test_detecta_los_cuatro_ataques(corrida):
    _, r = corrida
    a = r["alertas"]
    esperado = {"fuga de datos por SSH": "fuga", "Cuenta fantasma": "fantasma", "Fuerza bruta": "fuerza_bruta",
                "Escaneo": "escaneo"}
    for titulo, clave in esperado.items():
        x = _por_titulo(a, titulo)
        assert len(x) == 1, titulo
        _, _, ip, cuenta = gen.ATACANTES[clave]
        assert x[0]["ip_origen"] == ip and x[0]["cuenta"] == cuenta
        assert x[0]["fuente"] == "correlacion" and x[0]["caso"]


def test_gravedad_y_sin_falsos_positivos_graves(corrida):
    _, r = corrida
    graves = {a["titulo"]: a["gravedad"] for a in r["alertas"] if a["gravedad"] in ("Crítica", "Alta")}
    assert sorted(graves.values()) == ["Alta", "Alta", "Crítica", "Crítica"]
    assert graves["Cuenta fantasma con descarga de datos"] == "Crítica"
    assert graves["Posible fuga de datos por SSH"] == "Crítica"


def test_cuenta_fantasma_alinea_el_reloj(corrida):
    _, r = corrida
    x = _por_titulo(r["alertas"], "Cuenta fantasma")[0]
    assert x["desfase_reloj_h"] == -12 and x["inicio"] == "2026-10-24 10:40:00"
    assert "T1021.004" in x["tecnicas"] and "T1078" in x["tecnicas"]


def test_hallazgos_generales(corrida):
    _, r = corrida
    titulos = {a["titulo"] for a in r["alertas"]}
    assert "Servicios sin cifrado permitidos (Telnet, SMBv1, NetBIOS)" in titulos
    assert "Cuentas usadas por muchas personas" in titulos


def test_contrato_de_salida(corrida):
    base, _ = corrida
    alertas = json.loads((base / "salidas" / "alertas.json").read_text(encoding="utf-8"))
    for a in alertas:
        for campo, tipo in CAMPOS.items():
            assert isinstance(a[campo], tipo), campo
        assert re.fullmatch(r"A-[0-9A-F]{8}", a["id"])
        assert a["gravedad"] in ("Crítica", "Alta", "Media", "Baja") and 1 <= a["puntaje"] <= 25
        assert a["fuente"] in ("firewall", "sistema_medico", "correlacion")
        pd.to_datetime(a["inicio"], format="%Y-%m-%d %H:%M:%S")
        assert re.fullmatch(r"R[1-9]", a["riesgo"])
    assert len({a["id"] for a in alertas}) == len(alertas)
    res = json.loads((base / "salidas" / "resumen_motor.json").read_text(encoding="utf-8"))
    assert {"periodo", "generado", "registros", "tiempo_analisis_min", "cuentas_sospechosas", "conexiones_inseguras",
            "brechas_hipaa"} <= set(res)
    ml = json.loads((base / "salidas" / "ml.json").read_text(encoding="utf-8"))
    assert ml["usuarios_firewall"] and ml["cuentas_sistema_medico"]


def test_privacidad_sin_nombres_en_salidas(corrida):
    base, _ = corrida
    texto = "".join(f.read_text(encoding="utf-8") for f in (base / "salidas").glob("*.json"))
    for usuario, nombre, _, _ in gen.ATACANTES.values():
        assert usuario not in texto
        assert nombre not in texto
    assert not [u for u in gen.usuarios_fw() if f'"{u}"' in texto or f" {u} " in texto]
    assert (base / "restringido" / "tabla_reidentificacion.csv").exists()
    assert not list((base / "salidas").glob("*reidentificacion*"))


def test_sin_textos_institucionales(corrida):
    base, _ = corrida
    texto = "".join(f.read_text(encoding="utf-8") for f in (base / "salidas").glob("*.json"))
    assert "IESS" not in texto.upper()


def test_datos_mal_formados(tmp_path):
    fw = gen.firewall(3000).drop(columns=["Protocolo"])
    fw.loc[:9, "Fecha_Generacion"] = "fecha rota"
    fw.loc[10:19, "Puerto_Destino"] = "abc"
    fw.to_csv(tmp_path / "fw.csv", index=False)
    med = gen.sistema_medico(3000)
    med.loc[:4, "FECHA_EJECUTA_EVENTO"] = "2026XX01"
    med.to_csv(tmp_path / "med.csv", index=False, encoding="cp1252")
    with open(tmp_path / "fw.csv", "a", encoding="utf-8") as f:
        f.write("linea,con,columnas,de,mas,1,2,3,4,5,6,7\n")
    r = pipeline.ejecutar(tmp_path / "fw.csv", tmp_path / "med.csv", tmp_path / "s", con_ml=False,
                          restringido=tmp_path / "r")
    cal = r["resumen"]["calidad"]
    assert cal["filas_fecha_invalida"] >= 15 and "Protocolo" in cal["columnas_faltantes"]


def test_episodios():
    t = np.array([0, 1, 2, 3, 100, 101, 102, 500])
    assert episodios(t, 5, 3) == [(0, 3), (4, 6)]
    assert episodios(t, 5, 10) == []


def test_misma_persona():
    assert misma_persona("ivan.prieto", "PRIETO ESTÉVEZ IVÁN ARTURO")
    assert not misma_persona("ivan.prieto", "PRIETO ESTEVEZ CARLOS")
    assert not misma_persona("admin", "ADMIN ADMIN")


@pytest.mark.skipif(not os.environ.get("SENTINEL_EXTRACTOS"), reason="sin extractos reales en este equipo")
def test_extractos_reales(tmp_path):
    d = Path(os.environ["SENTINEL_EXTRACTOS"])
    r = pipeline.ejecutar(d / "fw.csv", d / "med.csv", tmp_path / "s", restringido=tmp_path / "r")
    casos = {a["ip_origen"]: a for a in r["alertas"] if a["caso"]}
    assert set(casos) == {"10.10.100.10", "10.10.100.20", "10.10.100.40", "10.10.100.50"}
