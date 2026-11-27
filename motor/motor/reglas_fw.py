"""Reglas sobre el firewall. Se apoyan en puertos y acciones, no en el nombre de la aplicación: en los datos de
octubre la fuerza bruta por el puerto 23 viene etiquetada como "Sesion_Incompleta" y la ráfaga SSH como "No_Aplica"."""
from __future__ import annotations

import pandas as pd

from . import config
from .hallazgo import Hallazgo
from .ventanas import por_entidad

MAX_FILAS = 2000   # filas de evidencia que se guardan por hallazgo


def _base(ep: pd.DataFrame, regla: str) -> Hallazgo:
    usuarios = ep["u"].astype(str).value_counts()
    return Hallazgo(
        regla=regla, fuente="firewall", inicio=int(ep["s"].min()), fin=int(ep["s"].max()),
        iph=int(ep["iph"].iloc[0]), usuarios=list(usuarios.index[:3]), filas_fw=ep["fila"].head(MAX_FILAS).tolist(),
        eventos_fw=len(ep), segmento=bool(ep["seg"].any()),
        evidencia={"eventos": len(ep), "negados": int(ep["neg"].sum()), "permitidos": int((~ep["neg"]).sum()),
                   "puertos": sorted(int(p) for p in ep["p"].unique() if p >= 0),
                   "duracion_seg": int(ep["s"].max() - ep["s"].min())})


def rafagas_ip(fw: pd.DataFrame) -> list[Hallazgo]:
    """Ráfagas de intentos desde una IP hacia el servidor: escaneo, fuerza bruta o ráfaga SSH."""
    srv = fw[fw["srv"]]
    salida = []
    for ep in por_entidad(srv, "iph", config.RAFAGA_IP_SEG, config.RAFAGA_IP_MIN):
        puertos = ep.loc[ep["p"] >= 0, "p"].nunique()
        pct_neg = ep["neg"].mean()
        if (ep["ssh"] & ~ep["neg"]).mean() >= config.SSH_PCT_RAFAGA:
            h = _base(ep, "rafaga_ssh")
            h.tecnica("T1021.004", "T1048")
        elif puertos >= config.ESCANEO_PUERTOS_MIN:
            h = _base(ep, "escaneo")
            h.tecnica("T1046")
        elif pct_neg >= config.FUERZA_BRUTA_PCT_NEGADO:
            h = _base(ep, "fuerza_bruta")
            h.tecnica("T1110")
        else:
            h = _base(ep, "rafaga_conexiones")
        salida.append(h)
    return salida


def rafagas_ssh(fw: pd.DataFrame, ya: list[Hallazgo]) -> list[Hallazgo]:
    """Muchas sesiones SSH permitidas al servidor en pocos segundos desde una IP: posible extracción de datos."""
    ssh = fw[fw["srv"] & fw["ssh"] & ~fw["neg"]]
    salida = []
    for ep in por_entidad(ssh, "iph", config.RAFAGA_SSH_SEG, config.RAFAGA_SSH_MIN):
        h = _base(ep, "rafaga_ssh")
        if any(x.iph == h.iph and x.inicio <= h.fin and h.inicio <= x.fin for x in ya):
            continue
        h.tecnica("T1021.004", "T1048")
        salida.append(h)
    return salida


def servicios_inseguros(fw: pd.DataFrame) -> Hallazgo | None:
    """Conexiones permitidas por Telnet, SMBv1 y NetBIOS (hallazgo general del mes)."""
    ok = ~fw["neg"] & fw["p"].isin(list(config.PUERTOS_INSEGUROS))
    if not ok.any():
        return None
    x = fw.loc[ok, ["p", "srv"]]
    servicio = x["p"].map(config.PUERTOS_INSEGUROS)
    return Hallazgo(
        regla="servicios_inseguros", fuente="firewall", inicio=int(fw["s"].min()), fin=int(fw["s"].max()),
        general=True, eventos_fw=int(ok.sum()),
        evidencia={"permitidas_total": int(ok.sum()), "permitidas_al_servidor": int(x["srv"].sum()),
                   **{f"{k}": int(v) for k, v in servicio.value_counts().items()}})


def segmento_servidor(fw: pd.DataFrame) -> dict:
    """Contexto: cuántos eventos y usuarios salen del mismo segmento del servidor médico."""
    x = fw[fw["seg"]]
    return {"eventos": len(x), "ips_distintas": int(x["iph"].nunique()), "usuarios": int(x["u"].nunique())}


def detectar(fw: pd.DataFrame) -> tuple[list[Hallazgo], list[Hallazgo], dict]:
    ataques = rafagas_ip(fw)
    ataques += rafagas_ssh(fw, ataques)
    generales = [h for h in [servicios_inseguros(fw)] if h]
    return ataques, generales, segmento_servidor(fw)
