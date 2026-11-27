"""Métricas de evaluación precision/recall/F1 (T4/S5, informe 14.6)."""
import pytest

from motor.hbvf import model_evaluation as me


def test_precision_recall_f1_y_tasa_de_falsos_positivos():
    m = me.metricas(vp=4, fp=0, fn=1, vn=5)
    assert m["vp"] == 4 and m["fp"] == 0 and m["fn"] == 1 and m["vn"] == 5
    assert m["precision"] == 1.0
    assert m["recall"] == 0.8
    assert m["f1"] == pytest.approx(2 * 1.0 * 0.8 / (1.0 + 0.8))
    assert m["tasa_falsos_positivos"] == 0.0


def test_denominador_cero_devuelve_cero_no_excepcion():
    m = me.metricas(vp=0, fp=0, fn=0, vn=0)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0
    assert m["tasa_falsos_positivos"] == 0.0
