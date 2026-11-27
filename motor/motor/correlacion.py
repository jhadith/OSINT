"""Cruce firewall + sistema médico.

En el sistema médico la IP registrada es la del servidor, no la del atacante, así que el cruce se hace por persona y
por hora: el usuario del firewall ("ivan.prieto") se compara con el nombre del sistema médico
("PRIETO ESTEVEZ IVAN ARTURO") y los eventos tienen que caer en la misma ventana, probando desfases de reloj.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

import numpy as np
import pandas as pd

from . import config
from .hallazgo import Hallazgo


def fichas(texto: str) -> set[str]:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper()
    return {p for p in re.split(r"[^A-Z]+", t) if len(p) >= 3}


def misma_persona(usuario: str, persona: str) -> bool:
    u = fichas(usuario)
    return len(u) >= 2 and u <= fichas(persona)


def _solapan(a0, a1, b0, b1, tol) -> bool:
    return a0 <= b1 + tol and b0 - tol <= a1


def _unir(f: Hallazgo, m: Hallazgo, desfase_h: int) -> Hallazgo:
    corrido = desfase_h * 3600
    if m.fin - m.inicio > 2 * 3600:      # el sistema médico se extiende el día entero: manda la hora del firewall
        inicio, fin = f.inicio + corrido, f.fin + corrido
    else:
        inicio, fin = min(m.inicio, f.inicio + corrido), max(m.fin, f.fin + corrido)
    h = replace(m, regla=f"{f.regla}+{m.regla}", fuente="correlacion", inicio=inicio, fin=fin,
                iph=f.iph, ip=f.ip, usuarios=f.usuarios, filas_fw=f.filas_fw, eventos_fw=f.eventos_fw,
                segmento=f.segmento, desfase_h=desfase_h, tecnicas=list(f.tecnicas),
                evidencia={"firewall": f.evidencia, "sistema_medico": m.evidencia})
    h.tecnica(*m.tecnicas)
    return h


def cruzar(fw: list[Hallazgo], med: list[Hallazgo]) -> tuple[list[Hallazgo], list[Hallazgo], list[Hallazgo]]:
    """Empareja hallazgos de ambas fuentes. Devuelve (correlacionados, solo_firewall, solo_medico)."""
    tol = config.CORRELACION_TOLERANCIA_SEG
    usados_f, usados_m, juntos = set(), set(), []
    for d in config.DESFASES_HORAS:          # primero sin desfase
        for i, f in enumerate(fw):
            if i in usados_f:
                continue
            for j, m in enumerate(med):
                if j in usados_m:
                    continue
                if not any(misma_persona(u, p) for u in f.usuarios for p in m.personas):
                    continue
                if _solapan(f.inicio + d * 3600, f.fin + d * 3600, m.inicio, m.fin, tol):
                    juntos.append(_unir(f, m, d))
                    usados_f.add(i)
                    usados_m.add(j)
                    break
    return (juntos, [f for i, f in enumerate(fw) if i not in usados_f],
            [m for j, m in enumerate(med) if j not in usados_m])


def buscar_en_firewall(m: Hallazgo, fw: pd.DataFrame, usuarios_fw: list[str]) -> Hallazgo | None:
    """Para un hallazgo del sistema médico sin pareja: busca en el firewall eventos hacia el servidor de la misma
    persona en esa ventana (con cada desfase) y se queda con el más cercano, prefiriendo SSH.
    Solo para hallazgos cortos (cuenta rara, extracción): en un día completo siempre habría algún evento del usuario."""
    if m.fin - m.inicio > config.CORRELACION_TOLERANCIA_SEG:
        return None
    candidatos = [u for u in usuarios_fw if any(misma_persona(u, p) for p in m.personas)]
    if not candidatos:
        return None
    x = fw[fw["srv"] & fw["u"].isin(candidatos)]
    tol, mejor = config.CORRELACION_TOLERANCIA_SEG, None
    for d in config.DESFASES_HORAS:
        t = x["s"].to_numpy() + d * 3600
        cerca = (t >= m.inicio - tol) & (t <= m.fin + tol)
        if not cerca.any():
            continue
        y = x[cerca]
        dist = np.minimum(np.abs(t[cerca] - m.inicio), np.abs(t[cerca] - m.fin))
        orden = np.lexsort((dist, ~y["ssh"].to_numpy()))      # SSH primero, luego el más cercano
        k = orden[0]
        es_ssh = bool(y["ssh"].iloc[k])
        if not es_ssh and dist[k] > 5:     # un evento cualquiera del usuario no basta: SSH o casi simultáneo
            continue
        nota = (not es_ssh, int(dist[k]), abs(d))
        if mejor is None or nota < mejor[0]:
            mejor = (nota, d, y.iloc[[k]])
    if mejor is None:
        return None
    _, d, fila = mejor
    f = Hallazgo(regla="conexion_asociada", fuente="firewall", inicio=int(fila["s"].iloc[0]),
                 fin=int(fila["s"].iloc[0]), iph=int(fila["iph"].iloc[0]), usuarios=[str(fila["u"].iloc[0])],
                 filas_fw=fila["fila"].tolist(), eventos_fw=1, segmento=bool(fila["seg"].iloc[0]),
                 evidencia={"eventos": 1, "puertos": [int(fila["p"].iloc[0])],
                            "accion": "negado" if bool(fila["neg"].iloc[0]) else "permitido"})
    if bool(fila["ssh"].iloc[0]):
        f.tecnica("T1021.004")
    h = _unir(f, m, d)
    h.regla = m.regla + "+firewall"
    return h
