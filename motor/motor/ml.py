"""Isolation Forest por ventanas de tiempo: usuario por hora en el firewall y cuenta por día en el sistema médico.
No supervisado: no conoce los ataques. Da un puntaje 0-100 a cada ventana y explica las 3 variables más raras."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from . import config

TEXTO = {
    "eventos": "eventos en la ventana", "pct_negado": "% negado", "pct_servidor": "% hacia el servidor médico",
    "servicios_distintos": "servicios distintos", "max_por_minuto": "máximo de eventos en un minuto",
    "ssh_permitido": "SSH permitidos al servidor", "desde_segmento_servidor": "eventos desde el segmento del servidor",
    "veces_su_hora_tipica": "veces su hora típica", "nombres_distintos": "nombres distintos",
    "pct_ip_mal_formada": "% IP mal escrita", "dias_activos_cuenta": "días activos de la cuenta en el mes",
    "veces_su_dia_tipico": "veces su día típico",
}


@dataclass
class Ranking:
    tabla: pd.DataFrame          # entidad, ventana (segundos de inicio), puntaje, puesto, por_que (solo top)
    total: int
    entidades: int


def _puntuar(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = f.to_numpy(dtype="float64")
    for j, c in enumerate(f.columns):
        if not c.startswith("pct_"):
            X[:, j] = np.log1p(np.clip(X[:, j], 0, None))
    desv = X.std(axis=0)
    desv[desv == 0] = 1
    Z = (X - X.mean(axis=0)) / desv
    modelo = IsolationForest(n_estimators=200, max_samples=min(4096, len(Z)), random_state=config.SEMILLA,
                             n_jobs=-1).fit(Z)
    bruto = -modelo.score_samples(Z)
    rango = bruto.max() - bruto.min() or 1
    return 100 * (bruto - bruto.min()) / rango, Z


def _num(v: float) -> str:
    """Formato local: 2.000 y 1,5."""
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}".replace(",", ".")
    return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _explicar(f: pd.DataFrame, Z: np.ndarray, filas) -> list[str]:
    med = f.median()
    salida = []
    for i in filas:
        partes = []
        for j in np.argsort(-np.abs(Z[i]))[:3]:
            c, v, n = f.columns[j], f.iat[i, j], med.iloc[j]
            nombre = TEXTO.get(c, c.replace("pct_", "% ").replace("_", " "))
            if c.startswith("pct_"):
                partes.append(f"{nombre}: {100 * v:.0f}% (normal {100 * n:.0f}%)")
            else:
                partes.append(f"{nombre}: {_num(v)} (normal {_num(n)})")
        salida.append(" | ".join(partes))
    return salida


def _ranking(f: pd.DataFrame, entidad: str, paso: int, top: int) -> Ranking:
    puntaje, Z = _puntuar(f)
    r = f.reset_index()[[entidad, "v"]].copy()
    r["ventana"] = r["v"] * paso
    r["puntaje"] = puntaje.round(1)
    orden = np.argsort(-puntaje, kind="stable")
    r["puesto"] = 0
    r.loc[r.index[orden], "puesto"] = np.arange(1, len(r) + 1)
    r["por_que"] = ""
    r.loc[r.index[orden[:top]], "por_que"] = _explicar(f, Z, orden[:top])
    return Ranking(r.drop(columns="v"), len(r), int(r[entidad].nunique()))


def firewall(fw: pd.DataFrame, top: int = 200) -> Ranking:
    d = fw[["u", "s", "p", "neg", "srv", "ssh", "seg"]].copy()
    d["v"] = d["s"] // 3600
    d["m"] = d["s"] // 60
    d["ssh_ok"] = d["ssh"] & ~d["neg"] & d["srv"]
    g = d.groupby(["u", "v"], observed=True)
    f = pd.DataFrame({"eventos": g.size()})
    f["pct_negado"] = g["neg"].mean()
    f["pct_servidor"] = g["srv"].mean()
    f["servicios_distintos"] = g["p"].nunique()
    f["max_por_minuto"] = d.groupby(["u", "v", "m"], observed=True).size().groupby(level=[0, 1], observed=True).max()
    f["ssh_permitido"] = g["ssh_ok"].sum()
    f["desde_segmento_servidor"] = g["seg"].sum()
    f["veces_su_hora_tipica"] = f["eventos"] / f["eventos"].groupby(level=0, observed=True).transform("median")
    return _ranking(f.fillna(0), "u", 3600, top)


def sistema_medico(med: pd.DataFrame, top: int = 200) -> Ranking:
    d = med[["cuenta", "persona", "accion", "s", "ipmal"]].copy()
    d["v"] = d["s"] // 86400
    d["m"] = d["s"] // 60
    g = d.groupby(["cuenta", "v"], observed=True)
    f = pd.DataFrame({"eventos": g.size()})
    acc = pd.crosstab([d["cuenta"], d["v"]], d["accion"], normalize="index")
    acc.columns = ["pct_" + str(c).lower().replace("usuarios - ", "").replace(" ", "_") for c in acc.columns]
    f = f.join(acc)
    f["nombres_distintos"] = g["persona"].nunique()
    f["max_por_minuto"] = d.groupby(["cuenta", "v", "m"], observed=True).size().groupby(level=[0, 1],
                                                                                         observed=True).max()
    f["pct_ip_mal_formada"] = g["ipmal"].mean()
    f["dias_activos_cuenta"] = f.groupby(level=0, observed=True)["eventos"].transform("size")
    f["veces_su_dia_tipico"] = f["eventos"] / f["eventos"].groupby(level=0, observed=True).transform("median")
    return _ranking(f.fillna(0), "cuenta", 86400, top)


def puesto(r: Ranking | None, entidad_col: str, entidad: str, segundo: int, paso: int) -> dict:
    if r is None:
        return {}
    x = r.tabla[(r.tabla[entidad_col].astype(str) == str(entidad)) & (r.tabla["ventana"] == (segundo // paso) * paso)]
    if x.empty:
        return {}
    return {"puesto": int(x["puesto"].iloc[0]), "de": r.total, "puntaje": float(x["puntaje"].iloc[0]),
            "por_que": str(x["por_que"].iloc[0])}
