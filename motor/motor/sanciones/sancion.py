"""Motor de sanción progresiva SOLO sobre el dispositivo emisor (T22, S8).

Escala ``bloqueo_horas: [1, 4, 24, 72]`` (primera ofensa = 1 h exactas) con
``ventana_ofensas_dias: 30``: fuera de la ventana el contador vuelve a empezar.
Toda ofensa deja ofensa + bloqueo + bitácora (incluido el aviso de equipo
compartido); la apelación se registra como ``pendiente`` y espera revisión
humana — nunca levanta el bloqueo por sí sola.

Ninguna función de este motor recibe el identificador de la cita: la sanción
nunca afecta citas ya reservadas de terceros. El método ``verificador`` tiene
la forma ``Callable[[str, datetime], str | None]`` que inyecta el backend del
simulador (``motor.simulador.backend.crear_simulador``) para responder 423.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from . import almacen
from .config import ConfigSanciones, cargar_config

AVISO_COMPARTIDO = (
    "la sanción aplica solo al dispositivo emisor; si el equipo se comparte en "
    "familia, revisar la apelación antes de mantener el bloqueo"
)


class Sancionador:
    """Ofensas/bloqueos/apelaciones/bitácora en un SQLite propio (append-only)."""

    def __init__(self, ruta_bd: Path, cfg: ConfigSanciones | None = None,
                 reloj=None) -> None:
        self.ruta = Path(ruta_bd)
        self.cfg = cfg or cargar_config()
        self.reloj = reloj or datetime.now
        almacen.crear_esquema(self.ruta)

    # ------------------------------------------------------------- consultas

    def ofensas(self, device_id: str) -> list[dict]:
        with almacen.abrir(self.ruta) as conn:
            return almacen.ofensas(conn, device_id)

    def ofensas_en_ventana(self, device_id: str, ahora: datetime | None = None) -> int:
        """Ofensas dentro de la ventana deslizante de ``ventana_ofensas_dias``."""
        ahora = ahora or self.reloj()
        desde = (ahora - timedelta(days=self.cfg.ventana_ofensas_dias)).isoformat()
        with almacen.abrir(self.ruta) as conn:
            return len(almacen.ofensas_desde(conn, device_id, desde))

    def bloqueos(self, device_id: str) -> list[dict]:
        with almacen.abrir(self.ruta) as conn:
            return almacen.bloqueos(conn, device_id)

    def apelaciones(self, device_id: str) -> list[dict]:
        with almacen.abrir(self.ruta) as conn:
            return almacen.apelaciones(conn, device_id)

    def bitacora(self, device_id: str | None = None) -> list[dict]:
        with almacen.abrir(self.ruta) as conn:
            return almacen.bitacora(conn, device_id)

    # ------------------------------------------------------------- sanciones

    def registrar_ofensa(self, device_id: str, motivo: str,
                         ahora: datetime | None = None) -> str:
        """Registra la ofensa y aplica el bloqueo progresivo; devuelve ``bloqueado_hasta`` (ISO)."""
        ahora = ahora or self.reloj()
        nivel = self.ofensas_en_ventana(device_id, ahora) + 1
        horas = self.cfg.bloqueo_horas[min(nivel, len(self.cfg.bloqueo_horas)) - 1]
        desde_iso, hasta_iso = ahora.isoformat(), (ahora + timedelta(hours=horas)).isoformat()
        with almacen.abrir(self.ruta) as conn:
            almacen.insertar_ofensa(conn, device_id, desde_iso, motivo)
            almacen.insertar_bloqueo(conn, device_id, desde_iso, hasta_iso, nivel, horas)
            almacen.insertar_bitacora(conn, desde_iso, "ofensa", device_id, motivo)
            almacen.insertar_bitacora(conn, desde_iso, "bloqueo", device_id,
                                      f"nivel {nivel}: {horas} h hasta {hasta_iso}")
            almacen.insertar_bitacora(conn, desde_iso, "aviso_dispositivo_compartido",
                                      device_id, AVISO_COMPARTIDO)
        return hasta_iso

    def bloqueo_activo(self, device_id: str, ahora: datetime | None = None) -> str | None:
        """``bloqueado_hasta`` (ISO) si el dispositivo está bloqueado; None si no."""
        ahora = ahora or self.reloj()
        with almacen.abrir(self.ruta) as conn:
            fila = almacen.bloqueo_activo(conn, device_id, ahora.isoformat())
        return fila["hasta"] if fila else None

    def verificador(self, device_id: str, ahora: datetime) -> str | None:
        """Adapter del backend del simulador: (device_id, ahora) → hasta | None."""
        return self.bloqueo_activo(device_id, ahora)

    def apelar(self, device_id: str, motivo: str,
               ahora: datetime | None = None) -> dict:
        """Registra una apelación pendiente (no levanta el bloqueo: revisión humana)."""
        ahora = ahora or self.reloj()
        with almacen.abrir(self.ruta) as conn:
            registro = almacen.insertar_apelacion(conn, device_id, ahora.isoformat(), motivo)
            almacen.insertar_bitacora(conn, ahora.isoformat(), "apelacion", device_id, motivo)
        return registro
