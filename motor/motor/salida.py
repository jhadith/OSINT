"""Convierte los hallazgos al contrato de salida (salidas/alertas.json, resumen_motor.json, ml.json).
Antes de escribir, los nombres y usuarios de personas pasan a seudónimos. La sal y la tabla de reidentificación
quedan en restringido/, que no se sube a Git ni se entrega a la API."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import secrets
from pathlib import Path

import pandas as pd

from . import config, priorizacion as pr
from .hallazgo import Hallazgo
from .ingesta import fecha

GRAV = ["Crítica", "Alta", "Media", "Baja"]


class Seudonimos:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        carpeta.mkdir(parents=True, exist_ok=True)
        f = carpeta / "sal.txt"
        if not f.exists():
            f.write_text(secrets.token_hex(16), encoding="utf-8")
        self.sal = f.read_text(encoding="utf-8").strip()
        self.tabla: dict[str, str] = {}

    def __call__(self, valor: str, prefijo: str) -> str:
        v = (valor or "").strip()
        if not v:
            return ""
        c = f"{prefijo}-" + hashlib.sha256((self.sal + v).encode("utf-8")).hexdigest()[:6].upper()
        self.tabla[c] = v
        return c

    def guardar(self) -> None:
        with open(self.carpeta / "tabla_reidentificacion.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["seudonimo", "valor_real"])
            w.writerows(sorted(self.tabla.items()))


def _ts(s: int) -> str:
    return fecha(s).strftime("%Y-%m-%d %H:%M:%S")


def linea(h: Hallazgo, filas_fw: pd.DataFrame, med: pd.DataFrame, maximo: int = 40) -> list[dict]:
    eventos = []
    if h.filas_fw and len(filas_fw):
        x = filas_fw[filas_fw["fila"].isin(h.filas_fw)].copy()
        x["min"] = x["Fecha_Generacion"].str.slice(0, 16)
        nota = f" (reloj {h.desfase_h * -1:+d} h)" if h.desfase_h else ""
        x["evento"] = "Puerto " + x["Puerto_Destino"] + " " + x["Accion"].str.lower() + nota
        for (m, e), n in x.groupby(["min", "evento"]).size().items():
            eventos.append({"fecha_hora": m + ":00", "fuente": "Firewall", "evento": e, "cantidad": int(n)})
    if h.idx_med:
        y = med.loc[h.idx_med, ["s", "accion"]]
        paso = 60 if y["s"].max() - y["s"].min() <= 7200 else 3600   # por minuto, o por hora si dura mucho
        y = y.assign(min=(y["s"] // paso) * paso, accion=y["accion"].astype(str))
        for (m, a), n in y.groupby(["min", "accion"]).size().items():
            eventos.append({"fecha_hora": _ts(m), "fuente": "Sistema médico", "evento": a.capitalize(),
                            "cantidad": int(n)})
    eventos.sort(key=lambda e: (e["fecha_hora"], e["fuente"]))
    return eventos[:maximo]


def alerta(h: Hallazgo, seud: Seudonimos, filas_fw: pd.DataFrame, med: pd.DataFrame) -> dict:
    t = pr.tipo(h)
    if h.general:
        prob, imp, punt = 3, 3, 9
    elif h.solo_ml:
        prob, imp, punt = 2, 2, 4          # revisión sugerida: el modelo la marca, ninguna regla la confirma
    else:
        prob, imp = pr.puntaje(h)
        punt = prob * imp
    clave = f"{h.regla}|{h.ip}|{h.cuenta}|{h.inicio}"
    return {
        "id": "A-" + hashlib.sha256(clave.encode()).hexdigest()[:8].upper(),
        "caso": None, "regla": h.regla, "titulo": pr.TITULO[t], "gravedad": pr.gravedad(punt), "puntaje": punt,
        "probabilidad": prob, "impacto": imp, "fuente": h.fuente, "inicio": _ts(h.inicio), "fin": _ts(h.fin),
        "ip_origen": h.ip, "cuenta": h.cuenta,
        "usuario_firewall": seud(h.usuarios[0], "U") if h.usuarios else "",
        "persona": seud(h.personas[0], "P") if h.personas else "",
        "tecnicas": h.tecnicas, "eventos_firewall": h.eventos_fw, "eventos_sistema_medico": h.eventos_med,
        "resumen": pr.resumen(h, t), "acciones": pr.acciones(h, t), "riesgo": pr.RIESGO[t], "cid": pr.CID[t],
        "salvaguarda_hipaa": pr.HIPAA.get(t, ""), "desfase_reloj_h": h.desfase_h, "ml": h.ml,
        "segmento_servidor": h.segmento, "evidencia": h.evidencia, "tipo": t,
        "linea": linea(h, filas_fw, med),
    }


# Numeración del informe: 1 fuerza bruta, 2 escaneo, 3 fuga de datos, 4 cuenta fantasma; otros después, por fecha
ORDEN_CASOS = ["fuerza_bruta", "fallidos_masivos", "escaneo", "rafaga_ssh", "extraccion_masiva", "cuenta_rara"]


def _orden_caso(a: dict):
    t = pr.tipo(a["regla"])
    return (ORDEN_CASOS.index(t) if t in ORDEN_CASOS else len(ORDEN_CASOS), a["inicio"])


def numerar(alertas: list[dict]) -> list[dict]:
    """Casos = ataques confirmados por ambas fuentes. Orden final de la lista: gravedad e inicio."""
    for n, a in enumerate(sorted((a for a in alertas if a["fuente"] == "correlacion"), key=_orden_caso), 1):
        a["caso"] = f"Caso {n}"
    return sorted(alertas, key=lambda a: (GRAV.index(a["gravedad"]), a["inicio"]))


def limpiar(texto: str) -> str:
    """Las etiquetas de los datos traen el nombre de la institución (p. ej. "INGRESO SIST_MED_IESS"). La ficha del
    reto no permite textos institucionales en la simulación, así que se cambian por términos neutros."""
    texto = re.sub(r"sist[_ ]?med[_ ]?iess", "sistema médico", texto, flags=re.IGNORECASE)
    return re.sub(r"\biess\b", "institución", texto, flags=re.IGNORECASE)


def escribir(carpeta: Path, alertas: list[dict], resumen: dict, ml: dict) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, obj in (("alertas.json", alertas), ("resumen_motor.json", resumen), ("ml.json", ml)):
        (carpeta / nombre).write_text(limpiar(json.dumps(obj, ensure_ascii=False, indent=2)), encoding="utf-8")
