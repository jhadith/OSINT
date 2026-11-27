"""Cargas de datos: cada análisis corre el motor en segundo plano y deja sus pasos visibles para la consola.

estado/analisis/<id>/
  entrada/        archivos subidos (si se subieron por el navegador)
  salidas/        lo que escribe el motor (incluye salidas/consola/)
  restringido/    tabla de reidentificación de ese análisis
  meta.json       archivos, autor, estado y pasos
estado/analisis/activo.txt   el análisis que muestra la consola
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess  # nosec B404 - se ejecuta solo el motor propio, con argumentos fijos y sin shell
import threading
import time
from pathlib import Path

from . import config, estado

PASOS = [
    ("recepcion", "Recepción de archivos", "Se reciben los archivos y se comprueba que sean CSV."),
    ("validacion", "Lectura y validación", "Se leen por partes; las filas dañadas se apartan sin detener el análisis."),
    ("normalizacion", "Normalización", "Fechas, IPs, usuarios y acciones quedan en un formato común."),
    ("reglas", "Detección por reglas", "Se buscan patrones de ataque conocidos en cada fuente."),
    ("cruce", "Cruce de fuentes", "Se une lo que pasó en la red con lo que pasó en el sistema médico."),
    ("modelo", "Machine learning", "Isolation Forest compara cada usuario y cuenta con el resto del mes."),
    ("agendamiento", "Agendamiento médico (HBVF)", "Se agrupan sesiones del chatbot y se validan patrones."),
    ("priorizacion", "Priorización", "Cada hallazgo recibe un puntaje de probabilidad por impacto."),
    ("proteccion", "Protección de datos", "Nombres y usuarios salen convertidos en seudónimos."),
    ("listo", "Resultados listos", "La consola muestra el nuevo análisis."),
]
_lock = threading.Lock()
_en_curso: dict[str, subprocess.Popen] = {}
NOMBRE_SEGURO = re.compile(r"^[\w\-. ()]{1,120}\.csv$", re.IGNORECASE)


def carpeta() -> Path:
    d = config.estado() / "analisis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def activo_id() -> str | None:
    f = carpeta() / "activo.txt"
    if f.exists():
        i = f.read_text(encoding="utf-8").strip()
        if (carpeta() / i / "salidas" / "consola" / "casos.json").exists():
            return i
    return None


def salidas_activas() -> Path | None:
    i = activo_id()
    return carpeta() / i / "salidas" if i else None


def restringido_activo() -> Path | None:
    i = activo_id()
    return carpeta() / i / "restringido" if i else None


def _meta(i: str) -> dict:
    return json.loads((carpeta() / i / "meta.json").read_text(encoding="utf-8"))


def _guardar(i: str, m: dict) -> None:
    """Escritura atómica: quien lee el progreso nunca ve un archivo a medio escribir.
    En Windows el reemplazo falla si otro hilo tiene el archivo abierto en ese instante; se reintenta."""
    destino = carpeta() / i / "meta.json"
    tmp = destino.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    for intento in range(20):
        try:
            os.replace(tmp, destino)
            return
        except PermissionError:
            time.sleep(0.05 * (intento + 1))
    destino.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")
    tmp.unlink(missing_ok=True)


def listar() -> list[dict]:
    act = activo_id()
    out = []
    for d in sorted(carpeta().iterdir(), reverse=True):
        if d.is_dir() and (d / "meta.json").exists():
            m = _meta(d.name)
            m["activo"] = d.name == act
            out.append({k: m[k] for k in ("id", "creado", "autor", "estado", "archivos", "activo", "resumen")})
    return out


def obtener(i: str) -> dict:
    if not re.fullmatch(r"AN-\d{8}-\d{6}-[0-9a-f]{4}", i) or not (carpeta() / i / "meta.json").exists():
        raise KeyError(i)
    m = _meta(i)
    m["activo"] = i == activo_id()
    return m


def mostrar(nombre: str) -> str:
    """Nombre de archivo para pantalla, sin el nombre de la institución que traen los datasets del reto."""
    return re.sub(r"(?i)iess", "inst", nombre)


def fuentes() -> list[dict]:
    """CSV disponibles en la carpeta de datos del equipo y en los ejemplos del proyecto."""
    out = []
    for origen, d in (("datos", config.datos()), ("ejemplo", config.EJEMPLOS)):
        if d.exists():
            for f in sorted(d.glob("*.csv")):
                out.append({"origen": origen, "nombre": f.name, "etiqueta": mostrar(f.name),
                            "mb": round(f.stat().st_size / 1e6, 1), "tipo": _adivinar_tipo(f.name)})
    return out


def _adivinar_tipo(nombre: str) -> str:
    n = nombre.lower()
    if "fw" in n or "firewall" in n:
        return "firewall"
    if "med" in n:
        return "sistema_medico"
    if "agenda" in n or "cita" in n or "chatbot" in n:
        return "agendamiento"
    return "otro"


def resolver_fuente(origen: str, nombre: str) -> Path:
    base = {"datos": config.datos(), "ejemplo": config.EJEMPLOS}.get(origen)
    if base is None or not NOMBRE_SEGURO.match(nombre):
        raise ValueError("Archivo no permitido.")
    f = (base / nombre).resolve()
    if f.parent != base.resolve() or not f.is_file():
        raise ValueError(f"No existe {nombre} en la carpeta de {origen}.")
    return f


def nuevo(autor: str) -> str:
    import datetime as dt
    i = f"AN-{dt.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    (carpeta() / i / "entrada").mkdir(parents=True)
    return i


def guardar_subida(i: str, campo: str, archivo) -> Path:
    destino = carpeta() / i / "entrada" / f"{campo}.csv"
    total = 0
    with open(destino, "wb") as f:
        while True:
            trozo = archivo.read(1024 * 1024)
            if not trozo:
                break
            total += len(trozo)
            if total > config.MAX_SUBIDA:
                raise ValueError("El archivo supera el tamaño máximo permitido.")
            f.write(trozo)
    return destino


def ocupado() -> bool:
    with _lock:
        return any(p.poll() is None for p in _en_curso.values())


def lanzar(i: str, autor: str, fw: Path, med: Path, citas: Path | None, reportes: list[str],
           al_terminar) -> dict:
    """Arranca el motor en otro proceso. `al_terminar(id)` se llama cuando el análisis queda listo."""
    if ocupado():
        raise RuntimeError("Ya hay un análisis en curso. Espera a que termine.")
    d = carpeta() / i
    pasos = [{"id": k, "nombre": n, "explicacion": e, "estado": "pendiente", "datos": {}} for k, n, e in PASOS]
    pasos[0].update(estado="listo", datos={"firewall": mostrar(fw.name), "sistema_medico": mostrar(med.name),
                                           "agendamiento": mostrar(citas.name) if citas else None,
                                           "mb": round(sum(p.stat().st_size for p in [fw, med] + ([citas] if citas else []))
                                                       / 1e6, 1)})
    meta = {"id": i, "creado": estado.ahora(), "autor": autor, "estado": "en_curso",
            "archivos": {"firewall": mostrar(fw.name), "sistema_medico": mostrar(med.name),
                         "agendamiento": mostrar(citas.name) if citas else None},
            "pasos": pasos, "resumen": None, "error": None, "registro": []}
    _guardar(i, meta)
    rep = d / "reportes.txt"
    rep.write_text("\n".join(reportes), encoding="utf-8")
    cmd = [config.PYTHON_MOTOR, "-m", "motor", "--fw", str(fw), "--med", str(med), "--salidas", str(d / "salidas"),
           "--restringido", str(d / "restringido"), "--reportes", str(rep)]
    if citas:
        cmd += ["--citas", str(citas)]
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(cmd, cwd=str(config.MOTOR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,  # nosec B603  # noqa: S603 (lista fija, sin shell)
                            text=True, encoding="utf-8", errors="replace", bufsize=1, env=entorno)
    with _lock:
        _en_curso[i] = proc
    threading.Thread(target=_seguir, args=(i, proc, al_terminar), daemon=True).start()
    return meta


def _seguir(i: str, proc: subprocess.Popen, al_terminar) -> None:
    meta = _meta(i)
    por_id = {p["id"]: p for p in meta["pasos"]}
    for linea in proc.stdout:
        linea = linea.rstrip()
        if linea.startswith("@@"):
            try:
                ev = json.loads(linea[2:])
            except ValueError:
                continue
            p = por_id.get(ev.pop("paso"))
            if p:
                p["estado"] = ev.pop("estado")
                p["datos"].update(ev)
            _guardar(i, meta)
        elif linea.strip():
            meta["registro"] = (meta["registro"] + [linea])[-30:]
    proc.wait()
    if proc.returncode == 0:
        meta["estado"] = "listo"
        r = json.loads((carpeta() / i / "salidas" / "resumen_motor.json").read_text(encoding="utf-8"))
        meta["resumen"] = {"registros": r["registros"]["total"], "minutos": r["tiempo_analisis_min"],
                           "periodo": r["periodo"]}
        (carpeta() / "activo.txt").write_text(i, encoding="utf-8")
    else:
        meta["estado"] = "error"
        for p in meta["pasos"]:
            if p["estado"] == "en_curso":
                p["estado"] = "error"
        meta["error"] = "El motor se detuvo. Revisa que los archivos tengan las columnas del reto."
    _guardar(i, meta)
    with _lock:
        _en_curso.pop(i, None)
    estado.bitacora(meta["autor"], "Sentinel Salud", "Análisis terminado" if proc.returncode == 0 else "Análisis con error",
                    i, f"{meta['archivos']['firewall']} y {meta['archivos']['sistema_medico']}")
    if proc.returncode == 0:
        al_terminar(i)


def activar(i: str) -> None:
    m = obtener(i)
    if m["estado"] != "listo":
        raise ValueError("Solo se puede activar un análisis terminado.")
    (carpeta() / "activo.txt").write_text(i, encoding="utf-8")


def borrar_entrada(i: str) -> None:
    shutil.rmtree(carpeta() / i / "entrada", ignore_errors=True)
