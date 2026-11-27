"""Lectura por partes de los dos CSV a tablas compactas en memoria.

Firewall (una fila por evento):  s (segundos desde EPOCA), iph (hash de la IP de origen), u (usuario, categoría),
  p (puerto), neg (negado), srv (hacia el servidor médico), seg (IP del segmento del servidor), fila (n.º de fila).
  La IP en texto no se guarda para los 5 millones de filas: se recupera después solo para las filas de las alertas.
Sistema médico:  s, cuenta, persona, accion, ip (categorías), ipmal (IP mal escrita).
Las filas con fecha inválida se descartan y se cuentan; no detienen el análisis.
Los CSVs REALES del IESS (contrato v2: BOM UTF-8, ~5M de filas) se leen con `leer_fw_real`/`leer_med_real`,
camino paralelo con la misma salida que `leer_fw`/`leer_med` (ver tests/test_ingesta_reales.py).
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

from . import config

COL_FW = ["Fecha_Generacion", "IP_Origen", "IP_Destino", "Usuario_Origen", "Usuario_Destino", "Aplicacion",
          "Puerto_Destino", "Protocolo", "Accion"]
COL_MED = ["USUARIO_EJECUTA_EVENTO", "NOMBRE_USUARIO_EJECUTA_EVENTO", "FECHA_EJECUTA_EVENTO", "HORA_EJECUTA_EVENTO",
           "DESCRIPCION_ACCION", "IP_CONEXION"]
EPOCA = pd.Timestamp(config.EPOCA)
IP_VALIDA = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
ENCODING_REAL = "utf-8-sig"      # los CSVs reales del IESS llevan BOM UTF-8 (contrato v2)


@dataclass
class Lectura:
    datos: pd.DataFrame
    filas: int = 0
    invalidas: int = 0
    faltantes: list = field(default_factory=list)


def codificacion(ruta: Path) -> str:
    with open(ruta, "rb") as f:
        trozo = f.read(4_000_000)
    try:
        codecs.getincrementaldecoder("utf-8")().decode(trozo, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def partes(ruta: Path, tam: int = config.TAM_PARTE, encoding: str | None = None):
    # encoding=None -> auto-detección (utf-8/cp1252) como siempre; los lectores reales fuerzan utf-8-sig.
    yield from pd.read_csv(ruta, dtype=str, chunksize=tam, encoding=encoding or codificacion(ruta),
                           encoding_errors="replace", keep_default_na=False, on_bad_lines="skip")


def _completar(df: pd.DataFrame, columnas: list[str]) -> list[str]:
    faltan = [c for c in columnas if c not in df.columns]
    for c in faltan:
        df[c] = ""
    for c in columnas:
        df[c] = df[c].astype(str).str.strip()
    return faltan


def segundos(ts: pd.Series) -> pd.Series:
    return ((ts - EPOCA) // pd.Timedelta(seconds=1)).astype("int64")


def hash_ip(s: pd.Series) -> np.ndarray:
    return pd.util.hash_pandas_object(s.astype(str), index=False).to_numpy(dtype="uint64")


def _unir(trozos: list[pd.DataFrame], categoricas: list[str]) -> pd.DataFrame:
    if not trozos:
        return pd.DataFrame()
    unidos = {c: union_categoricals([t[c] for t in trozos], ignore_order=True) for c in categoricas}
    resto = pd.concat([t.drop(columns=categoricas) for t in trozos], ignore_index=True)
    for c in categoricas:
        resto[c] = unidos[c]
    return resto


def leer_fw(ruta: Path, tam: int = config.TAM_PARTE, avance=print) -> Lectura:
    return _leer_fw(ruta, tam, avance)


def leer_fw_real(ruta: Path, tam: int = config.TAM_PARTE, avance=print) -> Lectura:
    """Camino paralelo para el CSV real del IESS (contrato v2, docs/data-contracts.md).

    BOM UTF-8 (utf-8-sig), deriva de protocolo con la prioridad del contrato
    (Aplicacion contiene SSH > Protocolo SSH > puerto conocido) y descarte de las
    filas con IP de formato inválido; el resto es idéntico a leer_fw.
    """
    return _leer_fw(ruta, tam, avance, encoding=ENCODING_REAL, real=True)


def _leer_fw(ruta: Path, tam: int, avance, *, encoding: str | None = None, real: bool = False) -> Lectura:
    trozos, filas, invalidas, faltantes, base = [], 0, 0, [], 0
    for i, df in enumerate(partes(ruta, tam, encoding)):
        faltan = _completar(df, COL_FW)
        faltantes = faltan or faltantes
        n = len(df)
        ts = pd.to_datetime(df["Fecha_Generacion"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        ok = ts.notna().to_numpy()
        if real:
            # contrato v2: IP_Origen/IP_Destino inválida -> ip_invalida (se descarta y se cuenta)
            ip_ok = pd.Series(True, index=df.index)
            for c in ("IP_Origen", "IP_Destino"):
                if c not in faltan:
                    ip_ok &= df[c].str.match(IP_VALIDA)
            ok &= ip_ok.to_numpy()
        puerto = pd.to_numeric(df["Puerto_Destino"], errors="coerce").fillna(-1).astype("int32")
        apps = df["Aplicacion"].str.upper()
        # deriva de protocolo (contrato v2): en los reales Aplicacion puede contener "SSH"
        # (p. ej. Tunneling_SSH) además de ser "SSH" a secas.
        es_ssh = apps.str.contains("SSH", regex=False) if real else apps.eq("SSH")
        ssh = (puerto.isin(config.PUERTOS_SSH) | es_ssh | df["Protocolo"].str.upper().eq("SSH")).to_numpy()
        t = pd.DataFrame({
            "fila": np.arange(base, base + n, dtype="int64"),
            "s": segundos(ts.fillna(EPOCA)),
            "iph": hash_ip(df["IP_Origen"]),
            "u": df["Usuario_Origen"].astype("category"),
            "p": puerto.to_numpy(),
            "neg": df["Accion"].str.lower().eq("negado").to_numpy(),
            "srv": df["IP_Destino"].eq(config.SERVIDOR).to_numpy(),
            "seg": (df["IP_Origen"].str.startswith(config.SEGMENTO_SERVIDOR)
                    & df["IP_Origen"].ne(config.SERVIDOR)).to_numpy(),
            "ssh": ssh,
        })[ok]
        trozos.append(t)
        filas, invalidas, base = filas + n, invalidas + int((~ok).sum()), base + n
        avance(f"  firewall: parte {i + 1} ({filas:,} filas)")
    d = _unir(trozos, ["u"])
    return Lectura(d.astype({"s": "int64"}) if len(d) else d, filas, invalidas, faltantes)


def leer_med(ruta: Path, tam: int = config.TAM_PARTE, avance=print) -> Lectura:
    return _leer_med(ruta, tam, avance)


def leer_med_real(ruta: Path, tam: int = config.TAM_PARTE, avance=print) -> Lectura:
    """Camino paralelo para el CSV real del IESS (contrato v2): BOM UTF-8 (utf-8-sig).

    Las 9 acciones de DESCRIPCION_ACCION se conservan tal cual (incluida la errata
    TRANFERENCIA) porque las reglas y el ML las emparejan por texto; las IP de
    formato raro (p. ej. sin puntos) se conservan marcadas en ipmal, como en leer_med.
    """
    return _leer_med(ruta, tam, avance, encoding=ENCODING_REAL)


def _leer_med(ruta: Path, tam: int, avance, *, encoding: str | None = None) -> Lectura:
    trozos, filas, invalidas, faltantes = [], 0, 0, []
    for i, df in enumerate(partes(ruta, tam, encoding)):
        faltantes = _completar(df, COL_MED) or faltantes
        n = len(df)
        ts = pd.to_datetime(df["FECHA_EJECUTA_EVENTO"] + " " + df["HORA_EJECUTA_EVENTO"], format="%Y%m%d %H:%M:%S",
                            errors="coerce")
        ok = ts.notna().to_numpy()
        t = pd.DataFrame({
            "s": segundos(ts.fillna(EPOCA)),
            "cuenta": df["USUARIO_EJECUTA_EVENTO"].astype("category"),
            "persona": df["NOMBRE_USUARIO_EJECUTA_EVENTO"].astype("category"),
            "accion": df["DESCRIPCION_ACCION"].astype("category"),
            "ip": df["IP_CONEXION"].astype("category"),
            "ipmal": (~df["IP_CONEXION"].str.match(IP_VALIDA)).to_numpy(),
        })[ok]
        trozos.append(t)
        filas, invalidas = filas + n, invalidas + int((~ok).sum())
        avance(f"  sistema médico: parte {i + 1} ({filas:,} filas)")
    d = _unir(trozos, ["cuenta", "persona", "accion", "ip"])
    return Lectura(d, filas, invalidas, faltantes)


def filas_fw(ruta: Path, indices: set[int], tam: int = config.TAM_PARTE) -> pd.DataFrame:
    """Segunda pasada: trae completas solo las filas pedidas (las de las alertas)."""
    if not indices:
        return pd.DataFrame(columns=COL_FW + ["fila"])
    buscados = np.array(sorted(indices), dtype="int64")
    trozos, base = [], 0
    for df in partes(ruta, tam):
        n = len(df)
        locales = buscados[(buscados >= base) & (buscados < base + n)] - base
        if len(locales):
            x = df.iloc[locales].copy()
            _completar(x, COL_FW)
            x["fila"] = locales + base
            trozos.append(x)
        base += n
    return pd.concat(trozos, ignore_index=True) if trozos else pd.DataFrame(columns=COL_FW + ["fila"])


def fecha(s: int | float) -> pd.Timestamp:
    return EPOCA + pd.Timedelta(seconds=int(s))
