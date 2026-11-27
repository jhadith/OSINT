"""Detección de ráfagas: tramos de eventos de una misma entidad donde hay al menos `minimo` eventos dentro de
`ventana` segundos. Devuelve un episodio por tramo continuo (no una alerta por cada segundo)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def episodios(t: np.ndarray, ventana: int, minimo: int) -> list[tuple[int, int]]:
    """t: segundos ordenados. Devuelve [(i_inicio, i_fin)] inclusivos sobre t."""
    n = len(t)
    if n < minimo:
        return []
    fin = np.searchsorted(t, t + ventana, side="right")   # primer índice fuera de la ventana [t_i, t_i+ventana]
    cuenta = fin - np.arange(n)
    marcados = np.zeros(n + 1, dtype="int32")
    cumplen = np.flatnonzero(cuenta >= minimo)            # cada ventana que cumple marca sus filas
    np.add.at(marcados, cumplen, 1)
    np.add.at(marcados, fin[cumplen], -1)
    dentro = np.cumsum(marcados[:n]) > 0
    if not dentro.any():
        return []
    # un episodio nuevo empieza donde se entra en zona marcada o donde hay un hueco mayor que la ventana
    hueco = np.concatenate(([True], np.diff(t) > ventana))
    previo = np.concatenate(([False], dentro[:-1]))
    empieza = dentro & (~previo | hueco)
    siguiente_empieza = np.concatenate((empieza[1:], [True]))
    siguiente_dentro = np.concatenate((dentro[1:], [False]))
    termina = dentro & (~siguiente_dentro | siguiente_empieza)
    return [(int(a), int(b)) for a, b in zip(np.flatnonzero(empieza), np.flatnonzero(termina), strict=False)]


def por_entidad(df: pd.DataFrame, clave: str, ventana: int, minimo: int) -> list[pd.DataFrame]:
    """Aplica `episodios` a cada valor de `clave` con al menos `minimo` eventos. Devuelve un DataFrame por episodio."""
    conteo = df[clave].value_counts()
    candidatas = conteo[conteo >= minimo].index
    if len(candidatas) == 0:
        return []
    sub = df[df[clave].isin(candidatas)].sort_values([clave, "s"], kind="stable")
    salida = []
    for _, g in sub.groupby(clave, observed=True, sort=False):
        t = g["s"].to_numpy()
        for i0, i1 in episodios(t, ventana, minimo):
            salida.append(g.iloc[i0:i1 + 1])
    return salida
