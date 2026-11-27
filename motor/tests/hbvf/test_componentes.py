"""T4/S5: los 4 componentes mínimos del informe 14.4 existen y el catálogo JSON parsea."""
import json
from pathlib import Path

import motor.hbvf as hbvf
from motor import agendamiento

PKG = Path(hbvf.__file__).parent
MINIMOS = ("pattern_catalog.json", "behavior_validation.py", "mitigation_engine.py", "model_evaluation.py")
CLAVES_PATRON = {"id", "nombre", "familia", "fuente", "contexto_legitimo", "validacion"}
ESTADOS = {"presente", "ausente", "desconocido", "explicado"}


def _catalogo() -> dict:
    return json.loads((PKG / "pattern_catalog.json").read_text(encoding="utf-8"))


def test_los_cuatro_componentes_minimos_y_el_almacen_existen():
    for nombre in MINIMOS:
        assert (PKG / nombre).is_file(), f"falta {nombre}"
    assert (PKG / "almacen.py").is_file(), "falta almacen.py"


def test_los_modulos_importan_y_exponen_su_superficie():
    from motor.hbvf import almacen, behavior_validation, mitigation_engine, model_evaluation

    assert callable(behavior_validation.validar)
    assert callable(mitigation_engine.recomendaciones)
    assert callable(model_evaluation.metricas)
    assert callable(almacen.crear_esquema)


def test_catalogo_json_parsea_con_las_claves_esperadas():
    datos = _catalogo()
    assert {"patrones", "peso_familia", "estados"} <= set(datos)
    assert [p["id"] for p in datos["patrones"]] == [f"HG-0{i}" for i in range(1, 8)]
    for p in datos["patrones"]:
        assert set(p) == CLAVES_PATRON, p["id"]
    familias = {p["familia"] for p in datos["patrones"]}
    assert familias == {"volumen", "ritmo", "ciclo_de_cita", "momento", "tecnica", "externa"}
    assert set(datos["peso_familia"]) == familias
    assert set(datos["estados"]) == ESTADOS


def test_fachada_expone_el_mismo_catalogo_que_el_json():
    datos = _catalogo()
    assert agendamiento.CATALOGO == datos["patrones"]
    assert agendamiento.PESO_FAMILIA == datos["peso_familia"]
