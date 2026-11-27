"""Sentinel Salud · motor de detección y análisis.

Uso:
  python -m motor                                   usa datos/ y escribe en salidas/
  python -m motor --fw ruta.csv --med ruta.csv --salidas carpeta [--sin-ml]

Capas: reglas sobre cada fuente -> correlación firewall + sistema médico -> modelo Isolation Forest por ventanas
-> priorización (probabilidad x impacto) -> seudónimos -> salidas/*.json para la API.
"""
from __future__ import annotations

import argparse
import json
import re
import datetime as dt
import time
from pathlib import Path

from . import agendamiento, config, consola, correlacion, ingesta, ml, reglas_fw, reglas_med, salida
from .hallazgo import Hallazgo


def _log(msg: str) -> None:
    print(msg, flush=True)


def _ml_en_hallazgos(hs, fw, med, rf, rm) -> None:
    s_por_fila = fw.set_index("fila")["s"] if rf is not None else None
    for h in hs:
        if rf is not None and h.usuarios and h.filas_fw:
            h.ml["fw"] = ml.puesto(rf, "u", h.usuarios[0], int(s_por_fila.loc[h.filas_fw[0]]), 3600)
        if rm is not None and h.cuenta and h.idx_med:
            h.ml["med"] = ml.puesto(rm, "cuenta", h.cuenta, int(med.loc[h.idx_med[0], "s"]), 86400)
        h.ml = {k: v for k, v in h.ml.items() if v}


def _ml_solas(rf, rm, hs) -> list[Hallazgo]:
    """Ventanas muy anómalas que ninguna regla explica: se reportan como alertas de revisión."""
    vistas_fw = {(h.ml.get("fw", {}).get("puesto")) for h in hs}
    vistas_med = {(h.ml.get("med", {}).get("puesto")) for h in hs}
    nuevas = []
    for r, col, vistas, fuente, paso in ((rf, "u", vistas_fw, "firewall", 3600),
                                         (rm, "cuenta", vistas_med, "sistema_medico", 86400)):
        if r is None:
            continue
        top = r.tabla[(r.tabla["puntaje"] >= config.ML_ALERTA_PUNTAJE) & ~r.tabla["puesto"].isin(vistas)]
        for _, x in top.sort_values("puesto").head(config.ML_ALERTAS_MAX).iterrows():
            h = Hallazgo(regla=f"ml_{fuente}", fuente=fuente, inicio=int(x["ventana"]), fin=int(x["ventana"]) + paso - 1,
                         evidencia={"por_que": x["por_que"]}, general=False)
            h.solo_ml = True
            if fuente == "firewall":
                h.usuarios = [str(x[col])]
                h.ml["fw"] = {"puesto": int(x["puesto"]), "de": r.total, "puntaje": float(x["puntaje"]),
                              "por_que": x["por_que"]}
            else:
                h.cuenta = str(x[col])
                h.ml["med"] = {"puesto": int(x["puesto"]), "de": r.total, "puntaje": float(x["puntaje"]),
                               "por_que": x["por_que"]}
            nuevas.append(h)
    return nuevas


def _ml_json(rf, rm, seud, sospechosas: int) -> dict:
    def top(r, col, paso, fmt, prefijo):
        if r is None:
            return []
        x = r.tabla.sort_values("puesto").head(config.ML_TOP)
        filas = []
        for _, f in x.iterrows():
            ent = seud(str(f[col]), prefijo) if prefijo else str(f[col])
            filas.append({"puesto": int(f["puesto"]), ("usuario" if prefijo else "cuenta"): ent,
                          "ventana": ingesta.fecha(int(f["ventana"])).strftime(fmt), "puntaje": float(f["puntaje"]),
                          "explicacion": f["por_que"]})
        return filas
    return {
        "modelo": "Isolation Forest", "random_state": config.SEMILLA,
        "usuarios_firewall": top(rf, "u", 3600, "%Y-%m-%d %H:00", "U"),
        "total_usuarios_firewall": rf.entidades if rf else 0, "total_ventanas_firewall": rf.total if rf else 0,
        "cuentas_sistema_medico": top(rm, "cuenta", 86400, "%Y-%m-%d", ""),
        "total_cuentas": rm.entidades if rm else 0, "total_ventanas_sistema_medico": rm.total if rm else 0,
        "cuentas_sospechosas": sospechosas,
    }


def _nombre(ruta) -> str:
    """Nombre del archivo sin el nombre de la institución que traen los datasets del reto."""
    return re.sub(r"(?i)iess", "inst", Path(ruta).name)


def _evento(paso: str, estado: str, **datos) -> None:
    """Línea de progreso para la consola web: el backend la lee y anima cada paso con estos números."""
    print("@@" + json.dumps({"paso": paso, "estado": estado, **datos}, ensure_ascii=False, default=str), flush=True)


