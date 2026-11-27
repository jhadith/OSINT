"""Fingerprint de dispositivo para el simulador de chatbot (T21, S8).

Espejo local de ``web/simulador/fingerprint.js``: mismas señales, misma regla
de identidad. ``device_id = "DEV-" + primeros 16 hex de SHA-256 sobre el JSON
canónico de las señales`` (claves ordenadas, sin espacios, sin escape de
acentos). Solo hashing estándar de Python: sin red ni estado.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["canonica", "device_id"]


def canonica(senales: dict[str, Any]) -> str:
    """Serializa las señales de forma canónica e independiente del orden."""
    return json.dumps(
        senales, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def device_id(senales: dict[str, Any]) -> str:
    """Devuelve ``DEV-<16 hex>`` estable a partir de las señales del dispositivo."""
    digest = hashlib.sha256(canonica(senales).encode("utf-8")).hexdigest()
    return f"DEV-{digest[:16]}"
