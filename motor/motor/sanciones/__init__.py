"""Sanción progresiva del simulador de chatbot (T22, S8).

Detección de tramitadores por reservas/dispositivo/día (umbral y bandas en
``config/sanciones.yaml``) y motor de sanción con SQLite propio
(``sanciones.sqlite3``): ofensas, bloqueos, apelaciones y bitácora
**append-only** (triggers abortan UPDATE/DELETE).

Principios:
- La sanción aplica **SOLO sobre el dispositivo emisor**; jamás sobre citas
  ya reservadas de terceros (ninguna función de este paquete recibe el
  identificador de la cita — hay test que lo garantiza).
- Bloqueo progresivo ``[1, 4, 24, 72]`` h con ventana de 30 días; el
  dispositivo bloqueado recibe HTTP 423 en el simulador (verificador
  inyectable ``Sancionador.verificador``).
- Toda ofensa deja bitácora, incluido el aviso de equipo compartido; la
  apelación se registra y espera revisión humana (no levanta el bloqueo sola).
"""
from __future__ import annotations

from .config import ConfigSanciones, cargar_config
from .deteccion import candidatos, detectar_tramitadores, perfil
from .sancion import Sancionador

__all__ = [
    "ConfigSanciones",
    "Sancionador",
    "cargar_config",
    "candidatos",
    "detectar_tramitadores",
    "perfil",
]
