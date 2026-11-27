"""Módulo de inteligencia de agendamiento médico con el marco HBVF (Healthcare Behavior Validation Framework).

Sigue el apartado 14 del informe:
  1. Ingesta y privacidad: registros del chatbot con referencias seudónimas de paciente y contacto; sin datos clínicos
     ni teléfonos en claro.
  2. Agrupación candidata: sesiones que comparten rastros se juntan en un "punto". Un punto es una agrupación candidata,
     no una identidad.
  3. Detección: patrones HG-01 a HG-07 y un Isolation Forest local sobre las características de cada punto.
  4. Validación HBVF: cada patrón se contrasta con su explicación legítima (cuidador, operador autorizado, red
     compartida). Si falta información, el patrón queda "desconocido", nunca culpable. Los indicadores de la misma
     familia no cuentan como evidencias independientes.
  5. Priorización: anomalía, confianza y riesgo sanitario van separados. El puntaje no es probabilidad de fraude.
  6. Recomendación: mitigaciones no excluyentes. Nada se cancela ni se bloquea de forma automática.

Los componentes mínimos del informe 14.4 viven en el paquete `hbvf` (catálogo JSON, validación de patrones,
mitigaciones consultivas, métricas y persistencia SQLite); este módulo es la fachada pública que conserva la
firma `analizar(...)` y el contrato de salida.
"""
from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from . import config
from .hbvf import almacen
from .hbvf.behavior_validation import cargar_catalogo, validar
from .hbvf.mitigation_engine import MITIGACIONES, textos_consultivos
from .hbvf.model_evaluation import evaluar
from .ingesta import codificacion

_CATALOGO = cargar_catalogo()
CATALOGO = _CATALOGO["patrones"]
PESO_FAMILIA = _CATALOGO["peso_familia"]

COLUMNAS = ["evento_id", "cita_id", "fecha_hora", "accion", "canal", "sesion", "paciente_ref", "contacto_ref",
            "rol_declarado", "autorizacion_ref", "ip", "ja4", "user_agent", "respuesta_ms", "especialidad", "unidad"]


def referencia_contacto(texto: str) -> str:
    """Seudónimo de un teléfono o correo de contacto. El backend usa la misma función para cruzar denuncias (HG-07)."""
    limpio = "".join(ch for ch in str(texto).lower() if ch.isalnum() or ch in "@.-_")
    return "CT-" + hashlib.sha256((config.SAL_CONTACTO + limpio).encode()).hexdigest()[:10].upper() if limpio else ""


