"""Detección de tramitadores por reservas/dispositivo/día (T22, S8).

Regla (umbrales en ``config/sanciones.yaml``):

- **candidato**: un dispositivo que supera ``umbral_reservas_dispositivo_dia``
  (10) reservas en un mismo día; se le asigna un perfil según las bandas del
  informe 14.6 — normal ≤6, familiar ≤12, entre 13 y 24 queda en observación,
  tramitador 25–100.
- **tramitador detectado**: un candidato cuyo perfil es ``tramitador``. Los
  dispositivos familiares compartidos (≤12/día) y los normales jamás se
  detectan ni se sancionan.

Las funciones reciben filas de telemetría (dicts con ``device_id``,
``fecha_hora``, ``accion``, ``referencia_paciente``) y **no** reciben el
identificador de la cita: la detección no mira ni toca citas de terceros.
"""
from __future__ import annotations

from .config import cargar_config

__all__ = ["candidatos", "detectar_tramitadores", "perfil", "reservas_por_dispositivo_dia"]


def _agrupar(filas) -> dict[tuple[str, str], dict]:
    grupos: dict[tuple[str, str], dict] = {}
    for fila in filas:
        if fila.get("accion") != "reservar":
            continue
        device_id = fila.get("device_id") or ""
        fecha = fila.get("fecha_hora") or ""
        clave = (device_id, fecha[:10])
        grupo = grupos.setdefault(clave, {"reservas": 0, "pacientes": set()})
        grupo["reservas"] += 1
        paciente = fila.get("referencia_paciente") or ""
        if paciente:
            grupo["pacientes"].add(paciente)
    return grupos


def reservas_por_dispositivo_dia(filas) -> dict[tuple[str, str], int]:
    """{(device_id, día): nº de reservas} sobre la telemetría."""
    return {clave: g["reservas"] for clave, g in _agrupar(filas).items()}


def perfil(reservas_dia: int, cfg=None) -> str:
    """Bandas del informe 14.6: normal ≤6, familiar ≤12, observación 13–24, tramitador ≥25."""
    cfg = cfg or cargar_config()
    if reservas_dia <= cfg.normal_max_reservas_dia:
        return "normal"
    if reservas_dia <= cfg.familiar_max_reservas_dia:
        return "familiar"
    if reservas_dia < cfg.tramitador_min_reservas_dia:
        return "observacion"
    return "tramitador"


def candidatos(filas, cfg=None) -> list[dict]:
    """Dispositivos que superan el umbral de reservas/dispositivo/día, con perfil."""
    cfg = cfg or cargar_config()
    grupos = _agrupar(filas)
    salida = []
    for (device_id, dia), grupo in grupos.items():
        reservas = grupo["reservas"]
        if reservas <= cfg.umbral_reservas_dispositivo_dia:
            continue
        salida.append({
            "device_id": device_id,
            "fecha": dia,
            "reservas": reservas,
            "pacientes": len(grupo["pacientes"]),
            "perfil": perfil(reservas, cfg),
        })
    salida.sort(key=lambda d: (-d["reservas"], d["device_id"]))
    return salida


def detectar_tramitadores(filas, cfg=None) -> list[dict]:
    """Candidatos en la banda de tramitador (25–100 reservas/día): los sancionables."""
    cfg = cfg or cargar_config()
    return [c for c in candidatos(filas, cfg) if c["perfil"] == "tramitador"]
