"""Pruebas de generalidad (T6, S6b · T17 Hackaton / S12): mismo patrón, otros datos → mismos hallazgos.

S12 (verbatim del usuario): "tenemos que generar otros cvs iguales con diferentes datos y nuestro producto
tiene que detectar los mismos patrones, entender los mismos, validar lo mismo, debe de ser infalible en todo
sentido".

En Hackaton la variante salía del CLI (--semilla 77 --ip-interno 10.99.50 --mes 2026-09); el generador de
sentinel no acepta esos parámetros (RED observado: TypeError en generar()) y su semilla solo cambia el
ruido —las IPs/fechas/cuentas de los ataques son constantes (ATACANTES, INICIO)—, así que la variante se
construye DENTRO de este test con transformaciones deterministas sobre los CSV de tests/generador.py:

  * Otras IPs: todo origen del segmento del servidor (10.10.100.x) pasa a otro segmento (10.99.50.x).
    IP_Destino no se toca: es la IP del servidor médico, que es el umbral SERVIDOR de rules/firewall.yml
    (la regla protege ese servidor), no un valor del hallazgo.
  * Otras fechas: +DESPLAZO_DIAS en las dos fuentes; el desfase de reloj de 12 h del caso fantasma se
    conserva porque ambas se corrigen igual.
  * Otras cuentas: renombrado biyectivo y determinista de todas las cuentas del sistema médico.
  * Filas reordenadas: shuffle determinista de ambas fuentes.

Se exige: (a) las reglas detectan los MISMOS tipos de hallazgo que con los datos originales —rafaga_ssh,
fuerza_bruta, escaneo, servicios_inseguros y cuentas compartidas/extracción— sin ningún valor literal de
IP ni de cuenta en las aserciones; (b) dos corridas sobre la misma variante producen salidas idénticas.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from motor import config, pipeline
from tests import generador as gen

N_FW, N_MED = 120_000, 100_000          # mismos tamaños calibrados que test_motor
DESPLAZO_DIAS = 13
SEG_NUEVO = "10.99.50."                 # otro segmento para los orígenes
PREFIJO_CUENTA = "CTA"                  # prefijo de las cuentas renumeradas (disjoint de las originales)
SHUFFLE_FW, SHUFFLE_MED = 4242, 4243    # shuffle determinista de cada fuente

# Los tipos de hallazgo que S12 exige que sigan apareciendo con otros datos:
# ráfaga/extracción SSH, fuerza bruta, escaneo, servicios inseguros y cuentas genéricas (compartidas).
TIPOS_EXIGIDOS = {"rafaga_ssh", "fuerza_bruta", "escaneo", "servicios_inseguros", "cuentas_compartidas"}


def _leer(par: tuple[Path, Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    fw, med = par
    return (pd.read_csv(fw, dtype=str, keep_default_na=False),
            pd.read_csv(med, dtype=str, keep_default_na=False, encoding="cp1252"))


def _variante(fw_csv: Path, med_csv: Path, salida: Path) -> tuple[Path, Path]:
    """La variante S12: mismos patrones con otros datos, por transformaciones deterministas."""
    fw, med = _leer((fw_csv, med_csv))
    # otras IPs: el segmento del servidor como origen se renumera a otro segmento (el destino servidor no
    # se toca: su IP es el umbral SERVIDOR de rules/firewall.yml, no un valor del hallazgo)
    fw["IP_Origen"] = fw["IP_Origen"].str.replace(rf"^{re.escape(config.SEGMENTO_SERVIDOR)}", SEG_NUEVO,
                                                  regex=True)
    # otras fechas: corrididas en las dos fuentes, conservando el desfase de reloj entre ellas
    fw["Fecha_Generacion"] = (pd.to_datetime(fw["Fecha_Generacion"], format="%Y-%m-%d %H:%M:%S")
                              + pd.Timedelta(days=DESPLAZO_DIAS)).dt.strftime("%Y-%m-%d %H:%M:%S")
    med["FECHA_EJECUTA_EVENTO"] = (pd.to_datetime(med["FECHA_EJECUTA_EVENTO"], format="%Y%m%d")
                                   + pd.Timedelta(days=DESPLAZO_DIAS)).dt.strftime("%Y%m%d")
    # otras cuentas: mapeo biyectivo y determinista sobre todas las cuentas del sistema médico
    cuentas = sorted(med["USUARIO_EJECUTA_EVENTO"].unique())
    mapa = {c: f"{PREFIJO_CUENTA}{i:07d}" for i, c in enumerate(cuentas)}
    med["USUARIO_EJECUTA_EVENTO"] = med["USUARIO_EJECUTA_EVENTO"].map(mapa)
    # filas reordenadas
    fw = fw.sample(frac=1, random_state=SHUFFLE_FW).reset_index(drop=True)
    med = med.sample(frac=1, random_state=SHUFFLE_MED).reset_index(drop=True)
    salida.mkdir(parents=True, exist_ok=True)
    fw_out, med_out = salida / "fw.csv", salida / "med.csv"
    fw.to_csv(fw_out, index=False)
    med.to_csv(med_out, index=False, encoding="cp1252")   # el original viene en cp1252
    return fw_out, med_out


@pytest.fixture(scope="module")
def rutas(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("generalidad")
    fw, med = gen.generar(tmp / "originales", N_FW, N_MED)
    return {
        "original": (fw, med),
        "variante": _variante(fw, med, tmp / "variante"),
        "salida_original": tmp / "salidas_original",
        "salida_variante": tmp / "salidas_variante",
        "salida_variante_repetida": tmp / "salidas_variante_repetida",
        "restringido_original": tmp / "restringido_original",
        # MISMA carpeta para las dos corridas de la variante: comparten la sal de los seudónimos
        "restringido_variante": tmp / "restringido_variante",
    }


@pytest.fixture(scope="module")
def corrida_original(rutas):
    return pipeline.ejecutar(*rutas["original"], rutas["salida_original"],
                             restringido=rutas["restringido_original"])


@pytest.fixture(scope="module")
def corrida_variante(rutas):
    return pipeline.ejecutar(*rutas["variante"], rutas["salida_variante"],
                             restringido=rutas["restringido_variante"])


@pytest.fixture(scope="module")
def corrida_variante_repetida(rutas):
    return pipeline.ejecutar(*rutas["variante"], rutas["salida_variante_repetida"],
                             restringido=rutas["restringido_variante"])


def _tipos(corrida: dict) -> list[str]:
    """Tipos de hallazgo por regla. Las alertas solo-ML (tipo 'ml') no son reglas: quedan fuera."""
    return sorted(a["tipo"] for a in corrida["alertas"] if a["tipo"] != "ml")


def test_la_variante_realmente_difiere(rutas):
    """Otros datos: sin orígenes en el segmento del servidor, fechas corrididas y cuentas renombradas."""
    fw_o, med_o = _leer(rutas["original"])
    fw_v, med_v = _leer(rutas["variante"])
    assert len(fw_o) == len(fw_v) and len(med_o) == len(med_v)      # mismas filas: solo cambian valores
    # otras IPs de origen
    assert fw_o["IP_Origen"].str.startswith(config.SEGMENTO_SERVIDOR).any()
    assert not fw_v["IP_Origen"].str.startswith(config.SEGMENTO_SERVIDOR).any()
    assert fw_v["IP_Origen"].str.startswith(SEG_NUEVO).any()
    # otras fechas: exactamente DESPLAZO_DIAS en las dos fuentes
    for col, fmt in (("Fecha_Generacion", None), ("FECHA_EJECUTA_EVENTO", "%Y%m%d")):
        o = pd.to_datetime((fw_o if col == "Fecha_Generacion" else med_o)[col], format=fmt)
        v = pd.to_datetime((fw_v if col == "Fecha_Generacion" else med_v)[col], format=fmt)
        assert (v.min() - o.min()) == pd.Timedelta(days=DESPLAZO_DIAS)
        assert (v.max() - o.max()) == pd.Timedelta(days=DESPLAZO_DIAS)
    # otras cuentas: biyección, ninguna cuenta original queda
    cuentas_o = set(med_o["USUARIO_EJECUTA_EVENTO"])
    cuentas_v = set(med_v["USUARIO_EJECUTA_EVENTO"])
    assert cuentas_o and len(cuentas_v) == len(cuentas_o) and not (cuentas_o & cuentas_v)
    assert all(c.startswith(PREFIJO_CUENTA) for c in cuentas_v)
    # filas reordenadas: el orden de una columna que la transformación no cambia ya no coincide
    assert fw_o["Aplicacion"].tolist() != fw_v["Aplicacion"].tolist()


def test_mismos_tipos_de_hallazgo(corrida_original, corrida_variante):
    """(a) Con otros datos, las reglas detectan los mismos tipos de hallazgo, ni más ni menos (S12)."""
    assert _tipos(corrida_variante) == _tipos(corrida_original)
    assert TIPOS_EXIGIDOS <= set(_tipos(corrida_variante))
    # la extracción masiva del sistema médico sigue formando parte del caso de fuga
    assert any("extraccion_masiva" in a["regla"] for a in corrida_variante["alertas"])
    # los 4 ataques plantados quedan confirmados por ambas fuentes en las dos variantes de datos
    casos_o = [a for a in corrida_original["alertas"] if a["caso"]]
    casos_v = [a for a in corrida_variante["alertas"] if a["caso"]]
    assert len(casos_v) == len(casos_o) == 4


def test_determinismo_dos_corridas_identicas(rutas, corrida_variante, corrida_variante_repetida):
    """(b) Determinismo: mismo CSV + misma sal ⇒ salidas idénticas byte a byte entre dos corridas."""
    d1, d2 = rutas["salida_variante"], rutas["salida_variante_repetida"]
    assert (d1 / "alertas.json").read_bytes() == (d2 / "alertas.json").read_bytes()
    assert (d1 / "ml.json").read_bytes() == (d2 / "ml.json").read_bytes()
    # resumen_motor.json se excluye: su `generado` y `tiempo_analisis_min` son el reloj de la corrida.
