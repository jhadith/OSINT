"""Pruebas del módulo de agendamiento (HBVF) con el dataset sintético complementario."""
import pytest

from motor import agendamiento, config
from tests import generador_citas as gc


@pytest.fixture(scope="module")
def salida(tmp_path_factory):
    ruta = gc.generar(tmp_path_factory.mktemp("citas") / "citas.csv")
    return agendamiento.analizar(ruta, config.REDES, {agendamiento.referencia_contacto("SIM-TRAMITE-02")})


def test_contrato_del_informe(salida):
    campos = {"case_id", "pattern_ids", "anomaly_score", "confidence", "risk_score", "status", "evidence_refs",
              "legitimate_explanations", "recommendations", "review_required", "dataset_origin"}
    assert salida["casos"] and all(campos <= set(c) for c in salida["casos"])
    assert [p["id"] for p in salida["catalogo"]] == [f"HG-0{i}" for i in range(1, 8)]


def test_encuentra_los_cuatro_tramitadores_sin_marcar_legitimos(salida):
    e = salida["evaluacion"]
    assert e["matriz"]["vp"] == 4 and e["matriz"]["fp"] == 0
    for legitimo in ("cuidador_autorizado", "operador_autorizado", "red_compartida", "normal"):
        assert e["por_escenario"][legitimo]["marcados_para_revision"] == 0


def test_operadores_autorizados_quedan_explicados(salida):
    assert salida["evaluacion"]["por_escenario"]["operador_autorizado"]["estados"] == {
        "Explicado por contexto legítimo": 3}


def test_canal_sin_datos_tecnicos_marca_desconocido(salida):
    wsp = [c for c in salida["casos"] if "whatsapp" in c["resumen"]["canales"] and c["review_required"]]
    assert wsp and wsp[0]["patrones"]["HG-06"] == "desconocido" and "HG-07" in wsp[0]["pattern_ids"]


def test_nada_automatico_y_sin_contactos_en_claro(salida):
    texto = str(salida)
    assert "SIM-TRAMITE" not in texto and "SIM-AF" not in texto
    for c in salida["casos"]:
        assert all("bloque" not in r["texto"].lower() or "no" in r["texto"].lower() for r in c["recommendations"])
