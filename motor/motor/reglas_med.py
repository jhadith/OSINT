"""Reglas sobre el sistema médico."""
from __future__ import annotations

import pandas as pd

from . import config
from .hallazgo import Hallazgo
from .ventanas import por_entidad

MAX_FILAS = 3000


def _acciones(med: pd.DataFrame, patron: str) -> pd.Series:
    cats = pd.Series(med["accion"].cat.categories)
    elegidas = set(cats[cats.str.contains(patron, case=False, regex=True)])
    return med["accion"].isin(elegidas)


def _base(ep: pd.DataFrame, regla: str) -> Hallazgo:
    personas = ep["persona"].astype(str).value_counts()
    acciones = ep["accion"].astype(str).value_counts()
    return Hallazgo(
        regla=regla, fuente="sistema_medico", inicio=int(ep["s"].min()), fin=int(ep["s"].max()),
        cuenta=str(ep["cuenta"].iloc[0]), personas=list(personas.index[:3]), idx_med=ep.index[:MAX_FILAS].tolist(),
        eventos_med=len(ep),
        evidencia={"eventos": len(ep), "acciones": {k: int(v) for k, v in acciones.items()},
                   "personas_distintas": int(len(personas)), "duracion_seg": int(ep["s"].max() - ep["s"].min())})


def fallidos_masivos(med: pd.DataFrame) -> list[Hallazgo]:
    x = med[_acciones(med, config.PATRON_FALLIDO)]
    salida = []
    for ep in por_entidad(x, "cuenta", config.FALLIDOS_SEG, config.FALLIDOS_MIN):
        h = _base(ep, "fallidos_masivos")
        h.tecnica("T1110")
        salida.append(h)
    return salida


def extraccion_masiva(med: pd.DataFrame) -> list[Hallazgo]:
    x = med[_acciones(med, config.PATRON_SENSIBLE)]
    salida = []
    for ep in por_entidad(x, "cuenta", config.MASIVO_SEG, config.MASIVO_MIN):
        h = _base(ep, "extraccion_masiva")
        h.tecnica("T1213", "T1048")
        salida.append(h)
    return salida


def cuentas_raras(med: pd.DataFrame, conteo: pd.Series) -> list[Hallazgo]:
    """Cuenta con muy pocos eventos en el mes y al menos uno que saca datos (cuenta fantasma)."""
    raras = conteo[(conteo > 0) & (conteo <= config.CUENTA_RARA_MAX)].index
    x = med[med["cuenta"].isin(raras)]
    sensibles = set(x.loc[_acciones(x, config.PATRON_SENSIBLE), "cuenta"].astype(str))
    salida = []
    for cuenta in sorted(sensibles):
        ep = x[x["cuenta"] == cuenta].sort_values("s")
        h = _base(ep, "cuenta_rara")
        h.evidencia["eventos_en_el_mes"] = int(conteo[cuenta])
        h.tecnica("T1078", "T1213")
        salida.append(h)
    return salida


def cuentas_compartidas(med: pd.DataFrame) -> Hallazgo | None:
    nombres = med.groupby("cuenta", observed=True)["persona"].nunique()
    malas = nombres[nombres >= config.NOMBRES_CUENTA_COMPARTIDA].sort_values(ascending=False)
    if malas.empty:
        return None
    return Hallazgo(
        regla="cuentas_compartidas", fuente="sistema_medico", inicio=int(med["s"].min()), fin=int(med["s"].max()),
        general=True, cuenta=", ".join(map(str, malas.index[:5])), tecnicas=["T1078"],
        evidencia={"cuentas": len(malas), "max_nombres": int(malas.iloc[0]),
                   "detalle": {str(k): int(v) for k, v in malas.head(10).items()},
                   "mediana_nombres_por_cuenta": float(nombres.median())})


def administracion_concentrada(med: pd.DataFrame) -> Hallazgo | None:
    """Cuentas que hacen una acción administrativa muchas más veces que la cuenta típica."""
    x = med[_acciones(med, config.PATRON_ADMIN)]
    if x.empty:
        return None
    t = x.groupby(["cuenta", "accion"], observed=True).size()
    mediana = t.groupby(level="accion", observed=True).transform("median")
    altas = t[t >= config.ADMIN_VECES_MEDIANA * mediana].sort_values(ascending=False)
    if altas.empty:
        return None
    cuentas = list(dict.fromkeys(str(c) for c, _ in altas.index))
    return Hallazgo(
        regla="administracion_concentrada", fuente="sistema_medico", inicio=int(med["s"].min()),
        fin=int(med["s"].max()), general=True, cuenta=", ".join(cuentas[:5]), tecnicas=["T1098"],
        eventos_med=int(altas.sum()),
        evidencia={"cuentas": len(cuentas),
                   "detalle": {f"{c} · {a}": int(v) for (c, a), v in altas.head(10).items()},
                   "mediana_por_cuenta": float(mediana.median())})


def detectar(med: pd.DataFrame) -> tuple[list[Hallazgo], list[Hallazgo], pd.Series]:
    conteo = med.groupby("cuenta", observed=True).size()
    ataques = fallidos_masivos(med) + extraccion_masiva(med) + cuentas_raras(med, conteo)
    generales = [h for h in [cuentas_compartidas(med), administracion_concentrada(med)] if h]
    return ataques, generales, conteo
