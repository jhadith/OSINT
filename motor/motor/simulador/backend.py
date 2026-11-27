"""Backend del simulador de chatbot (T21, S8): telemetría de 9 columnas + verificador inyectable.

Mini-aplicación FastAPI detrás de la página estática ``web/simulador/``:

- ``POST /reservar`` registra cada petición en la telemetría (CSV o JSONL)
  con las columnas del informe 14.4: id_evento, id_cita, fecha_hora, accion,
  canal, referencia_paciente, id_sesion, senal_tecnica, device_id.
- Si se inyecta ``verificador_bloqueo: Callable[[str, datetime], str | None]``
  y devuelve ``bloqueado_hasta``, la petición responde HTTP 423 con motivo y
  **no deja telemetría** (nada de eventos para quien está bloqueado).
- Sin verificador, siempre acepta: la detección/sanción es T22 y este módulo
  no importa ``motor.sanciones`` (la inyección rompe el acoplamiento).

Nada de esto toca citas reales: es una SIMULACIÓN; el chatbot real (IzyBot)
no se modifica.
"""
from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import COLUMNAS

# web/simulador/ en la raíz del repositorio (…/sentinel/motor/motor/simulador/backend.py)
WEB_DIR = Path(__file__).resolve().parents[3] / "web" / "simulador"

RELOJ_DEFECTO = datetime.now


class Peticion(BaseModel):
    """Contrato del payload aceptado por POST /reservar."""

    id_cita: str
    accion: str = "reservar"
    canal: str = "app"
    referencia_paciente: str
    device_id: str
    senal_tecnica: str = ""        # opcional


def _siguiente_indice(ruta: Path) -> int:
    """Siguiente id_evento EV-SIM-%06d: continúa si el archivo ya existe."""
    if not ruta.exists():
        return 1
    with open(ruta, encoding="utf-8") as fh:
        lineas = sum(1 for _ in fh)
    if ruta.suffix == ".jsonl":
        return lineas + 1
    return max(lineas, 1)          # con header: filas + 1


def _registrar(ruta: Path, fila: dict) -> None:
    """Agrega una fila a la telemetría: CSV (con header la primera vez) o JSONL."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.suffix == ".jsonl":
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        return
    existe = ruta.exists()
    with open(ruta, "a", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUMNAS)
        if not existe:
            escritor.writeheader()
        escritor.writerow(fila)


def crear_simulador(
    ruta: Path,
    verificador_bloqueo: Callable[[str, datetime], str | None] | None = None,
    reloj: Callable[[], datetime] = RELOJ_DEFECTO,
) -> FastAPI:
    """Crea la app del simulador.

    - ``ruta``: archivo de telemetría (.csv o .jsonl); se crea al primer evento
      aceptado (una petición bloqueada no lo toca).
    - ``verificador_bloqueo(device_id, ahora)``: devuelve ``bloqueado_hasta``
      (ISO) para responder 423, o ``None`` para aceptar. Inyectable para que
      T22 conecte su SQLite de sanciones sin acoplamiento.
    - ``reloj``: reloj inyectable; la telemetría registra exactamente su instante.
    """
    app = FastAPI(title="Simulador de citas (SIMULACIÓN)", docs_url=None, redoc_url=None)
    estado = {"siguiente": _siguiente_indice(ruta)}

    @app.post("/reservar")
    def reservar(p: Peticion):
        ahora = reloj()
        if verificador_bloqueo is not None:
            hasta = verificador_bloqueo(p.device_id, ahora)
            if hasta is not None:
                return JSONResponse(status_code=423, content={
                    "aceptada": False,
                    "motivo": "dispositivo_bloqueado",
                    "bloqueado_hasta": hasta,
                })
        fila = {
            "id_evento": f"EV-SIM-{estado['siguiente']:06d}",
            "id_cita": p.id_cita,
            "fecha_hora": ahora.isoformat(),
            "accion": p.accion,
            "canal": p.canal,
            "referencia_paciente": p.referencia_paciente,
            "id_sesion": f"SES-SIM-{uuid.uuid4().hex[:12]}",
            "senal_tecnica": p.senal_tecnica,
            "device_id": p.device_id,
        }
        estado["siguiente"] += 1
        _registrar(ruta, fila)
        return {"aceptada": True}

    @app.get("/simulador/")
    def pagina():
        return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")

    @app.get("/simulador/fingerprint.js")
    def fingerprint_js():
        return FileResponse(WEB_DIR / "fingerprint.js", media_type="text/javascript; charset=utf-8")

    return app
