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
from .ingesta import codificacion

COLUMNAS = ["evento_id", "cita_id", "fecha_hora", "accion", "canal", "sesion", "paciente_ref", "contacto_ref",
            "rol_declarado", "autorizacion_ref", "ip", "ja4", "user_agent", "respuesta_ms", "especialidad", "unidad"]

CATALOGO = [
    {"id": "HG-01", "nombre": "Muchos pacientes distintos desde un mismo origen", "familia": "volumen",
     "fuente": "Zou et al. (2026)", "contexto_legitimo": "Cuidador, familiar u operador autorizado",
     "validacion": "Rol, canal y representación autorizada"},
    {"id": "HG-02", "nombre": "Operaciones más rápidas que una persona", "familia": "ritmo",
     "fuente": "Zou et al. (2026); OWASP API6:2023", "contexto_legitimo": "Operador capacitado o tecnología de asistencia",
     "validacion": "Línea base del mismo canal; repetición y contexto"},
    {"id": "HG-03", "nombre": "Cancelaciones recurrentes", "familia": "ciclo_de_cita",
     "fuente": "Zou et al. (2026); Dantas et al. (2018)", "contexto_legitimo": "Cambio de horario, enfermedad, transporte",
     "validacion": "Estado real de las citas y explicación operativa"},
    {"id": "HG-04", "nombre": "Reservas concentradas al abrir la agenda", "familia": "momento",
     "fuente": "OWASP API6:2023; OAT-005", "contexto_legitimo": "Demanda acumulada o campaña autorizada",
     "validacion": "Capacidad ofertada y demanda por especialidad"},
    {"id": "HG-05", "nombre": "Cita cancelada y reasignada enseguida a otro paciente", "familia": "ciclo_de_cita",
     "fuente": "Hipótesis propia del equipo", "contexto_legitimo": "Reasignación normal de turnos",
     "validacion": "Historial de la cita y corroboración independiente"},
    {"id": "HG-06", "nombre": "Señales técnicas coincidentes (huella JA4, red, rotación de IP)", "familia": "tecnica",
     "fuente": "FoxIO JA4+", "contexto_legitimo": "Red o dispositivo compartido",
     "validacion": "Calidad de los vínculos; nunca atribuir solo por JA4 o IP"},
    {"id": "HG-07", "nombre": "Oferta comercial de citas reportada por un ciudadano", "familia": "externa",
     "fuente": "Comunicado institucional (2025); OAT-005", "contexto_legitimo": "Reporte erróneo o manipulado",
     "validacion": "Autenticidad del reporte y relación con el caso"},
]
PESO_FAMILIA = {"volumen": 1.0, "momento": 1.0, "ritmo": 1.0, "ciclo_de_cita": 1.0, "tecnica": 0.5, "externa": 1.0}

MITIGACIONES = {
    "confirmacion": "Confirmar la reserva con el afiliado por su contacto ya verificado (no el que se dejó en el chat). "
                    "Puede confirmar, desconocer o pedir ayuda; no responder no le quita la cita.",
    "representacion": "Verificar si existe una representación autorizada (cuidador u operador) antes de actuar.",
    "educacion": "Informar a los pacientes de este punto sobre los canales oficiales y que las citas son gratuitas, "
                 "sin acusar a nadie.",
    "revision": "Revisión conjunta del SOC y el área de agendamiento; las reservas se preservan mientras se investiga.",
    "desafio": "Pedir una verificación adicional (por ejemplo, un CAPTCHA accesible) a las sesiones de este origen.",
    "lista_espera": "Si un paciente desconoce su cita, ofrecerla por la lista de espera según el procedimiento.",
    "seguimiento": "Medir reincidencia corroborada y posibles perjuicios a pacientes legítimos.",
}


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
    def desde_csv(cls, ruta: Path) -> "TablaRedes":
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
        return pd.DataFrame({"tipo_red": [self.tipo[i] if o else "desconocida" for i, o in zip(k, ok)],
                             "red": [self.nombre[i] if o else "" for i, o in zip(k, ok)]}, index=ips.index)


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


# ---------- validación HBVF ----------
def _estado_patron(presente: bool | None, explicado: bool = False) -> str:
    if presente is None:
        return "desconocido"
    if presente and explicado:
        return "explicado"
    return "presente" if presente else "ausente"


