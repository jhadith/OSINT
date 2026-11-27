"""Los umbrales viven en rules/*.yml (S3/S12): el motor los lee de ahí, no los define en su código.

- Cada parámetro calibrable existe en un archivo de rules/ y config.py expone exactamente ese valor.
- config.py no contiene asignaciones literales de ningún umbra (barrido de fuentes).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from motor import config

REGLAS = Path(__file__).resolve().parents[2] / "rules"   # raíz del repo/rules
ARCHIVOS_ESPERADOS = {"firewall.yml", "sistema_medico.yml", "correlacion.yml", "ml.yml", "agendamiento.yml"}

# Claves que el loader convierte a tipos de Python (YAML da listas)
A_CONJUNTO = {"PUERTOS_SSH", "CITAS_REDES_OCULTAS"}
A_TUPLA = {"DESFASES_HORAS"}


def _yaml_umbrales() -> dict:
    todos = {}
    for ruta in sorted(REGLAS.glob("*.yml")):
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        assert isinstance(datos, dict), f"{ruta.name}: se esperaba un mapeo nombre → valor"
        for k, v in datos.items():
            assert k not in todos, f"umbra duplicado entre archivos de rules/: {k}"
            todos[k] = v
    return todos


def test_existen_los_archivos_de_umbrales():
    encontrados = {p.name for p in REGLAS.glob("*.yml")}
    assert ARCHIVOS_ESPERADOS <= encontrados, f"faltan: {ARCHIVOS_ESPERADOS - encontrados}"


def test_config_expone_el_valor_del_yaml():
    for nombre, valor in _yaml_umbrales().items():
        esperado = set(valor) if nombre in A_CONJUNTO else tuple(valor) if nombre in A_TUPLA else valor
        assert hasattr(config, nombre), f"config.py no expone {nombre}"
        assert getattr(config, nombre) == esperado, f"{nombre}: config={getattr(config, nombre)!r} yaml={esperado!r}"


def test_sin_umbrales_como_literal_en_el_codigo_del_motor():
    fuentes = [Path(config.__file__)]
    fuentes += sorted((Path(config.__file__).parent / n) for n in
                      ("reglas_fw.py", "reglas_med.py", "correlacion.py", "ml.py"))
    for nombre in _yaml_umbrales():
        for fuente in fuentes:
            texto = fuente.read_text(encoding="utf-8")
            assert not re.search(rf"^{re.escape(nombre)}\s*=", texto, re.M), \
                f"{nombre} sigue definido como literal en {fuente.name}"


def test_sin_ips_de_datos_en_config():
    """S12: ni SERVIDOR ni SEGMENTO viven en el código Python; están en rules/firewall.yml."""
    texto = Path(config.__file__).read_text(encoding="utf-8")
    assert not re.search(r'"10\.\d+\.\d+\.\d+"', texto), "config.py contiene una IP de datos literal"
    assert config.SERVIDOR and config.SEGMENTO_SERVIDOR   # pero siguen disponibles para el motor
