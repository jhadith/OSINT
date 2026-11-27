"""Umbrales de detección y sanción: viven en ``config/sanciones.yaml``, no en el código.

El SOC calibra el umbral de reservas/dispositivo/día, las bandas de perfil
(normal ≤6, familiar ≤12, tramitador 25–100) y la escala de sanción progresiva
(``bloqueo_horas``, ``ventana_ofensas_dias``) sin tocar Python; un test
comprueba que los valores cargados son exactos los del YAML.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# …/sentinel/motor/motor/sanciones/config.py → raíz del repositorio
RUTA_DEFECTO = Path(__file__).resolve().parents[3] / "config" / "sanciones.yaml"

_CLAVES = (
    "umbral_reservas_dispositivo_dia",
    "normal_max_reservas_dia",
    "familiar_max_reservas_dia",
    "tramitador_min_reservas_dia",
    "tramitador_max_reservas_dia",
    "bloqueo_horas",
    "ventana_ofensas_dias",
)


@dataclass(frozen=True)
class ConfigSanciones:
    umbral_reservas_dispositivo_dia: int
    normal_max_reservas_dia: int
    familiar_max_reservas_dia: int
    tramitador_min_reservas_dia: int
    tramitador_max_reservas_dia: int
    bloqueo_horas: tuple[int, ...]
    ventana_ofensas_dias: int


def cargar_config(ruta: Path | None = None) -> ConfigSanciones:
    """Lee ``config/sanciones.yaml`` (o `ruta`) y valida su forma."""
    ruta = ruta or RUTA_DEFECTO
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la configuración de sanciones: {ruta}")
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    if not isinstance(datos, dict):
        raise ValueError(f"{ruta.name}: se esperaba un mapeo nombre → valor")
    faltantes = [c for c in _CLAVES if c not in datos]
    if faltantes:
        raise ValueError(f"{ruta.name}: faltan claves {faltantes}")
    horas = datos["bloqueo_horas"]
    if not isinstance(horas, list) or not horas or not all(
        isinstance(h, int) and h > 0 for h in horas
    ):
        raise ValueError(f"{ruta.name}: bloqueo_horas debe ser una lista de enteros > 0")
    if datos["ventana_ofensas_dias"] <= 0:
        raise ValueError(f"{ruta.name}: ventana_ofensas_dias debe ser > 0")
    return ConfigSanciones(
        umbral_reservas_dispositivo_dia=int(datos["umbral_reservas_dispositivo_dia"]),
        normal_max_reservas_dia=int(datos["normal_max_reservas_dia"]),
        familiar_max_reservas_dia=int(datos["familiar_max_reservas_dia"]),
        tramitador_min_reservas_dia=int(datos["tramitador_min_reservas_dia"]),
        tramitador_max_reservas_dia=int(datos["tramitador_max_reservas_dia"]),
        bloqueo_horas=tuple(horas),
        ventana_ofensas_dias=int(datos["ventana_ofensas_dias"]),
    )
