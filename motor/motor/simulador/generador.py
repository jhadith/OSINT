"""Generador determinista de la muestra de chatbot (T21/T22, S8).

Escribe un CSV con las 9 columnas de telemetría (siempre con ``device_id``
calculado por fingerprint) que sirve de insumo a la detección de tramitadores:

- 400 dispositivos legítimos con 1 a 12 filas cada uno (nunca más de 6
  reservas por dispositivo/día: por debajo del umbral de 10);
- 3 tramitadores con 60/40/25 reservas, todas para pacientes distintos y en
  un mismo día (2026-10-19), por encima de la banda de tramitador.

Determinista byte a byte con ``seed=42``: sin reloj real, sin uuid y sin
iterar conjuntos sin ordenar. Uso: ``scripts/simulador_chatbot.py --generar``.
"""
from __future__ import annotations

import csv
import hashlib
import random
from datetime import datetime, timedelta
from pathlib import Path

from . import COLUMNAS
from .fingerprint import device_id

SEED = 42
N_LEGITIMOS = 400
TRAMITADORES = (60, 40, 25)
DIA_TRAMITADORES = datetime(2026, 10, 19, 7, 0, 0)

CANALES = ["app", "web", "call_center", "presencial"]
PANTALLAS = ["1920x1080x24", "1366x768x24", "2560x1440x24", "1280x800x30"]
NAVEGADORES = [
    "Mozilla/5.0 (X11; Linux x86_64) SentinelSim/1.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SentinelSim/1.0",
    "Mozilla/5.0 (Linux; Android 14) SentinelSim/1.0",
]
HUSOS = [-300, -360, -240, 0]
OTRAS_ACCIONES = ["confirmar", "modificar", "cancelar", "no_show"]


def _senales(rng: random.Random) -> dict:
    """Señales canónicas del fingerprint (mismo dict → mismo device_id)."""
    return {
        "canvas": hashlib.sha256(f"canvas-{rng.getrandbits(64):016x}".encode()).hexdigest()[:16],
        "devicePixelRatio": rng.choice([1, 1, 1.5, 2]),
        "screen": rng.choice(PANTALLAS),
        "timezone": rng.choice(HUSOS),
        "userAgent": rng.choice(NAVEGADORES),
    }


def _senal_tecnica(senales: dict) -> str:
    return "JA4T_" + hashlib.sha256(
        repr(sorted(senales.items())).encode()
    ).hexdigest()[:12]


def _fila(fecha, sesion, cita, accion, canal, paciente, senal, dev) -> dict:
    return {
        "id_cita": cita,
        "fecha_hora": fecha.isoformat(),
        "accion": accion,
        "canal": canal,
        "referencia_paciente": paciente,
        "id_sesion": sesion,
        "senal_tecnica": senal,
        "device_id": dev,
    }


def _legitimo(rng: random.Random, indice: int) -> list[dict]:
    """Un dispositivo legítimo: 1–12 filas en un día, a lo sumo 6 reservas/día."""
    senales = _senales(rng)
    dev = device_id(senales)
    n_filas = indice % 12 + 1                      # todos los valores 1..12, tope exacto
    n_reservas = min(n_filas, 6)                   # banda normal: nunca cruza el umbral 10
    dia = 1 + indice % 28
    fecha = datetime(2026, 10, dia, 6 + indice % 12, (indice * 7) % 60, 0)
    sesion = f"SES-SIM-LEG-{indice:04d}"
    canal = rng.choice(CANALES)
    senal = _senal_tecnica(senales)
    pacientes = [f"PAC-LEG-{indice:04d}-{k}" for k in range(1 + indice % 3)]
    filas: list[dict] = []
    citas: list[str] = []
    for k in range(n_filas):
        if k < n_reservas:
            accion = "reservar"
            cita = f"CIT-LEG-{indice:04d}-{k:02d}"
            citas.append(cita)
        else:
            accion = OTRAS_ACCIONES[(k - n_reservas) % len(OTRAS_ACCIONES)]
            cita = citas[k % len(citas)]
        paciente = pacientes[k % len(pacientes)]
        filas.append(_fila(fecha, sesion, cita, accion, canal, paciente, senal, dev))
        fecha += timedelta(minutes=rng.randint(1, 20))
    return filas


def _tramitador(rng: random.Random, indice: int, total: int) -> list[dict]:
    """Un tramitador: `total` reservas en un mismo día para pacientes distintos."""
    senales = _senales(rng)
    dev = device_id(senales)
    sesion = f"SES-SIM-TRAM-{indice:02d}"
    canal = rng.choice(CANALES)
    senal = _senal_tecnica(senales)
    base = DIA_TRAMITADORES + timedelta(minutes=5 * indice)
    filas: list[dict] = []
    for k in range(total):
        fecha = base + timedelta(seconds=30 * k)
        filas.append(_fila(
            fecha, sesion, f"CIT-TRAM-{indice:02d}-{k:03d}", "reservar", canal,
            f"PAC-TRAM-{indice:02d}-{k:03d}", senal, dev,
        ))
    return filas


def generar_filas() -> list[dict]:
    """Todas las filas de la muestra, ordenadas de forma determinista."""
    rng = random.Random(SEED)
    filas: list[dict] = []
    for indice in range(N_LEGITIMOS):
        filas.extend(_legitimo(rng, indice))
    for indice, total in enumerate(TRAMITADORES):
        filas.extend(_tramitador(rng, indice, total))
    filas.sort(key=lambda f: (f["fecha_hora"], f["device_id"], f["id_sesion"], f["id_cita"]))
    return filas


def generar_muestra(ruta: Path) -> int:
    """Escribe la muestra en `ruta` (padres creados) y devuelve el nº de filas."""
    filas = generar_filas()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
        escritor.writeheader()
        for indice, fila in enumerate(filas, start=1):
            escritor.writerow({"id_evento": f"EV-SIM-{indice:06d}", **fila})
    return len(filas)
