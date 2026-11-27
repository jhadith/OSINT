"""Isolation Forest por ventanas de tiempo: usuario por hora en el firewall y cuenta por día en el sistema médico.
No supervisado: no conoce los ataques. Da un puntaje 0-100 a cada ventana y explica las 3 variables más raras.

Además (S9/T18) acumula las ventanas de cada corrida en un histórico CSV (acumular) y puede
reentrenar con TODO ese histórico (reentrenar/puntuar_modelo), siempre con la semilla de rules/ml.yml
para que el resultado sea reproducible. El reentrenamiento nunca corre solo: lo invoca quien
recalibra (backend/app/realimentacion.py) o una prueba.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

HISTORICO_DEFECTO = {"firewall": "historico_firewall.csv", "sistema_medico": "historico_sistema_medico.csv"}


@dataclass
class Ranking:
    tabla: pd.DataFrame          # entidad, ventana (segundos de inicio), puntaje, puesto, por_que (solo top)
    total: int
    entidades: int


@dataclass
class Modelo:
    """Isolation Forest reentrenado con el histórico acumulado de ventanas."""
    fuente: str
    bosque: IsolationForest
    media: np.ndarray            # ajuste del histórico con el que se puntúan las ventanas nuevas
    desv: np.ndarray
    columnas: list[str]
    ventanas: int
    semilla: int


def _transformar(f: pd.DataFrame) -> np.ndarray:
    """Variables → escala de aprendizaje: log1p en todo salvo los porcentajes (ya están en 0-1)."""
    X = f.to_numpy(dtype="float64")
    for j, c in enumerate(f.columns):
        if not c.startswith("pct_"):
            X[:, j] = np.log1p(np.clip(X[:, j], 0, None))
    return X


def _puntuar(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = _transformar(f)
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


def ventanas_firewall(fw: pd.DataFrame) -> pd.DataFrame:
    """Variables por ventana (usuario × hora): lo que puntúa el modelo y lo que se acumula en el histórico."""
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
    return f.fillna(0)


def firewall(fw: pd.DataFrame, top: int = 200) -> Ranking:
    return _ranking(ventanas_firewall(fw), "u", 3600, top)


def ventanas_sistema_medico(med: pd.DataFrame) -> pd.DataFrame:
    """Variables por ventana (cuenta × día): lo que puntúa el modelo y lo que se acumula en el histórico."""
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
    return f.fillna(0)


def sistema_medico(med: pd.DataFrame, top: int = 200) -> Ranking:
    return _ranking(ventanas_sistema_medico(med), "cuenta", 86400, top)


def ruta_historico(fuente: str, ruta: Path | str | None = None) -> Path:
    """CSV acumulativo de la fuente: por defecto en datos/ del motor (carpeta ignorada por git)."""
    if fuente not in HISTORICO_DEFECTO:
        raise ValueError(f"fuente desconocida: {fuente} (usa {', '.join(HISTORICO_DEFECTO)})")
    return Path(ruta) if ruta else config.DATOS / HISTORICO_DEFECTO[fuente]


def acumular(f: pd.DataFrame, fuente: str, ruta: Path | str | None = None) -> Path:
    """Agrega las ventanas de una corrida al histórico acumulativo (CSV, solo-agregar).

    Idempotente: una ventana (entidad, ventana) ya escrita no se vuelve a agregar, así que repetir
    el mismo análisis no duplica el histórico. Columnas: entidad, ventana y las variables de la
    ventana; un archivo por fuente porque sus variables no son las mismas.
    """
    destino = ruta_historico(fuente, ruta)
    x = f.reset_index()
    x.columns = ["entidad", "ventana", *x.columns[2:]]
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        previo = pd.read_csv(destino, float_precision="round_trip")
        vistas = set(zip(previo["entidad"].astype(str), previo["ventana"], strict=False))
        x = x[[k not in vistas for k in zip(x["entidad"].astype(str), x["ventana"], strict=False)]]
        if x.empty:
            return destino
    x.to_csv(destino, mode="a", header=not destino.exists(), index=False)
    return destino


def leer_historico(fuente: str, ruta: Path | str | None = None) -> pd.DataFrame:
    """Histórico acumulado; falla con un mensaje claro si aún no hay nada que reentrenar."""
    destino = ruta_historico(fuente, ruta)
    if not destino.exists():
        raise ValueError(f"No hay histórico acumulado de {fuente}: {destino}. Acumula ventanas primero.")
    df = pd.read_csv(destino, float_precision="round_trip")
    if df.empty:
        raise ValueError(f"El histórico de {fuente} está vacío: {destino}.")
    return df


def reentrenar(fuente: str, ruta: Path | str | None = None) -> Modelo:
    """Reentrena el Isolation Forest con TODO el histórico acumulado de ventanas.

    Determinista: misma semilla (rules/ml.yml) + mismos datos → mismo modelo. Estandariza con la
    media y la desviación del histórico, y puntuar_modelo usa ese mismo ajuste, para que las
    ventanas nuevas se midan contra la normalidad acumulada y no contra sí mismas.
    """
    df = leer_historico(fuente, ruta)
    columnas = [c for c in df.columns if c not in ("entidad", "ventana")]
    if not columnas:
        raise ValueError(f"El histórico de {fuente} no tiene variables de ventana.")
    X = _transformar(df[columnas])
    media = X.mean(axis=0)
    desv = X.std(axis=0)
    desv[desv == 0] = 1
    Z = (X - media) / desv
    bosque = IsolationForest(n_estimators=200, max_samples=min(4096, len(Z)), random_state=config.SEMILLA,
                             n_jobs=-1).fit(Z)
    return Modelo(fuente=fuente, bosque=bosque, media=media, desv=desv, columnas=columnas,
                  ventanas=int(len(df)), semilla=int(config.SEMILLA))


def puntuar_modelo(m: Modelo, f: pd.DataFrame) -> np.ndarray:
    """Puntaje 0-100 de las ventanas `f` con el modelo reentrenado (misma escala que _puntuar)."""
    faltan = [c for c in m.columnas if c not in f.columns]
    if faltan:
        raise ValueError(f"Variables que el modelo no conoce: {', '.join(faltan)}.")
    X = _transformar(f[m.columnas])
    Z = (X - m.media) / m.desv
    bruto = -m.bosque.score_samples(Z)
    rango = bruto.max() - bruto.min() or 1
    return 100 * (bruto - bruto.min()) / rango


def puesto(r: Ranking | None, entidad_col: str, entidad: str, segundo: int, paso: int) -> dict:
    if r is None:
        return {}
    x = r.tabla[(r.tabla[entidad_col].astype(str) == str(entidad)) & (r.tabla["ventana"] == (segundo // paso) * paso)]
    if x.empty:
        return {}
    return {"puesto": int(x["puesto"].iloc[0]), "de": r.total, "puntaje": float(x["puntaje"].iloc[0]),
            "por_que": str(x["por_que"].iloc[0])}
