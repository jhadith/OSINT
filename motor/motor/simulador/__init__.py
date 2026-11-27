"""Simulador local del chatbot de citas con fingerprint de dispositivo (T21, S8).

Se **simula** un chatbot de agendamiento (IzyBot del IESS no se toca): las
peticiones llevan un ``device_id`` obtenido por fingerprint en JS local
(``web/simulador/``), espejo de :mod:`motor.simulador.fingerprint`. El backend
(:mod:`motor.simulador.backend`) registra la telemetría de 9 columnas y aplica
un verificador de bloqueo **inyectable**; la detección de tramitadores y la
sanción progresiva viven en :mod:`motor.sanciones` (T22).

El backend se importa desde ``motor.simulador.backend`` (requiere FastAPI);
este paquete en sí solo depende del estándar.
"""

from __future__ import annotations

from .fingerprint import device_id

# Contrato de telemetría del informe 14.4 (9 columnas), compartido por el
# backend y el generador de la muestra.
COLUMNAS = [
    "id_evento",
    "id_cita",
    "fecha_hora",
    "accion",
    "canal",
    "referencia_paciente",
    "id_sesion",
    "senal_tecnica",
    "device_id",
]

__all__ = ["COLUMNAS", "device_id"]
