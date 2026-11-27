"""Métricas de evaluación de HBVF (informe 14.6): precision, sensibilidad (recall) y F1.

Fórmulas del informe: precision = VP/(VP+FP), recall = VP/(VP+FN),
tasa de falsos positivos = FP/(FP+VN) y F1 = 2*precision*recall/(precision+recall).
Un denominador en cero produce 0.0 (nunca una excepción ni un valor inventado).
"""
from __future__ import annotations

import pandas as pd


def metricas(vp: int, fp: int, fn: int, vn: int) -> dict:
    """Matriz de confusión y métricas del informe 14.6.

    Sin ejemplos para evaluar en una dirección el resultado es 0.0: no hay métrica,
    y el cero explícito documenta la ausencia de evidencia en lugar de fingirla.
    """
    precision = vp / (vp + fp) if vp + fp else 0.0
    recall = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"vp": vp, "fp": fp, "fn": fn, "vn": vn, "precision": precision, "recall": recall,
            "tasa_falsos_positivos": fp / (fp + vn) if fp + vn else 0.0, "f1": f1}


def evaluar(df: pd.DataFrame, m: pd.DataFrame, resultados: dict) -> dict | None:
    """Solo si el dataset trae la columna `escenario` (datos sintéticos con escenarios conocidos). El detector no la usa."""
    if "escenario" not in df.columns or not (df["escenario"] != "").any():
        return None
    real = df.groupby("punto")["escenario"].agg(lambda s: s.value_counts().index[0])
    positivo = real.str.startswith("tramitador")
    pred = pd.Series({p: resultados[p]["revision_requerida"] and not resultados[p]["estado"].startswith("Indeterminado")
                      for p in m.index})
    vp = int((positivo & pred).sum())
    fp = int((~positivo & pred).sum())
    fn = int((positivo & ~pred).sum())
    vn = int((~positivo & ~pred).sum())
    met = metricas(vp, fp, fn, vn)
    por_escenario = {}
    for esc, grupo in real.groupby(real):
        por_escenario[esc] = {"puntos": int(len(grupo)),
                              "marcados_para_revision": int(pred.reindex(grupo.index).sum()),
                              "estados": pd.Series([resultados[p]["estado"] for p in grupo.index]).value_counts()
                              .to_dict()}
    return {"nota": "Prueba preliminar con datos sintéticos y escenarios conocidos; no demuestra eficacia real.",
            "matriz": {"vp": vp, "fp": fp, "fn": fn, "vn": vn}, "precision": round(met["precision"], 3),
            "sensibilidad": round(met["recall"], 3),
            "tasa_falsos_positivos": round(met["tasa_falsos_positivos"], 4),
            "f1": round(met["f1"], 3), "por_escenario": por_escenario}