def _avance(fuente: str):
    def f(msg: str) -> None:
        _log(msg)
        m = re.search(r"\(([\d,\.]+) filas\)", msg)
        if m:
            _evento("validacion", "en_curso", fuente=fuente, filas=int(re.sub(r"[^\d]", "", m.group(1))))
    return f


def ejecutar(ruta_fw: Path, ruta_med: Path, carpeta: Path, con_ml: bool = True, tam: int = config.TAM_PARTE,
             restringido: Path = config.RESTRINGIDO, ruta_citas: Path | None = None,
             ruta_redes: Path | None = config.REDES, reportados_contacto: set | None = None) -> dict:
    t0 = time.time()
    _log("1/7 Leyendo y validando datos")
    _evento("validacion", "en_curso")
    lfw = ingesta.leer_fw(ruta_fw, tam, _avance("firewall"))
    lmed = ingesta.leer_med(ruta_med, tam, _avance("sistema_medico"))
    fw, med = lfw.datos, lmed.datos
    _evento("validacion", "listo", filas_firewall=lfw.filas, filas_sistema_medico=lmed.filas,
            filas_descartadas=lfw.invalidas + lmed.invalidas, columnas_faltantes=lfw.faltantes + lmed.faltantes,
            codificacion_sistema_medico=ingesta.codificacion(ruta_med))
    _evento("normalizacion", "listo", fechas_unificadas=len(fw) + len(med), usuarios_firewall=int(fw["u"].nunique()),
            cuentas_sistema_medico=int(med["cuenta"].nunique()), ips_mal_escritas=int(med["ipmal"].sum()),
            acciones_distintas=int(med["accion"].nunique()))

    _log("2/7 Reglas de detección")
    _evento("reglas", "en_curso")
    a_fw, g_fw, seg = reglas_fw.detectar(fw)
    a_med, g_med, _ = reglas_med.detectar(med)
    _log(f"  firewall: {len(a_fw)} ráfagas · sistema médico: {len(a_med)} hallazgos")
    _evento("reglas", "listo", rafagas_firewall=len(a_fw), hallazgos_sistema_medico=len(a_med),
            debilidades_configuracion=len(g_fw) + len(g_med))

    _log("3/7 Cruce firewall + sistema médico")
    _evento("cruce", "en_curso")
    juntos, solo_fw, solo_med = correlacion.cruzar(a_fw, a_med)
    usuarios = [str(u) for u in fw["u"].cat.categories]
    resto_med = []
    for m in solo_med:
        h = correlacion.buscar_en_firewall(m, fw, usuarios)
        (juntos if h else resto_med).append(h or m)
    hallazgos = juntos + solo_fw + resto_med
    _log(f"  correlacionados: {len(juntos)}")
    _evento("cruce", "listo", ataques_confirmados_en_ambas_fuentes=len(juntos),
            relojes_corregidos=sum(1 for h in juntos if h.desfase_h))

    rf = rm = None
    if con_ml:
        _log("4/7 Machine learning por ventanas")
        _evento("modelo", "en_curso")
        rf, rm = ml.firewall(fw), ml.sistema_medico(med)
        _ml_en_hallazgos(hallazgos, fw, med, rf, rm)
        hallazgos += _ml_solas(rf, rm, hallazgos)
        _evento("modelo", "listo", ventanas_firewall=rf.total, ventanas_sistema_medico=rm.total,
                usuarios=rf.entidades, cuentas=rm.entidades)
    else:
        _log("4/7 Machine learning omitido (--sin-ml)")
        _evento("modelo", "omitido")

    _log("5/7 Recuperando evidencia del firewall")
    filas = ingesta.filas_fw(ruta_fw, {f for h in hallazgos for f in h.filas_fw}, tam)
    ip_de = dict(zip(filas["fila"], filas["IP_Origen"]))
    for h in hallazgos:
        if h.filas_fw:
            h.ip = ip_de.get(h.filas_fw[0], "")

    agenda = None
    if ruta_citas:
        _log("6/7 Agendamiento médico (HBVF)")
        _evento("agendamiento", "en_curso")
        agenda = agendamiento.analizar(ruta_citas, ruta_redes, reportados_contacto, origen=Path(ruta_citas).name)
        _evento("agendamiento", "listo", sesiones=agenda["resumen"]["sesiones"], puntos=agenda["resumen"]["puntos"],
                revision_requerida=agenda["resumen"]["revision_requerida"])
    else:
        _evento("agendamiento", "omitido")

    _log("7/7 Priorizando, protegiendo datos y escribiendo salidas")
    _evento("priorizacion", "en_curso")
    seud = salida.Seudonimos(restringido)
    todos = hallazgos + g_fw + g_med
    alertas = [salida.alerta(h, seud, filas, med) for h in todos]
    pares = list(zip(todos, alertas))
    alertas = salida.numerar(alertas)
    cuentas = {a["cuenta"] for a in alertas if a["cuenta"] and not any(h.general and h.cuenta == a["cuenta"]
                                                                       for h in g_med)}
    for g in g_med:
        cuentas |= {k.split(" · ")[0] for k in g.evidencia.get("detalle", {})}
    s_min = int(min(fw["s"].min(), med["s"].min()))
    s_max = int(max(fw["s"].max(), med["s"].max()))
    hipaa = {a["salvaguarda_hipaa"] for a in alertas if a["salvaguarda_hipaa"]}
    if any(a["desfase_reloj_h"] for a in alertas) or int(med["ipmal"].sum()):
        hipaa.add("Controles de auditoría")
    resumen = {
        "periodo": {"desde": ingesta.fecha(s_min).strftime("%Y-%m-%d"), "hasta": ingesta.fecha(s_max).strftime("%Y-%m-%d")},
        "generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "registros": {"firewall": lfw.filas, "sistema_medico": lmed.filas, "total": lfw.filas + lmed.filas},
        "tiempo_analisis_min": round((time.time() - t0) / 60, 1),
        "cuentas_sospechosas": len(cuentas),
        "conexiones_inseguras": next((g.evidencia["permitidas_total"] for g in g_fw
                                      if g.regla == "servicios_inseguros"), 0),
        "brechas_hipaa": len(hipaa),
        "calidad": {"filas_fecha_invalida": lfw.invalidas + lmed.invalidas,
                    "ip_mal_escrita_sistema_medico": int(med["ipmal"].sum()),
                    "columnas_faltantes": lfw.faltantes + lmed.faltantes},
        "segmento_servidor": seg,
        "archivos": {"firewall": _nombre(ruta_fw), "sistema_medico": _nombre(ruta_med),
                     "agendamiento": _nombre(ruta_citas) if ruta_citas else None},
    }
    grav = {g: sum(1 for a in alertas if a["gravedad"] == g) for g in ("Crítica", "Alta", "Media", "Baja")}
    _evento("priorizacion", "listo", alertas=len(alertas), **{k.lower().replace("í", "i"): v for k, v in grav.items()})
    _evento("proteccion", "en_curso")
    salida.escribir(carpeta, alertas, resumen, _ml_json(rf, rm, seud, len(cuentas)))
    if agenda:
        (carpeta / "agendamiento.json").write_text(json.dumps(agenda, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        consola.generar(carpeta, pares, fw, med, rf, rm, seud, filas, g_fw + g_med, resumen)
    except Exception as e:  # la consola web es un extra: si falla, las salidas principales ya quedaron escritas
        _log(f"  aviso: no se pudo generar salidas/consola ({e})")
        if config.ESTRICTO:
            raise
    seud.guardar()
    _evento("proteccion", "listo", seudonimos_generados=len(seud.tabla), personas_firewall=int(fw["u"].nunique()),
            personas_sistema_medico=int(med["persona"].nunique()))
    resumen["tiempo_analisis_min"] = round((time.time() - t0) / 60, 1)
    (carpeta / "resumen_motor.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"Listo en {resumen['tiempo_analisis_min']} min · {len(alertas)} alertas en {carpeta}")
    for a in alertas:
        _log(f"  {a['gravedad']:8} {a['puntaje']:>2}  {a['caso'] or '':7} {a['inicio']}  {a['titulo']}"
             f"  {a['ip_origen']} {a['cuenta']}")
    _evento("listo", "listo", minutos=resumen["tiempo_analisis_min"], alertas=len(alertas))
    return {"alertas": alertas, "resumen": resumen, "agendamiento": agenda}


def main() -> None:
    ap = argparse.ArgumentParser(description="Sentinel Salud · motor de detección y análisis")
    ap.add_argument("--fw", type=Path, default=config.ARCHIVO_FW)
    ap.add_argument("--med", type=Path, default=config.ARCHIVO_MED)
    ap.add_argument("--salidas", type=Path, default=config.SALIDAS)
    ap.add_argument("--restringido", type=Path, default=config.RESTRINGIDO)
    ap.add_argument("--citas", type=Path, help="registros del chatbot de citas para el módulo HBVF (opcional)")
    ap.add_argument("--redes", type=Path, default=config.REDES, help="tabla de redes y ASN (CSV)")
    ap.add_argument("--reportes", type=Path, help="contactos seudonimizados reportados en denuncias (HG-07), uno por línea")
    ap.add_argument("--sin-ml", action="store_true")
    a = ap.parse_args()
    for r in (a.fw, a.med):
        if not r.exists():
            raise SystemExit(f"No existe {r}. Copia los CSV del reto en la carpeta datos/.")
    if a.citas and not a.citas.exists():
        raise SystemExit(f"No existe {a.citas}.")
    reportes = None
    if a.reportes and a.reportes.exists():
        reportes = {x.strip() for x in a.reportes.read_text(encoding="utf-8").splitlines() if x.strip()}
    ejecutar(a.fw, a.med, a.salidas, con_ml=not a.sin_ml, restringido=a.restringido, ruta_citas=a.citas,
             ruta_redes=a.redes, reportados_contacto=reportes)


if __name__ == "__main__":
    main()