# ---------- lectura ----------
def leer(ruta: Path) -> pd.DataFrame:
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding=codificacion(ruta), encoding_errors="replace",
                     on_bad_lines="skip")
    for c in COLUMNAS:
        if c not in df:
            df[c] = ""
        df[c] = df[c].astype(str).str.strip()
    df["ts"] = pd.to_datetime(df["fecha_hora"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    df = df[df["ts"].notna()].copy()
    df["accion"] = df["accion"].str.lower()
    df["canal"] = df["canal"].str.lower()
    df["rol_declarado"] = df["rol_declarado"].str.lower()
    df["respuesta_ms"] = pd.to_numeric(df["respuesta_ms"], errors="coerce")
    return df.sort_values("ts").reset_index(drop=True)


@dataclass
class TablaRedes:
    inicio: np.ndarray
    fin: np.ndarray
    tipo: list
    nombre: list

    @classmethod
    def desde_csv(cls, ruta: Path) -> TablaRedes:
        t = pd.read_csv(ruta, dtype=str)
        redes = [ipaddress.ip_network(r, strict=False) for r in t["red"]]
        orden = np.argsort([int(r.network_address) for r in redes])
        t = t.iloc[orden].reset_index(drop=True)
        redes = [redes[i] for i in orden]
        return cls(np.array([int(r.network_address) for r in redes], dtype="int64"),
                   np.array([int(r.broadcast_address) for r in redes], dtype="int64"),
                   t["tipo"].tolist(), (t["asn"] + " " + t["organizacion"]).tolist())

    def buscar(self, ips: pd.Series) -> pd.DataFrame:
        def a_int(x):
            try:
                return int(ipaddress.IPv4Address(x))
            except ValueError:
                return -1
        n = ips.map(a_int).to_numpy(dtype="int64")
        k = np.searchsorted(self.inicio, n, side="right") - 1
        ok = (k >= 0) & (n >= 0) & (n <= self.fin[np.clip(k, 0, None)])
        return pd.DataFrame({"tipo_red": [self.tipo[i] if o else "desconocida" for i, o in zip(k, ok, strict=False)],
                             "red": [self.nombre[i] if o else "" for i, o in zip(k, ok, strict=False)]}, index=ips.index)


def enriquecer(df: pd.DataFrame, redes: TablaRedes | None) -> pd.DataFrame:
    df = df.copy()
    if redes is not None:
        df = df.join(redes.buscar(df["ip"]))
    else:
        df["tipo_red"], df["red"] = "desconocida", ""
    df.loc[df["ip"].eq(""), "tipo_red"] = ""
    # JA4_a = t13d1516h2: los 2 últimos caracteres son el ALPN; un navegador negocia h2/h1, "00" es un cliente sin ALPN
    df["no_navegador"] = df["ja4"].ne("") & df["ja4"].str.slice(8, 10).eq("00")
    df["red_oculta"] = df["tipo_red"].isin(config.CITAS_REDES_OCULTAS)
    return df


# ---------- agrupación candidata ----------
class _Union:
    def __init__(self, n):
        self.p = list(range(n))

    def raiz(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def unir(self, a, b):
        ra, rb = self.raiz(a), self.raiz(b)
        if ra != rb:
            self.p[rb] = ra


def agrupar(df: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Devuelve el punto de cada evento y cuántas uniones hizo cada vínculo (para mostrar su calidad)."""
    ses = df.groupby("sesion").agg(contacto=("contacto_ref", "first"), ja4=("ja4", "first"), ua=("user_agent", "first"),
                                   ip=("ip", "first"), tipo=("tipo_red", "first"), red=("red", "first"),
                                   ts=("ts", "min"), no_nav=("no_navegador", "max"))
    ses["huella"] = ses["ja4"] + "|" + ses["ua"]
    idx = {s: i for i, s in enumerate(ses.index)}
    u = _Union(len(ses))
    vinculos = {}

    def unir_por(nombre, grupos):
        n = 0
        for _, g in grupos:
            ids = [idx[s] for s in g.index]
            for b in ids[1:]:
                u.unir(ids[0], b)
                n += 1
        vinculos[nombre] = n

    unir_por("mismo contacto", ses[ses["contacto"] != ""].groupby("contacto"))
    # celular que reinicia la conexión: misma huella y red, cadenas de >= 3 sesiones seguidas con IPs distintas
    ses["trio"] = ses["huella"] + "|" + ses["red"]
    prev = ses["trio"].map(ses["trio"].value_counts()) / len(ses)
    cand = ses[(ses["ja4"] != "") & (prev < config.CITAS_CADENA_PREVALENCIA)].sort_values("ts")
    limite = np.timedelta64(config.CITAS_CADENA_MIN, "m")
    n = 0
    for _, g in cand.groupby("trio"):
        tramo = np.cumsum(np.concatenate(([True], np.diff(g["ts"].to_numpy()) > limite)))
        todos = [idx[x] for _, c in g.groupby(tramo)
                 if len(c) >= config.CITAS_CADENA_SESIONES and c["ip"].nunique() >= config.CITAS_CADENA_SESIONES
                 for x in c.index]
        for b in todos[1:]:
            u.unir(todos[0], b)
            n += 1
    vinculos["rotación de IP con la misma huella"] = n
    unir_por("programa que no es navegador", ses[(ses["ja4"] != "") & ses["no_nav"]].groupby("huella"))
    oculta = ses[(ses["ja4"] != "") & ses["tipo"].isin(config.CITAS_REDES_OCULTAS)]
    unir_por("misma huella desde nube o VPN", oculta.groupby([oculta["huella"], oculta["tipo"],
                                                               oculta["ts"].dt.floor("D")]))
    fija = ses[(ses["ip"] != "") & ses["tipo"].isin(["residencial", "institucional"])]
    unir_por("misma IP fija en la misma hora", fija.groupby([fija["ip"], fija["ts"].dt.floor("h")]))
    raiz = pd.Series([u.raiz(idx[s]) for s in ses.index], index=ses.index)
    return df["sesion"].map(raiz), vinculos


# ---------- medir ----------
def _reasignaciones(df: pd.DataFrame) -> pd.Series:
    x = df[df["accion"].isin(["reserva", "cancelacion"]) & (df["cita_id"] != "")].sort_values(["cita_id", "ts"])
    p = x.shift(1)
    ok = ((x["cita_id"] == p["cita_id"]) & (p["accion"] == "cancelacion") & (x["accion"] == "reserva")
          & (x["paciente_ref"] != p["paciente_ref"])
          & ((x["ts"] - p["ts"]).dt.total_seconds() <= config.CITAS_REASIGNACION_SEG))
    return ok.groupby(x["punto"]).sum()


def medir(df: pd.DataFrame) -> pd.DataFrame:
    res = df[df["accion"] == "reserva"]
    can = df[df["accion"] == "cancelacion"]
    g, gr = df.groupby("punto"), res.groupby("punto")
    dias = max(1, (df["ts"].max() - df["ts"].min()).days + 1)
    canales = df[["punto", "canal"]].drop_duplicates().sort_values("canal").groupby("punto")["canal"].agg(", ".join)
    m = pd.DataFrame({
        "sesiones": g["sesion"].nunique(), "canales": canales, "inicio": g["ts"].min(), "fin": g["ts"].max(),
        "pct_red_oculta": g["red_oculta"].mean(), "no_navegador": g["no_navegador"].max(),
        "con_datos_tecnicos": g["ja4"].agg(lambda s: bool((s != "").any())),
        "con_tiempos": g["respuesta_ms"].agg(lambda s: bool(s.notna().any())),
        "ips": df[df["ip"] != ""].groupby("punto")["ip"].nunique(),
        "contactos": df[df["contacto_ref"] != ""].groupby("punto")["contacto_ref"].nunique(),
        "rol": g["rol_declarado"].agg(lambda s: next((x for x in s if x), "")),
        "autorizado": g["autorizacion_ref"].agg(lambda s: bool((s != "").any())),
    })
    m["reservas"] = gr.size()
    m["pacientes"] = gr["paciente_ref"].nunique()
    m["cancelaciones"] = can.groupby("punto").size()
    m["respuesta_mediana_ms"] = gr["respuesta_ms"].median()
    apertura = res["ts"].dt.hour.eq(config.CITAS_HORA_APERTURA) & (res["ts"].dt.minute < config.CITAS_MINUTOS_APERTURA)
    m["reservas_al_abrir"] = apertura.groupby(res["punto"]).sum()
    m["reasignaciones"] = _reasignaciones(df)
    m = m.fillna({"reservas": 0, "pacientes": 0, "cancelaciones": 0, "reservas_al_abrir": 0, "reasignaciones": 0,
                  "ips": 0, "contactos": 0})
    m["pacientes_por_semana"] = m["pacientes"] / (dias / 7)
    return m


def anomalia(m: pd.DataFrame) -> pd.Series:
    cols = ["sesiones", "ips", "reservas", "pacientes", "cancelaciones", "reservas_al_abrir", "reasignaciones",
            "pct_red_oculta"]
    X = m[cols].astype(float).copy()
    X["rapidez"] = 1 / (m["respuesta_mediana_ms"].fillna(m["respuesta_mediana_ms"].median()).clip(lower=50) / 1000)
    X = np.log1p(X.clip(lower=0))
    if len(X) < 10:
        return pd.Series(0.0, index=m.index)
    modelo = IsolationForest(n_estimators=200, random_state=config.SEMILLA, n_jobs=-1).fit(X)
    b = -modelo.score_samples(X)
    return pd.Series(np.round((b - b.min()) / ((b.max() - b.min()) or 1), 2), index=m.index)


def _persistir(ruta_db: Path, ruta: Path, filas: int, casos: list[dict]) -> None:
    """Registra fuente, catálogo y decisiones en SQLite (informe 14.4). Solo agrega bitácora: no modifica citas."""
    conn = almacen.abrir(ruta_db)
    try:
        almacen.crear_esquema(conn)
        almacen.guardar_fuente(conn, ruta=ruta, tipo="csv_citas_chatbot", filas=filas,
                               sha256=almacen.hash_archivo(ruta))
        almacen.guardar_patrones(conn, _CATALOGO)
        almacen.guardar_decisiones(conn, casos)
        conn.commit()
    finally:
        conn.close()


def analizar(ruta: Path, ruta_redes: Path | None = None, reportados_contacto: set | None = None,
             origen: str = "", ruta_db: Path | None = None) -> dict:
    """Devuelve el contrato de salida del módulo (informe, 14.4).

    Con ``ruta_db`` además persiste fuentes, patrones y decisiones en SQLite; nunca
    cancela ni bloquea nada (S10).
    """
    redes = TablaRedes.desde_csv(ruta_redes) if ruta_redes and Path(ruta_redes).exists() else None
    df = enriquecer(leer(ruta), redes)
    df["punto"], vinculos = agrupar(df)
    m = medir(df)
    reportados = set()
    if reportados_contacto:
        reportados = set(df.loc[df["contacto_ref"].isin(reportados_contacto), "punto"])
    res = {p: validar(r, reportados) for p, r in m.iterrows()}
    anom = anomalia(m)
    casos = []
    for p, v in sorted(res.items(), key=lambda kv: (-kv[1]["riesgo"], -kv[1]["confianza"])):
        if v["estado"] in ("Sin hallazgo",):
            continue
        r = m.loc[p]
        x = df[df["punto"] == p]
        cid = "AG-" + hashlib.sha256(f"{p}|{r['inicio']}".encode()).hexdigest()[:6].upper()
        casos.append({
            "case_id": cid, "pattern_ids": [k for k, e in v["patrones"].items() if e == "presente"],
            "patrones": v["patrones"], "anomaly_score": float(anom[p]), "confidence": v["confianza"],
            "risk_score": v["riesgo"], "probabilidad": v["probabilidad"], "impacto": v["impacto"],
            "status": v["estado"], "review_required": v["revision_requerida"],
            "evidence_refs": x["evento_id"].head(15).tolist(),
            "legitimate_explanations": v["explicaciones_legitimas"],
            "recommendations": textos_consultivos(v["recomendaciones"]),
            "dataset_origin": origen or Path(ruta).name,
            "resumen": {"sesiones": int(r["sesiones"]), "canales": r["canales"], "ips": int(r["ips"]),
                        "contactos": int(r["contactos"]), "reservas": int(r["reservas"]),
                        "pacientes": int(r["pacientes"]), "cancelaciones": int(r["cancelaciones"]),
                        "reasignaciones": int(r["reasignaciones"]), "reservas_al_abrir": int(r["reservas_al_abrir"]),
                        "respuesta_mediana_ms": None if pd.isna(r["respuesta_mediana_ms"])
                        else int(r["respuesta_mediana_ms"]),
                        "rol_declarado": r["rol"] or None, "representacion_autorizada": bool(r["autorizado"]),
                        "inicio": r["inicio"].strftime("%Y-%m-%dT%H:%M:%S"),
                        "fin": r["fin"].strftime("%Y-%m-%dT%H:%M:%S")},
            "citas_en_revision": sorted(set(x.loc[x["accion"] == "reserva", "cita_id"]))[:200]
            if v["revision_requerida"] else [],
            "contactos_ref": sorted(set(x.loc[x["contacto_ref"] != "", "contacto_ref"])),
        })
    estados = pd.Series([v["estado"] for v in res.values()]).value_counts().to_dict()
    salida = {
        "dataset_origin": origen or Path(ruta).name, "catalogo": CATALOGO, "mitigaciones": MITIGACIONES,
        "vinculos_de_agrupacion": vinculos,
        "resumen": {"eventos": int(len(df)), "sesiones": int(df["sesion"].nunique()), "puntos": int(len(m)),
                    "reservas": int((df["accion"] == "reserva").sum()), "estados": estados,
                    "revision_requerida": int(sum(v["revision_requerida"] for v in res.values())),
                    "citas_en_revision": int(sum(len(c["citas_en_revision"]) for c in casos)),
                    "periodo": {"desde": df["ts"].min().strftime("%Y-%m-%d"),
                                "hasta": df["ts"].max().strftime("%Y-%m-%d")}},
        "casos": casos, "evaluacion": evaluar(df, m, res),
        "principios": ["Un punto es una agrupación candidata, no una identidad.",
                       "JA4, red y contacto son señales auxiliares sujetas a colisiones y uso compartido.",
                       "Las señales faltantes se marcan como desconocidas, no como culpa.",
                       "Indicadores de la misma familia no cuentan como evidencias independientes.",
                       "Ninguna cita se cancela ni se bloquea de forma automática."],
    }
    if ruta_db is not None:
        _persistir(ruta_db, ruta, len(df), casos)
    return salida
