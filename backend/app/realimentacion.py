"""Realimentación (S9/T18): las decisiones del analista y los falsos positivos afinan reglas y modelo.

Métricas (GET /api/realimentacion), documentadas aquí y en la pantalla Realimentacion.tsx:

  precisión = confirmadas / (confirmadas + descartadas)
      Sobre las decisiones registradas en almacen: decisiones de caso (POST /api/casos/{id}/decision)
      y ciclo de vida de alertas (tabla decisiones). Mide: de todo lo que la consola encendió y el
      analista revisó, qué fracción era real. Sin decisiones no es calculable (valor null) y se dice
      en la explicación en vez de inventar un número.

  recall (exhaustividad) = casos de referencia confirmados / casos de referencia decididos
      Los casos de referencia son las alertas etiquetadas con `caso` (los casos del informe): el único
      ground truth disponible. Ojo, honestidad: esos casos los generó el propio sistema, así que este
      número mide qué mantuvo el analista al revisarlos, no cuánto detectó el modelo — sobre "todos
      los ataques reales" no hay registro y no se calcula. Sin decisiones sobre casos de referencia
      el valor es null.

  F1 = 2·precisión·recall / (precisión + recall) — solo si existen precisión y recall; si falta
      alguno, null con la razón.

Recalibración (POST /api/realimentacion/recalibrar): solo bajo invocación explícita de un rol con
permiso `tecnico`; nunca en cada request ni en silencio. Cada falso positivo descartado (alerta del
ciclo de vida o caso descartado por el analista) se traduce en un paso del 10 % (mínimo 1 unidad)
sobre el umbral de su regla en rules/*.yml: subirlo, o bajarlo cuando el umbral es un máximo
(p. ej. CUENTA_RARA_MAX). Los ajustes se reescriben línea por línea para conservar los comentarios
del YAML. Idempotente: los falsos positivos ya aplicados (según la bitácora) no se vuelven a
aplicar, y sin falsos positivos no cambia ningún archivo. Quién, por qué y qué cambió queda SIEMPRE
en la bitácora; un falso positivo sin umbral numérico (p. ej. servicios sin cifrar) se reporta en
`sinUmbral` en vez de forzar un número.

Reentrenamiento: cuando se aplica un cambio de umbrales, las ventanas del análisis activo se
acumulan en estado/historico/*.csv (solo-agregar, sin duplicar) y el Isolation Forest se reentrena
con todo el histórico y la semilla de rules/ml.yml (motor.ml.reentrenar). Nada corre automático:
solo en esta invocación explícita.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from . import almacen, analisis, config, datos, estado

ACCION = "Recalibración de umbrales"
PASO = 0.10                       # 10 % del umbral por falso positivo, mínimo 1 unidad
FUENTES = ("firewall", "sistema_medico")

# tipo de hallazgo → (archivo de rules/, clave numérica, dirección del ajuste ante un falso positivo)
UMBRAL_POR_TIPO = {
    "fuerza_bruta": ("firewall.yml", "FUERZA_BRUTA_PCT_NEGADO", "subir"),
    "escaneo": ("firewall.yml", "ESCANEO_PUERTOS_MIN", "subir"),
    "rafaga_ssh": ("firewall.yml", "RAFAGA_SSH_MIN", "subir"),
    "rafaga_conexiones": ("firewall.yml", "RAFAGA_IP_MIN", "subir"),
    "fallidos_masivos": ("sistema_medico.yml", "FALLIDOS_MIN", "subir"),
    "extraccion_masiva": ("sistema_medico.yml", "MASIVO_MIN", "subir"),
    "cuenta_rara": ("sistema_medico.yml", "CUENTA_RARA_MAX", "bajar"),
    "cuentas_compartidas": ("sistema_medico.yml", "NOMBRES_CUENTA_COMPARTIDA", "subir"),
    "administracion_concentrada": ("sistema_medico.yml", "ADMIN_VECES_MEDIANA", "subir"),
    "ml": ("ml.yml", "ML_ALERTA_PUNTAJE", "subir"),
    # servicios_inseguros no está: su regla es una lista de puertos, no un número ajustable.
}


def _alertas_json() -> list[dict]:
    """alertas.json del análisis activo (vacío si no hay análisis): casos etiquetados con `caso`."""
    return datos.motor("alertas.json", []) if analisis.activo_id() else []


def clave_caso(valor) -> str | None:
    """'Caso 1' (numeración del motor) y 'C1' (consola) son el mismo caso: normaliza a C1."""
    v = str(valor or "").strip()
    if not v:
        return None
    m = re.fullmatch(r"(?:caso\s*|c\s*)(\d+)", v, re.IGNORECASE)
    return f"C{int(m.group(1))}" if m else v


def _tipos_de(fp: dict, alertas_json: list[dict]) -> tuple[list[str], str | None]:
    """Tipo(s) de regla que produjeron el falso positivo: por el caso en alertas.json si existe,
    si no por el título contra el catálogo del motor. Nunca adivina fuera del catálogo."""
    k = clave_caso(fp.get("caso"))
    if k:
        reglas = [str(a.get("regla") or "") for a in alertas_json if clave_caso(a.get("caso")) == k]
        tipos = [_tipo_de_regla(r) for r in reglas if r]
        if tipos:
            return tipos, None
    titulo = fp.get("titulo")
    if titulo:
        from motor import priorizacion
        tipo = {t: n for n, t in priorizacion.TITULO.items()}.get(titulo)
        if tipo:
            return [tipo], None
        return [], f"el título «{titulo}» no está en el catálogo del motor: sin umbral que ajustar"
    return [], "sin alertas del análisis que relacionen este caso con una regla: sin umbral que ajustar"


def _tipo_de_regla(regla: str) -> str:
    from motor import priorizacion
    return priorizacion.tipo(regla)


# ---------- métricas ----------

def _conteo_decisiones(db) -> tuple[int, int]:
    """Decisiones del analista en las dos vías de almacen: decisiones de caso y ciclo de vida."""
    conf = desc = 0
    for d in almacen.leer_registros(db, "decisiones"):
        e = str(d.get("estado") or "").lower()
        if e in ("confirmado", "confirmada"):
            conf += 1
        elif e in ("descartado", "descartada"):
            desc += 1
    for fila in db.execute("SELECT estado_nuevo FROM decisiones"):
        if fila[0] == "confirmada":
            conf += 1
        elif fila[0] == "descartada":
            desc += 1
    return conf, desc


def _casos_conocidos(db, alertas_json: list[dict]) -> list[dict]:
    """Casos de referencia (etiqueta `caso`) con su estado de decisión vigente."""
    casos: dict[str, dict] = {}
    for a in alertas_json:
        k = clave_caso(a.get("caso"))
        if k:
            casos[k] = {"caso": k, "titulo": str(a.get("titulo") or ""), "estado": "pendiente"}
    for a in almacen.listar_alertas(db):
        k = clave_caso(a.get("caso_id"))
        if k and k not in casos:
            casos[k] = {"caso": k, "titulo": a["titulo"], "estado": "pendiente"}
    for d in almacen.leer_registros(db, "decisiones"):          # la decisión de caso manda
        k = clave_caso(d.get("casoId"))
        e = str(d.get("estado") or "").lower()
        if k in casos and e in ("confirmado", "confirmada", "descartado", "descartada"):
            casos[k]["estado"] = "confirmada" if e.startswith("confirm") else "descartada"
    for a in almacen.listar_alertas(db):                        # y el ciclo de vida completa
        k = clave_caso(a.get("caso_id"))
        if k in casos and casos[k]["estado"] == "pendiente":
            if a["estado"] in ("confirmada", "contenida"):
                casos[k]["estado"] = "confirmada"
            elif a["estado"] == "descartada":
                casos[k]["estado"] = "descartada"
    return list(casos.values())


def metricas(db, alertas_json: list[dict]) -> dict:
    """Precisión, recall y F1 con lo que de verdad hay: decisiones en almacen y casos etiquetados.

    Las fórmulas están en el docstring del módulo y en la pantalla; lo que no es calculable sale
    como `valor: None` con su explicación, nunca como un número inventado.
    """
    conf, desc = _conteo_decisiones(db)
    total = conf + desc
    precision = {
        "formula": "confirmadas / (confirmadas + descartadas)",
        "confirmadas": conf, "descartadas": desc,
        "valor": conf / total if total else None,
        "explicacion": (f"{conf} confirmadas de {total} decisiones revisadas: de todo lo que la "
                        "consola encendió y el analista revisó, esta fracción era real."
                        if total else "Aún no hay decisiones de analista: la precisión no es calculable."),
    }
    conocidos = _casos_conocidos(db, alertas_json)
    decididos = [c for c in conocidos if c["estado"] != "pendiente"]
    confirmados = [c for c in conocidos if c["estado"] == "confirmada"]
    recall = {
        "formula": "casos de referencia confirmados / casos de referencia decididos",
        "casosConocidos": len(conocidos), "decididos": len(decididos), "confirmados": len(confirmados),
        "valor": len(confirmados) / len(decididos) if decididos else None,
        "explicacion": (
            f"{len(confirmados)} de {len(decididos)} casos de referencia decididos quedaron confirmados "
            "(sobre los casos etiquetados con `caso`, el único ground truth disponible: miden qué "
            "mantuvo el analista, no cuánto detectó el modelo)."
            if decididos else
            "Los casos de referencia aún no tienen decisiones: el recall no es calculable y no se "
            "inventa un número."),
    }
    if precision["valor"] is not None and recall["valor"] is not None:
        p, r = precision["valor"], recall["valor"]
        valor = 2 * p * r / (p + r) if (p + r) else 0.0
        nota_f1 = "F1 combina precisión y recall en un solo número."
    else:
        valor, nota_f1 = None, "F1 necesita precisión y recall a la vez; falta uno de los dos."
    f1 = {"formula": "2·precisión·recall / (precisión + recall)", "valor": valor, "explicacion": nota_f1}
    return {"precision": precision, "recall": recall, "f1": f1, "casosConocidos": conocidos}


def _historico() -> dict[str, int]:
    """Ventanas acumuladas por fuente en estado/historico/ (0 si aún no hay histórico)."""
    out = {}
    for fuente in FUENTES:
        ruta = _ruta_historico(fuente)
        if ruta.exists():
            with ruta.open(encoding="utf-8") as f:
                out[fuente] = max(sum(1 for _ in f) - 1, 0)
        else:
            out[fuente] = 0
    return out


def _recalibraciones(db) -> list[dict]:
    """Historial desde la bitácora (append-only): quién recalibró, por qué y qué cambió."""
    out = []
    for e in reversed(almacen.leer_bitacora(db)):
        if e["accion"] != ACCION:
            continue
        try:
            d = json.loads(e["detalle"])
        except (ValueError, TypeError):
            d = {"motivo": str(e["detalle"])}
        out.append({"fecha": e["fecha"], "actor": e["actor"], "rol": e["rol"],
                    "motivo": d.get("motivo", ""), "fps": d.get("fps", []),
                    "cambios": d.get("cambios", []), "reentrenamiento": d.get("reentrenamiento")})
    return out


def resumen() -> dict:
    """Payload de GET /api/realimentacion."""
    alertas = _alertas_json()
    with almacen.abriendo(estado._ruta()) as db:
        salida = metricas(db, alertas)
        salida["analisis"] = analisis.activo_id()
        salida["recalibraciones"] = _recalibraciones(db)
    salida["historico"] = _historico()
    return salida


# ---------- recalibración ----------

def _falsos_positivos(db, alertas_json: list[dict]) -> list[dict]:
    """FP = todo lo que el analista descartó: alertas del ciclo de vida y casos descartados."""
    fps = []
    for a in almacen.listar_alertas(db, estado="descartada"):
        fps.append({"id": f"alerta:{a['id']}", "titulo": a["titulo"], "caso": a["caso_id"]})
    for d in almacen.leer_registros(db, "decisiones"):
        if str(d.get("estado") or "").lower() == "descartado":
            fps.append({"id": f"caso:{d.get('clave')}", "titulo": None, "caso": d.get("casoId")})
    return fps


def _fps_aplicados(db) -> set[str]:
    """FP cuyo ajuste ya está en la bitácora: la recalibración es idempotente por estos."""
    ids: set[str] = set()
    for e in almacen.leer_bitacora(db):
        if e["accion"] == ACCION:
            try:
                ids.update(json.loads(e["detalle"]).get("fps") or [])
            except (ValueError, TypeError):
                continue
    return ids


def _paso(antes, direccion: str):
    """Paso conservador: 10 % del umbral actual (mínimo 1 unidad), en la dirección indicada."""
    if isinstance(antes, float):
        return max(0.01, round(antes * (1 + PASO if direccion == "subir" else 1 - PASO), 2))
    delta = max(1, round(antes * PASO))
    nuevo = antes + delta if direccion == "subir" else antes - delta
    return max(1, nuevo)


def _leer_umbral(ruta: Path, clave: str):
    try:
        yml = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    v = yml.get(clave) if isinstance(yml, dict) else None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _reescribir(texto: str, clave: str, nuevo) -> str | None:
    """Cambia SOLO el valor de la línea de la clave, conservando comentarios y formato."""
    lineas = texto.splitlines(keepends=True)
    for i, linea in enumerate(lineas):
        cuerpo = linea[:len(linea.rstrip("\r\n"))]
        m = re.match(rf"^(\s*{re.escape(clave)}:\s*)(-?\d+(?:\.\d+)?)(\s*(?:#.*)?)$", cuerpo)
        if m:
            valor = f"{nuevo:g}" if isinstance(nuevo, float) else str(nuevo)
            lineas[i] = f"{m.group(1)}{valor}{m.group(3)}{linea[len(cuerpo):]}"
            return "".join(lineas)
    return None


def sugerir(fps: list[dict], alertas_json: list[dict], reglas_dir: Path) -> tuple[list[dict], list[dict]]:
    """Ajustes sugeridos por FP: un paso sobre el umbral de su regla en rules/*.yml.

    Devuelve (cambios, sin_umbral): cambios deduplicados por clave con todos los FP que los
    respaldan; sin_umbral lista los FP para los que no hay número que ajustar (con la razón).
    """
    por_objetivo: dict[tuple[str, str], dict] = {}
    sin_umbral = []
    for fp in fps:
        tipos, nota = _tipos_de(fp, alertas_json)
        mapeadas = [UMBRAL_POR_TIPO[t] for t in tipos if t in UMBRAL_POR_TIPO]
        if not mapeadas:
            if tipos and not nota:
                nota = f"la regla {tipos[0]} no tiene umbral numérico ajustable"
            sin_umbral.append({"fps": [fp["id"]], "nota": nota or "sin umbral que ajustar"})
            continue
        fp["objetivos"] = set()
        for archivo, clave, direccion in mapeadas:
            e = por_objetivo.setdefault((archivo, clave), {"direccion": direccion, "fps": []})
            if fp["id"] not in e["fps"]:
                e["fps"].append(fp["id"])
            fp["objetivos"].add((archivo, clave))
    cambios = []
    for (archivo, clave), info in sorted(por_objetivo.items()):
        antes = _leer_umbral(reglas_dir / archivo, clave)
        if antes is None:
            sin_umbral.append({"fps": info["fps"], "nota": f"no se encontró {clave} numérico en {archivo}"})
            continue
        despues = _paso(antes, info["direccion"])
        if despues == antes:
            continue
        cambios.append({"archivo": archivo, "clave": clave, "antes": antes, "despues": despues,
                        "direccion": info["direccion"], "fps": info["fps"]})
    return cambios, sin_umbral


def _ruta_historico(fuente: str) -> Path:
    """Histórico de ventanas de este despliegue: en estado/ (solo-agregar, redirigible con
    SENTINEL_ESTADO); motor.ml usa su propia ruta por defecto para uso desde el motor."""
    return config.estado() / "historico" / f"{fuente}.csv"


def _archivos_analisis() -> tuple[Path, Path] | None:
    """CSV de firewall y sistema médico del análisis activo: la copia de entrada/ si existe,
    o el archivo original en la carpeta de datos (el análisis desde carpeta no copia)."""
    i = analisis.activo_id()
    if not i:
        return None
    try:
        m = analisis.obtener(i)
    except KeyError:
        return None
    entrada = analisis.carpeta() / i / "entrada"
    pares = []
    for campo, nombre in (("firewall", "firewall.csv"), ("sistema_medico", "sistema_medico.csv")):
        f = entrada / nombre
        if not f.exists():
            mostrado = str((m.get("archivos") or {}).get(campo) or "")
            f = next((c for d in (config.datos(), config.EJEMPLOS) if d.exists()
                      for c in sorted(d.glob("*.csv")) if analisis.mostrar(c.name) == mostrado), None)
        pares.append(f)
    if all(f is not None and f.exists() for f in pares):
        return pares[0], pares[1]
    return None


def _acumular_y_reentrenar() -> dict:
    """Acumula las ventanas del análisis activo en estado/historico/ y reentrena con el histórico.

    Mejor esfuerzo: si falta un archivo o el histórico está vacío se reporta en `notas` en vez de
    fallar la recalibración, que ya cambió los umbrales.
    """
    from motor import ingesta, ml
    salida: dict = {"notas": []}
    rutas = _archivos_analisis()
    if rutas:
        try:
            fw, med = rutas
            lfw = ingesta.leer_fw(fw, avance=lambda *_: None)
            ml.acumular(ml.ventanas_firewall(lfw.datos), "firewall", _ruta_historico("firewall"))
            lmed = ingesta.leer_med(med, avance=lambda *_: None)
            ml.acumular(ml.ventanas_sistema_medico(lmed.datos), "sistema_medico",
                        _ruta_historico("sistema_medico"))
        except Exception as e:                                  # la recalibración no depende de esto
            salida["notas"].append(f"No se pudieron acumular las ventanas del análisis: {e}")
    else:
        salida["notas"].append("Sin análisis activo con archivos accesibles: no se acumularon ventanas.")
    for fuente in FUENTES:
        ruta = _ruta_historico(fuente)
        if not ruta.exists():
            salida["notas"].append(f"Sin histórico de {fuente}: el modelo no se reentrenó.")
            continue
        try:
            m = ml.reentrenar(fuente, ruta)
            salida[fuente] = {"ventanas": m.ventanas, "semilla": m.semilla,
                              "modelo": "Isolation Forest"}
        except Exception as e:
            salida["notas"].append(f"No se pudo reentrenar {fuente}: {e}")
    return salida


def recalibrar(*, motivo: str, actor: str, rol: str, reglas_dir: Path | None = None) -> dict:
    """Aplica los ajustes sugeridos por los falsos positivos. Solo bajo invocación explícita.

    Idempotente: los FP ya aplicados (según bitácora) no se vuelven a aplicar; sin FP no cambia
    ningún archivo ni se registra nada. Si algo cambió, deja SIEMPRE evento en bitácora con quién,
    por qué y qué cambió.
    """
    motivo = str(motivo or "").strip()
    if len(motivo) < 10:
        raise ValueError("El motivo debe tener al menos 10 caracteres: quién ajusta y por qué.")
    destino = (Path(reglas_dir) if reglas_dir else
               Path(os.environ.get("SENTINEL_RULES") or (config.PROYECTO / "rules")))
    alertas = _alertas_json()
    with almacen.abriendo(estado._ruta()) as db:
        fps = _falsos_positivos(db, alertas)
        pendientes = [f for f in fps if f["id"] not in _fps_aplicados(db)]
        cambios, sin_umbral = sugerir(pendientes, alertas, destino)
        aplicados = []
        for c in cambios:
            ruta = destino / c["archivo"]
            try:
                texto = ruta.read_text(encoding="utf-8")
            except OSError:
                continue
            nuevo_texto = _reescribir(texto, c["clave"], c["despues"])
            if nuevo_texto is None or nuevo_texto == texto:
                continue
            ruta.write_text(nuevo_texto, encoding="utf-8")
            aplicados.append(c)
        if not aplicados:
            if not fps:
                nota = "Sin falsos positivos descartados: no se recalibra nada."
            elif not pendientes:
                nota = "Los falsos positivos ya se habían aplicado: nada que recalcular (idempotente)."
            else:
                nota = "Ningún falso positivo tiene umbral numérico ajustable: no se cambió ningún archivo."
            return {"cambios": [], "sinUmbral": sin_umbral, "aplicadas": [], "reentrenamiento": None,
                    "nota": nota}
        reentrenamiento = _acumular_y_reentrenar()
        objetivos_ok = {(c["archivo"], c["clave"]) for c in aplicados}
        aplicadas = [f["id"] for f in pendientes
                     if f.get("objetivos") and f["objetivos"] <= objetivos_ok]
        detalle = json.dumps({"motivo": motivo, "fps": aplicadas, "cambios": aplicados,
                              "reentrenamiento": reentrenamiento}, ensure_ascii=False)
        estado.bitacora(actor, rol, ACCION, "rules/*.yml", detalle)
        return {"cambios": aplicados, "sinUmbral": sin_umbral, "aplicadas": aplicadas,
                "reentrenamiento": reentrenamiento,
                "nota": f"Se ajustaron {len(aplicados)} umbral(es) por {len(aplicadas)} "
                        f"falso(s) positivo(s); todo queda en la bitácora."}