def validar(r: pd.Series, reportados: set) -> dict:
    c = config
    autorizado = bool(r["autorizado"]) and r["rol"] in ("cuidador", "operador_autorizado")
    tecnica = None if not r["con_datos_tecnicos"] else bool(
        r["no_navegador"] or r["pct_red_oculta"] >= 0.5 or r["ips"] >= c.CITAS_IPS_ROTACION)
    patrones = {
        "HG-01": _estado_patron(r["pacientes_por_semana"] > c.CITAS_PACIENTES_SEMANA
                                or r["pacientes"] > c.CITAS_LIMITE_30_DIAS, explicado=autorizado),
        "HG-02": _estado_patron(None if not r["con_tiempos"] else
                                bool(r["respuesta_mediana_ms"] < c.CITAS_RESPUESTA_HUMANA_MS), explicado=autorizado),
        "HG-03": _estado_patron(r["cancelaciones"] >= c.CITAS_CANCELACIONES
                                and r["cancelaciones"] >= 0.3 * max(1, r["reservas"])),
        "HG-04": _estado_patron(r["reservas_al_abrir"] >= c.CITAS_AL_ABRIR),
        "HG-05": _estado_patron(r["reasignaciones"] >= 1),
        "HG-06": _estado_patron(tecnica, explicado=autorizado),
        "HG-07": "presente" if r.name in reportados else "ausente",
    }
    fam = {p["id"]: p["familia"] for p in CATALOGO}
    familias = {fam[k] for k, v in patrones.items() if v == "presente"}
    independientes = sum(PESO_FAMILIA[f] for f in familias)
    desconocidos = [k for k, v in patrones.items() if v == "desconocido"]
    explicados = [k for k, v in patrones.items() if v == "explicado"]
    presentes = [k for k, v in patrones.items() if v == "presente"]

    if not presentes and explicados:
        estado = "Explicado por contexto legítimo"
    elif independientes >= 3 or (independientes >= 2 and ("HG-05" in presentes or "HG-07" in presentes)):
        estado = "Revisión prioritaria"
    elif independientes >= 2:
        estado = "Requiere revisión"
    elif independientes >= 1 and len(desconocidos) >= 2:
        estado = "Indeterminado: falta información"
    elif independientes >= 1:
        estado = "Observación"
    else:
        estado = "Sin hallazgo"
    confianza = round(min(1.0, 0.22 * independientes + (0.12 if "HG-07" in presentes else 0)
                          - 0.05 * len(desconocidos)), 2)
    confianza = max(0.0, confianza)
    prob = 1 + min(4, int(round(independientes)))          # 1..5
    impacto = 5 if "HG-05" in presentes else 4             # disponibilidad y equidad del acceso a la salud
    legitimas = [p["contexto_legitimo"] for p in CATALOGO if patrones[p["id"]] in ("presente", "explicado")]
    recomendaciones = []
    if estado in ("Revisión prioritaria", "Requiere revisión"):
        recomendaciones = ["confirmacion", "representacion", "revision", "educacion"]
        if patrones["HG-06"] == "presente" or patrones["HG-02"] == "presente":
            recomendaciones.append("desafio")
        if "HG-05" in presentes:
            recomendaciones.append("lista_espera")
        recomendaciones.append("seguimiento")
    elif estado.startswith("Indeterminado") or estado == "Observación":
        recomendaciones = ["representacion", "seguimiento"]
    return {"patrones": patrones, "estado": estado, "confianza": confianza, "evidencia_independiente": independientes,
            "riesgo": prob * impacto, "probabilidad": prob, "impacto": impacto,
            "explicaciones_legitimas": legitimas, "recomendaciones": recomendaciones,
            "revision_requerida": estado in ("Revisión prioritaria", "Requiere revisión")
            or estado.startswith("Indeterminado")}


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
    prec = vp / (vp + fp) if vp + fp else 0.0
    sens = vp / (vp + fn) if vp + fn else 0.0
    por_escenario = {}
    for esc, grupo in real.groupby(real):
        por_escenario[esc] = {"puntos": int(len(grupo)),
                              "marcados_para_revision": int(pred.reindex(grupo.index).sum()),
                              "estados": pd.Series([resultados[p]["estado"] for p in grupo.index]).value_counts()
                              .to_dict()}
    return {"nota": "Prueba preliminar con datos sintéticos y escenarios conocidos; no demuestra eficacia real.",
            "matriz": {"vp": vp, "fp": fp, "fn": fn, "vn": vn}, "precision": round(prec, 3),
            "sensibilidad": round(sens, 3), "tasa_falsos_positivos": round(fp / (fp + vn), 4) if fp + vn else 0.0,
            "f1": round(2 * prec * sens / (prec + sens), 3) if prec + sens else 0.0, "por_escenario": por_escenario}


def analizar(ruta: Path, ruta_redes: Path | None = None, reportados_contacto: set | None = None,
             origen: str = "") -> dict:
    """Devuelve el contrato de salida del módulo (informe, 14.4)."""
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
            "recommendations": [{"id": k, "texto": MITIGACIONES[k]} for k in v["recomendaciones"]],
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
    return {
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
