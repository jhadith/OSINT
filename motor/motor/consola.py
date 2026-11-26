"""Salida para la consola web (frontend osit): escribe salidas/consola/*.json con las formas exactas de
frontend/src/api/types.ts. El backend solo lee estos archivos y les suma el estado (decisiones, bitácora, Telegram).

Los rangos de referencia (refMin, refMax) salen de los mismos datos: percentiles del comportamiento normal del mes,
como los valores de referencia de un examen de laboratorio.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, priorizacion as pr
from .ingesta import fecha
from .reglas_med import _acciones
from .salida import limpiar

MITRE = {"T1110": "Fuerza bruta", "T1046": "Descubrimiento de servicios de red", "T1021.004": "Servicios remotos: SSH",
         "T1048": "Exfiltración por protocolo alternativo", "T1078": "Cuentas válidas",
         "T1098": "Manipulación de cuentas", "T1213": "Datos de repositorios de información"}
SERVICIO = {22: "SSH", 23: "Telnet", 137: "NetBIOS", 138: "NetBIOS", 139: "NetBIOS", 445: "SMB", 3389: "RDP"}
GRAV = {"Crítica": "critica", "Alta": "alta", "Media": "media", "Baja": "baja"}
TITULO = {"fuerza_bruta": "Fuerza bruta", "fallidos_masivos": "Accesos fallidos masivos",
          "escaneo": "Escaneo de servicios", "rafaga_ssh": "Posible fuga de datos",
          "extraccion_masiva": "Posible fuga de datos", "cuenta_rara": "Cuenta fantasma"}
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
UMBRAL_ML = 0.8          # puntuación (0-1) desde la que una entidad queda marcada para revisión
PUESTO_ML = 50           # el modelo "detectó" un caso si lo puso entre los 50 primeros
NS = uuid.uuid5(uuid.NAMESPACE_URL, "espethreat-sentinel-salud")


def _iso(txt: str) -> str:
    return txt.replace(" ", "T")


def _ts(s: int) -> str:
    return fecha(s).strftime("%Y-%m-%dT%H:%M:%S")


def _p(x, q, minimo=0.0) -> float:
    x = np.asarray(x, dtype="float64")
    return float(round(max(minimo, np.percentile(x, q)), 1)) if len(x) else minimo


def _med(nombre, valor, ref_min, ref_max, unidad, nota=None) -> dict:
    m = {"nombre": nombre, "valor": float(valor), "refMin": float(ref_min), "refMax": float(ref_max), "unidad": unidad}
    if nota:
        m["nota"] = nota
    return m


def _fuera(m: dict) -> bool:
    return m["valor"] > m["refMax"] or m["valor"] < m["refMin"]


# ---------- líneas base ----------
def lineas_base(fw: pd.DataFrame, med: pd.DataFrame, ips_casos: set[int], cuentas_fuera: set[str]) -> dict:
    """Comportamiento normal del periodo, sin las IPs ni las cuentas de los casos y hallazgos."""
    normal = fw[~fw["iph"].isin(ips_casos)]
    por_ip = normal["iph"].value_counts()
    puertos_ip = normal[normal["srv"]].groupby("iph")["p"].nunique()
    ssh = fw[fw["srv"] & fw["ssh"] & ~fw["neg"]]
    ssh_seg = ssh.groupby(["iph", "s"]).size()
    eventos_cuenta = med.groupby("cuenta", observed=True).size()
    personas = med.groupby("cuenta", observed=True)["persona"].nunique()
    m = med[~med["cuenta"].astype(str).isin(cuentas_fuera)]
    fall = m[_acciones(m, config.PATRON_FALLIDO)]
    sens = m[_acciones(m, config.PATRON_SENSIBLE)]
    ev_n = eventos_cuenta[~eventos_cuenta.index.astype(str).isin(cuentas_fuera)]
    pe_n = personas[~personas.index.astype(str).isin(cuentas_fuera)]
    return {
        "ip_mes": _p(por_ip, 99.9, 1), "puertos_ip": _p(puertos_ip, 99.9, 1), "ssh_seg": _p(ssh_seg, 99, 1),
        "fallidos_dia": _p(fall.groupby(["cuenta", fall["s"] // 86400], observed=True).size(), 99, 1),
        "sensibles_min": _p(sens.groupby(["cuenta", sens["s"] // 60], observed=True).size(), 99.9, 1),
        "fallidos_hora": _p(fall.groupby(fall["s"] // 3600).size(), 99, 1),
        "eventos_mes_min": _p(ev_n, 1), "eventos_mes_max": _p(ev_n, 99),
        "personas_max": _p(pe_n, 99, 1),
    }, eventos_cuenta, personas


# ---------- casos ----------
def _mediciones_fw(efw: dict, filas: pd.DataFrame, base: dict) -> list[dict]:
    if not efw.get("eventos"):
        return []
    dur = pr.duracion(efw.get("duracion_seg", 0))
    ms = [_med("Intentos desde la IP", efw["eventos"], 0, base["ip_mes"], f"en {dur}",
               "Una IP normal no pasa de este número en todo el mes")]
    if "negados" in efw:
        ms.append(_med("Intentos negados", efw["negados"], 0, base["ip_mes"], "intentos"))
    ms.append(_med("Puertos distintos", len(efw.get("puertos", [])), 0, base["puertos_ip"], "puertos"))
    if 22 in efw.get("puertos", []) and len(filas):
        pico = filas.groupby("Fecha_Generacion").size().max()
        ms.append(_med("Conexiones SSH permitidas por segundo (pico)", pico, 0, base["ssh_seg"], "/s"))
    return ms


def _mediciones_med(emed: dict, cuenta: str, idx: list, med: pd.DataFrame, base: dict, eventos_cuenta, personas):
    if not cuenta or cuenta not in eventos_cuenta.index:
        return []
    acc = emed.get("acciones", {})
    ms = []
    fallidos = sum(v for k, v in acc.items() if "FALLID" in k.upper())
    if fallidos:
        ms.append(_med("Accesos fallidos de la cuenta en el día", fallidos, 0, base["fallidos_dia"], "en el día"))
    if idx:
        x = med.loc[idx]
        x = x[_acciones(x, config.PATRON_SENSIBLE)]
        if len(x):
            pico = x.groupby(x["s"] // 60).size().max()
            ms.append(_med("Transferencias o descargas por minuto (pico)", pico, 0, base["sensibles_min"], "/min"))
    ms.append(_med("Eventos de la cuenta en el mes", eventos_cuenta[cuenta], base["eventos_mes_min"],
                   base["eventos_mes_max"], "eventos"))
    ms.append(_med("Personas distintas en la cuenta", personas[cuenta], 1, base["personas_max"], "personas"))
    return ms


def _registros_fw(filas: pd.DataFrame) -> list[dict]:
    return [{"ts": r["Fecha_Generacion"], "campos": {"ip_origen": r["IP_Origen"], "ip_destino": r["IP_Destino"],
                                                     "puerto": r["Puerto_Destino"], "protocolo": r["Protocolo"],
                                                     "aplicacion": r["Aplicacion"], "accion": r["Accion"]}}
            for _, r in filas.head(8).iterrows()]


def _registros_med(idx: list, med: pd.DataFrame, seud) -> list[dict]:
    x = med.loc[idx[:8]]
    return [{"ts": fecha(int(r["s"])).strftime("%Y-%m-%d %H:%M:%S"),
             "campos": {"cuenta": str(r["cuenta"]), "usuario": seud(str(r["persona"]), "P"),
                        "evento": limpiar(str(r["accion"])), "ip": str(r["ip"])}} for _, r in x.iterrows()]


def _protocolo(puertos: list[int]) -> str:
    if len(puertos) == 1:
        return f"{SERVICIO.get(puertos[0], 'TCP')}/{puertos[0]}"
    return f"{len(puertos)} puertos" if puertos else ""


def _tipo_texto(t: str, puertos: list[int]) -> str:
    if t == "fuerza_bruta":
        return "Fuerza bruta por " + (SERVICIO.get(puertos[0], f"el puerto {puertos[0]}") if puertos else "red")
    return {"escaneo": "Descubrimiento de servicios de red", "rafaga_ssh": "Exfiltración por SSH",
            "extraccion_masiva": "Extracción masiva de datos", "cuenta_rara": "Uso de cuenta válida de un solo uso",
            "fallidos_masivos": "Fuerza bruta contra cuentas"}.get(t, t)


def mensaje_telegram(c: dict) -> str:
    return ("SENTINEL SALUD · AMENAZA CRÍTICA\n"
            f"Caso {c['id']} · {c['titulo']}\n"
            f"Inicio: {pd.Timestamp(c['inicio']).strftime('%d/%m/%Y %H:%M')}\n"
            f"MITRE ATT&CK: {', '.join(t['id'] for t in c['tecnicas'])}\n"
            f"Acción sugerida: {c['acciones'][0] if c['acciones'] else 'revisar en la consola'}.\n"
            "Sin datos personales. Detalle en la consola local.")


def caso(h, a: dict, filas_fw: pd.DataFrame, med: pd.DataFrame, base: dict, eventos_cuenta, personas, seud,
         total_fw: int) -> dict:
    t = a["tipo"]
    ev = a["evidencia"]
    efw = ev.get("firewall", ev if a["fuente"] == "firewall" else {})
    emed = ev.get("sistema_medico", ev if a["fuente"] == "sistema_medico" else {})
    filas = filas_fw[filas_fw["fila"].isin(h.filas_fw)] if h.filas_fw else filas_fw.iloc[0:0]
    puertos = efw.get("puertos", [])
    m_fw = _mediciones_fw(efw, filas, base)
    m_med = _mediciones_med(emed, a["cuenta"], h.idx_med, med, base, eventos_cuenta, personas)
    extra = [_med("Desfase de reloj entre fuentes", abs(a["desfase_reloj_h"]), 0, 0.1, "h",
                  "Firewall frente al sistema médico")] if a["desfase_reloj_h"] else []
    explicacion = [m for m in m_fw + m_med + extra if _fuera(m)][:4] or (m_fw + m_med)[:3]
    ml = a.get("ml", {})
    candidatos = [v for v in ml.values() if v.get("puesto")]
    mejor = min(candidatos, key=lambda v: v["puesto"] / v["de"]) if candidatos else None
    detectado = ["Reglas"]
    if mejor and mejor["puesto"] <= PUESTO_ML:
        detectado.append("Machine learning")
    if a["fuente"] == "correlacion":
        detectado.append("Cruce de datasets")
    riesgos = [a["riesgo"]] + (["R5"] if a.get("segmento_servidor") else []) + (["R8"] if a["desfase_reloj_h"] else [])
    calidad = []
    if a["desfase_reloj_h"]:
        calidad.append(f"El reloj del firewall está desfasado {abs(a['desfase_reloj_h'])} h respecto del sistema médico; "
                       "el motor lo corrigió para cruzar las fuentes.")
    if a["cuenta"] and a["cuenta"] in eventos_cuenta.index:
        mal = int(med.loc[med["cuenta"] == a["cuenta"], "ipmal"].sum())
        if mal:
            calidad.append(f"{mal} registros de la cuenta tienen la IP mal escrita.")
    n = int(a["caso"].split()[1])
    c = {
        "id": f"C{n}", "titulo": TITULO.get(t, a["titulo"]), "tipo": _tipo_texto(t, puertos),
        "gravedad": GRAV[a["gravedad"]], "inicio": _iso(a["inicio"]),
        "duracion": pr.duracion(int((pd.Timestamp(a["fin"]) - pd.Timestamp(a["inicio"])).total_seconds())),
        "ipOrigen": a["ip_origen"], "ipDestino": config.SERVIDOR, "protocolo": _protocolo(puertos),
        "cuenta": a["cuenta"], "seudonimo": a["persona"], "resumen": a["resumen"],
        "tecnicas": [{"id": x, "nombre": MITRE.get(x, x)} for x in a["tecnicas"]],
        "riesgos": list(dict.fromkeys(riesgos)), "detectadoPor": detectado,
        "modelo": ({"puntuacion": round(mejor["puntaje"] / 100, 2), "puesto": mejor["puesto"], "total": mejor["de"]}
                   if mejor else {"puntuacion": 0, "puesto": None, "total": total_fw}),
        "explicacion": explicacion,
        "firewall": {"fuente": "firewall",
                     "resumen": (f"{pr.eventos(efw['eventos'])} desde {a['ip_origen']} hacia el servidor médico"
                                 if efw.get("eventos") else "Sin eventos asociados en el firewall"),
                     "mediciones": m_fw, "registros": _registros_fw(filas)},
        "sistemaMedico": {"fuente": "sistema_medico",
                          "resumen": (limpiar(", ".join(f"{v:,} {k.lower()}".replace(",", ".") for k, v in
                                                        emed.get("acciones", {}).items())) or "Sin eventos asociados"),
                          "mediciones": m_med, "registros": _registros_med(h.idx_med, med, seud) if h.idx_med else []},
        "recorrido": [
            {"paso": "Ingesta", "detalle": f"{pr.eventos(a['eventos_firewall'])} del firewall y "
                                           f"{pr.miles(a['eventos_sistema_medico'])} del sistema médico"},
            {"paso": "Privacidad", "detalle": f"La persona detrás de la cuenta pasa a ser {a['persona'] or 'un seudónimo'}"},
            {"paso": "Detección", "detalle": " + ".join(detectado) +
             (f"; puesto {mejor['puesto']} de {mejor['de']} en el modelo" if mejor else "")},
            {"paso": "Priorización y alerta", "detalle": f"{a['gravedad']} (puntaje {a['puntaje']} de 25)" +
             ("; aviso inmediato por Telegram" if a["gravedad"] == "Crítica" else "")},
            {"paso": "Decisión y respuesta", "detalle": "Pendiente de la decisión del analista"},
            {"paso": "Difusión", "detalle": "Reglas Sigma, IoC, STIX y MISP en la página de inteligencia"},
        ],
        "acciones": a["acciones"], "calidadDatos": calidad, "alerta": None, "estado": "pendiente", "decision": None,
        "_tipo": t, "_usuario_fw": h.usuarios[0] if h.usuarios else "", "_eventos_med": a["eventos_sistema_medico"],
    }
    if a["gravedad"] == "Crítica":
        c["alerta"] = {"enviada": False, "fecha": "", "texto": mensaje_telegram(c)}
    return c


# ---------- serie, anomalías, grafo ----------
def serie(fw: pd.DataFrame, med: pd.DataFrame, rf) -> list[dict]:
    h0, h1 = int(min(fw["s"].min(), med["s"].min()) // 3600), int(max(fw["s"].max(), med["s"].max()) // 3600)
    horas = pd.RangeIndex(h0, h1 + 1)
    fall = med[_acciones(med, config.PATRON_FALLIDO)]["s"] // 3600
    sens = med[_acciones(med, config.PATRON_SENSIBLE)]["s"] // 3600
    ssh = fw.loc[fw["srv"] & fw["ssh"] & ~fw["neg"], "s"] // 3600
    punt = (rf.tabla.groupby(rf.tabla["ventana"] // 3600)["puntaje"].max() / 100) if rf is not None else pd.Series(dtype=float)
    f = lambda x: x.value_counts().reindex(horas, fill_value=0)  # noqa: E731
    df = pd.DataFrame({"fallidos": f(fall), "ssh": f(ssh), "transferencias": f(sens),
                       "puntuacion": punt.reindex(horas).fillna(0).round(2)})
    return [{"ts": _ts(h * 3600), "puntuacion": float(r["puntuacion"]), "fallidos": int(r["fallidos"]),
             "ssh": int(r["ssh"]), "transferencias": int(r["transferencias"])} for h, r in df.iterrows()]


def anomalias(r, col: str, stats: pd.DataFrame, fuente: str, casos_por: dict, seud, ip_caso: dict) -> dict:
    if r is None:
        return {"fuente": fuente, "total": 0, "umbral": UMBRAL_ML, "filas": []}
    t = r.tabla.sort_values("puntaje", ascending=False).drop_duplicates(col)
    t = t.assign(ent=t[col].astype(str))
    top = pd.concat([t.head(100), t[t["ent"].isin(casos_por) & ~t.index.isin(t.head(100).index)]])
    filas = []
    for k, x in enumerate(top.itertuples(), 1):
        ent = x.ent
        st = stats.loc[ent] if ent in stats.index else None
        motivo = (x.por_que.split(" | ")[0] if x.por_que else "Sin rasgo destacado en su peor ventana")
        if fuente == "firewall":
            sd = seud(ent, "U")
            ident = ip_caso.get(ent, sd)
        else:
            sd = seud(ip_caso.get(ent, ""), "P") or "sin persona"
            ident = ent
        filas.append({"puesto": int((t["puntaje"] > x.puntaje).sum()) + 1, "id": ident, "seudonimo": sd,
                      "fuente": fuente, "puntuacion": round(float(x.puntaje) / 100, 2),
                      "eventos": int(st["eventos"]) if st is not None else 0,
                      "fallidos": int(st["fallidos"]) if st is not None else 0,
                      "diversidad": int(st["diversidad"]) if st is not None else 1, "motivo": limpiar(motivo),
                      "sospechosa": bool(x.puntaje / 100 > UMBRAL_ML), "casoId": casos_por.get(ent)})
    return {"fuente": fuente, "total": int(len(t)), "umbral": UMBRAL_ML, "filas": filas}


def grafo(casos: list[dict], generales: list, personas) -> dict:
    nodos = [{"id": "srv", "tipo": "servidor", "etiqueta": config.SERVIDOR,
              "detalle": "Servidor del sistema médico (historias clínicas)", "casoId": None, "gravedad": None}]
    aristas, vistos = [], {"srv"}
    for c in casos:
        ip, cta = f"ip-{c['ipOrigen']}", f"cta-{c['cuenta']}"
        if c["ipOrigen"] and ip not in vistos:
            nodos.append({"id": ip, "tipo": "ip", "etiqueta": c["ipOrigen"], "detalle": c["tipo"], "casoId": c["id"],
                          "gravedad": c["gravedad"]})
            vistos.add(ip)
            ev = c["firewall"]["mediciones"][0]["valor"] if c["firewall"]["mediciones"] else 0
            aristas.append({"origen": ip, "destino": "srv", "etiqueta": c["protocolo"] or "red", "eventos": int(ev)})
        if c["cuenta"] and cta not in vistos:
            nodos.append({"id": cta, "tipo": "cuenta", "etiqueta": c["cuenta"], "detalle": c["titulo"],
                          "casoId": c["id"], "gravedad": c["gravedad"],
                          "personas": int(personas.get(c["cuenta"], 1))})
            vistos.add(cta)
            if c["ipOrigen"]:
                aristas.append({"origen": ip, "destino": cta, "etiqueta": "usa", "eventos": int(c["_eventos_med"] or 1)})
    for g in generales:
        for clave, v in list(g.evidencia.get("detalle", {}).items())[:3]:
            cuenta = clave.split(" · ")[0]
            accion = clave.split(" · ")[1] if " · " in clave else "personas distintas"
            nid = f"cta-{cuenta}"
            if nid not in vistos:
                nodos.append({"id": nid, "tipo": "cuenta", "etiqueta": cuenta,
                              "detalle": pr.TITULO[pr.tipo(g)], "casoId": None, "gravedad": "media",
                              "personas": int(personas.get(cuenta, 1))})
                vistos.add(nid)
            aristas.append({"origen": nid, "destino": "srv", "etiqueta": limpiar(accion.lower()), "eventos": int(v)})
    return {"nodos": nodos, "aristas": aristas}


# ---------- inteligencia ----------
def _sigma(id_, titulo, nivel, tecnica, casos, logsource, deteccion, desc) -> dict:
    return {"id": id_, "titulo": titulo, "nivel": nivel, "tecnica": tecnica, "casos": casos, "yaml":
            f"title: {titulo}\nid: {uuid.uuid5(NS, 'sigma' + id_)}\nstatus: experimental\ndescription: {desc}\n"
            f"author: ESPEThreat\ndate: 2026-11-26\ntags:\n  - attack.{tecnica.lower()}\nlogsource:\n{logsource}\n"
            f"detection:\n{deteccion}\nfalsepositives:\n  - Tareas de administración autorizadas\nlevel: {nivel}"}


def inteligencia(casos: list[dict], generado: str) -> dict:
    c = config
    de = lambda *tipos: [x["id"] for x in casos if x["_tipo"] in tipos]  # noqa: E731
    fwlog = "  product: firewall"
    medlog = "  product: sistema_medico\n  service: auditoria"
    sigma = [
        _sigma("01", "Fuerza bruta hacia el servidor médico", "high", "T1110", de("fuerza_bruta"), fwlog,
               f"  selection:\n    dst_ip: '{c.SERVIDOR}'\n    action: negado\n  timeframe: {c.RAFAGA_IP_SEG // 60}m\n"
               f"  condition: selection | count() by src_ip >= {c.RAFAGA_IP_MIN}",
               "Muchos intentos negados desde una IP contra el servidor médico."),
        _sigma("02", "Escaneo de servicios del servidor médico", "high", "T1046", de("escaneo"), fwlog,
               f"  selection:\n    dst_ip: '{c.SERVIDOR}'\n  timeframe: {c.RAFAGA_IP_SEG // 60}m\n"
               f"  condition: selection | count(dst_port) by src_ip >= {c.ESCANEO_PUERTOS_MIN}",
               "Una IP prueba varios puertos del servidor en pocos minutos."),
        _sigma("03", "Ráfaga SSH permitida hacia el servidor médico", "critical", "T1021.004",
               de("rafaga_ssh", "extraccion_masiva"), fwlog,
               f"  selection:\n    dst_ip: '{c.SERVIDOR}'\n    dst_port: 22\n    action: permitido\n"
               f"  timeframe: {c.RAFAGA_SSH_SEG}s\n  condition: selection | count() by src_ip >= {c.RAFAGA_SSH_MIN}",
               "Muchas sesiones SSH en segundos: posible extracción de datos."),
        _sigma("04", "Accesos fallidos masivos en el sistema médico", "high", "T1110",
               de("fuerza_bruta", "escaneo", "fallidos_masivos"), medlog,
               f"  selection:\n    accion|contains: 'FALLIDO'\n  timeframe: 24h\n"
               f"  condition: selection | count() by cuenta >= {c.FALLIDOS_MIN}",
               "Una cuenta acumula accesos fallidos muy por encima de lo normal."),
        _sigma("05", "Cuenta de un solo uso con descarga", "critical", "T1078", de("cuenta_rara"), medlog,
               "  descarga:\n    accion|contains:\n      - 'DESCARGA'\n      - 'TRANSFER'\n  timeframe: 30d\n"
               f"  condition: descarga | count() by cuenta <= {c.CUENTA_RARA_MAX}",
               "Cuenta casi sin actividad en el mes que de pronto descarga datos. Confirmar con el conteo total."),
    ]
    iocs = []
    for x in casos:
        conf = 90 if "Cruce de datasets" in x["detectadoPor"] else 75
        if x["ipOrigen"]:
            iocs.append({"tipo": "ipv4-addr", "valor": x["ipOrigen"], "descripcion": f"Origen: {x['tipo'].lower()}",
                         "casoId": x["id"], "confianza": conf})
        if x["cuenta"]:
            iocs.append({"tipo": "user-account", "valor": x["cuenta"], "descripcion": f"Cuenta del caso: {x['titulo'].lower()}",
                         "casoId": x["id"], "confianza": conf - 10})
    f = pd.Timestamp(generado).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    sid = lambda tipo, k: f"{tipo}--{uuid.uuid5(NS, tipo + k)}"  # noqa: E731
    ident = sid("identity", "espethreat")
    base = {"spec_version": "2.1", "created": f, "modified": f, "created_by_ref": ident}
    objs = [{"type": "identity", "id": ident, "name": "Equipo ESPEThreat", "identity_class": "organization",
             "spec_version": "2.1", "created": f, "modified": f}]
    tecs = set()
    for x in casos:
        if not x["ipOrigen"]:
            continue
        ind = sid("indicator", x["ipOrigen"])
        objs.append({"type": "indicator", "id": ind, "name": f"{x['id']}: {x['titulo']}",
                     "pattern": f"[ipv4-addr:value = '{x['ipOrigen']}']", "pattern_type": "stix",
                     "valid_from": x["inicio"] + "Z", "labels": ["malicious-activity", "sintetico"], **base})
        for t in x["tecnicas"]:
            if t["id"] not in tecs:
                tecs.add(t["id"])
                objs.append({"type": "attack-pattern", "id": sid("attack-pattern", t["id"]), "name": t["nombre"],
                             "external_references": [{"source_name": "mitre-attack", "external_id": t["id"]}], **base})
            objs.append({"type": "relationship", "id": sid("relationship", ind + t["id"]),
                         "relationship_type": "indicates", "source_ref": ind,
                         "target_ref": sid("attack-pattern", t["id"]), **base})
    stix = {"type": "bundle", "id": sid("bundle", "sentinel-salud"), "objects": objs}
    misp = {"Event": {"info": "Sentinel Salud · amenazas al sistema médico · datos sintéticos", "threat_level_id": "1",
                      "analysis": "1", "distribution": "0",
                      "Tag": [{"name": f"misp-galaxy:mitre-attack-pattern={t}"} for t in sorted(tecs)],
                      "Attribute": [{"type": "ip-src" if i["tipo"] == "ipv4-addr" else "target-user",
                                     "category": "Network activity" if i["tipo"] == "ipv4-addr" else "Targeting data",
                                     "value": i["valor"], "comment": f"{i['casoId']}: {i['descripcion']}",
                                     "to_ids": i["tipo"] == "ipv4-addr"} for i in iocs]}}
    return {"sigma": sigma, "iocs": iocs, "stix": json.dumps(stix, ensure_ascii=False, indent=2),
            "misp": json.dumps(misp, ensure_ascii=False, indent=2)}


# ---------- resumen ----------
def resumen(rm_motor: dict, fw, med, casos, serie_h, base, personas, generales, an_med, alertas) -> dict:
    pico = max(serie_h, key=lambda p: p["fallidos"]) if serie_h else None
    ssh = fw[fw["srv"] & fw["ssh"] & ~fw["neg"]]
    ssh_seg = ssh.groupby(["iph", "s"]).size()
    s_pico = int(ssh_seg.idxmax()[1]) if len(ssh_seg) else 0
    p_max = personas.idxmax() if len(personas) else ""
    inseguros = next((g for g in generales if g.regla == "servicios_inseguros"), None)
    admin = next((g for g in generales if g.regla == "administracion_concentrada"), None)
    desfase = max([abs(a["desfase_reloj_h"]) for a in alertas] or [0])
    ind = []
    if pico:
        ind.append(_med("Accesos fallidos por hora (pico)", pico["fallidos"], 0, base["fallidos_hora"], "/h",
                        pd.Timestamp(pico["ts"]).strftime("%d/%m %H:%M")))
    if len(ssh_seg):
        ind.append(_med("Conexiones SSH permitidas por segundo (pico)", ssh_seg.max(), 0, base["ssh_seg"], "/s",
                        fecha(s_pico).strftime("%d/%m %H:%M")))
    ind.append(_med("Personas distintas por cuenta (máx.)", personas.max(), 1, base["personas_max"], "personas",
                    f"Cuenta {p_max}"))
    if inseguros:
        ind.append(_med("Conexiones Telnet, SMBv1 y NetBIOS permitidas", inseguros.evidencia["permitidas_total"], 0, 0,
                        "en el periodo", "Protocolos sin cifrado"))
    ind.append(_med("Desfase de reloj entre fuentes", desfase, 0, 0.1, "h", "Firewall frente al sistema médico"))
    if admin and admin.evidencia.get("detalle"):
        clave, v = next(iter(admin.evidencia["detalle"].items()))
        ind.append(_med("Acción administrativa más concentrada", v, 0,
                        admin.evidencia["mediana_por_cuenta"] * config.ADMIN_VECES_MEDIANA, "en el periodo",
                        limpiar(clave)))
    def ids(pilar):
        return [c["id"] for c, a in casos if pilar in a["cid"]]
    pil = [
        {"pilar": "Confidencialidad", "riesgo": "Historias clínicas vistas o extraídas sin permiso",
         "evidencia": "; ".join(f"{c['id']} {c['titulo'].lower()}" for c, a in casos if "Confidencialidad" in a["cid"])
         or "Sin casos", "casos": ids("Confidencialidad")},
        {"pilar": "Integridad", "riesgo": "Permisos, usuarios o registros alterados",
         "evidencia": (f"{admin.evidencia['cuentas']} cuentas con acciones administrativas concentradas" if admin else
                       "Sin hallazgos de administración") + (f"; relojes desfasados {desfase:g} h" if desfase else ""),
         "casos": ids("Integridad")},
        {"pilar": "Disponibilidad", "riesgo": "Sistema médico detenido",
         "evidencia": (f"{inseguros.evidencia['permitidas_total']:,} conexiones sin cifrado permitidas".replace(",", ".")
                       if inseguros else "Sin servicios inseguros") + "; la fuerza bruta puede bloquear cuentas",
         "casos": ids("Disponibilidad")},
    ]
    d = pd.Timestamp(rm_motor["periodo"]["desde"])
    return {
        "periodo": f"{MESES[d.month - 1]} {d.year}", "registrosAnalizados": rm_motor["registros"]["total"],
        "registrosFirewall": rm_motor["registros"]["firewall"],
        "registrosSistemaMedico": rm_motor["registros"]["sistema_medico"],
        "minutosProcesamiento": rm_motor["tiempo_analisis_min"], "usuariosFirewall": int(fw["u"].nunique()),
        "cuentasSistemaMedico": int(med["cuenta"].nunique()),
        "cuentasSospechosas": sum(1 for f in an_med["filas"] if f["sospechosa"]),
        "controlesConBrecha": 0, "indicadores": ind, "pilares": pil,
    }


# ---------- todo ----------
def generar(carpeta: Path, pares: list, fw: pd.DataFrame, med: pd.DataFrame, rf, rm, seud, filas_fw: pd.DataFrame,
            generales: list, rm_motor: dict) -> None:
    salida = carpeta / "consola"
    salida.mkdir(parents=True, exist_ok=True)
    con_caso = sorted([(h, a) for h, a in pares if a.get("caso")], key=lambda p: int(p[1]["caso"].split()[1]))
    ips_casos = {h.iph for h, _ in con_caso if h.iph is not None}
    fuera = {a["cuenta"] for _, a in con_caso if a["cuenta"]}
    for g in generales:
        fuera |= {k.split(" · ")[0] for k in g.evidencia.get("detalle", {})}
    base, eventos_cuenta, personas = lineas_base(fw, med, ips_casos, fuera)
    total_fw = rf.entidades if rf is not None else int(fw["u"].nunique())
    casos = [(caso(h, a, filas_fw, med, base, eventos_cuenta, personas, seud, total_fw), a) for h, a in con_caso]
    serie_h = serie(fw, med, rf)
    st_fw = pd.DataFrame({"eventos": fw.groupby("u", observed=True).size(),
                          "fallidos": fw.groupby("u", observed=True)["neg"].sum(),
                          "diversidad": fw.groupby("u", observed=True)["iph"].nunique()})
    st_fw.index = st_fw.index.astype(str)
    fall = _acciones(med, config.PATRON_FALLIDO)
    st_med = pd.DataFrame({"eventos": eventos_cuenta, "fallidos": fall.groupby(med["cuenta"], observed=True).sum(),
                           "diversidad": personas})
    st_med.index = st_med.index.astype(str)
    por_usuario = {c["_usuario_fw"]: c["id"] for c, _ in casos if c["_usuario_fw"]}
    ip_usuario = {c["_usuario_fw"]: c["ipOrigen"] for c, _ in casos if c["_usuario_fw"]}
    por_cuenta = {c["cuenta"]: c["id"] for c, _ in casos if c["cuenta"]}
    an_fw = anomalias(rf, "u", st_fw, "firewall", por_usuario, seud, ip_usuario)
    # persona más frecuente de cada cuenta listada, para mostrar su seudónimo
    listadas = set(rm.tabla.sort_values("puntaje", ascending=False).drop_duplicates("cuenta").head(100)["cuenta"]
                   .astype(str)) | set(por_cuenta) if rm is not None else set()
    x = med[med["cuenta"].isin(listadas)]
    persona_de = (x.groupby("cuenta", observed=True)["persona"].agg(lambda p: str(p.value_counts().index[0]))
                  .to_dict() if len(x) else {})
    an_med = anomalias(rm, "cuenta", st_med, "sistema_medico", por_cuenta, seud,
                       {str(k): v for k, v in persona_de.items()})
    alertas = [a for _, a in pares]
    datos = {
        "resumen.json": resumen(rm_motor, fw, med, casos, serie_h, base, personas, generales, an_med, alertas),
        "casos.json": [{k: v for k, v in c.items() if not k.startswith("_")} for c, _ in casos],
        "serie.json": serie_h, "anomalias_firewall.json": an_fw, "anomalias_sistema_medico.json": an_med,
        "grafo.json": grafo([c for c, _ in casos], [g for g in generales if g.evidencia.get("detalle")], personas),
        "inteligencia.json": inteligencia([c for c, _ in casos], rm_motor["generado"]),
        "lineas_base.json": base,
    }
    def conv(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        return str(o)
    for nombre, obj in datos.items():
        (salida / nombre).write_text(limpiar(json.dumps(obj, ensure_ascii=False, indent=2, default=conv)),
                                     encoding="utf-8")
