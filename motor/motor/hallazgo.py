"""Estructura interna de un hallazgo antes de priorizarlo y convertirlo al contrato de salida."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hallazgo:
    regla: str
    fuente: str                         # firewall | sistema_medico | correlacion
    inicio: int                         # segundos desde EPOCA, en el reloj del sistema médico si hay correlación
    fin: int
    tecnicas: list[str] = field(default_factory=list)
    evidencia: dict = field(default_factory=dict)
    general: bool = False               # hallazgo de configuración del mes, no un ataque puntual
    # firewall
    iph: int | None = None
    ip: str = ""
    usuarios: list[str] = field(default_factory=list)
    filas_fw: list[int] = field(default_factory=list)
    eventos_fw: int = 0
    segmento: bool = False
    desfase_h: int = 0                  # horas que se restaron al reloj del firewall para alinearlo
    # sistema médico
    cuenta: str = ""
    personas: list[str] = field(default_factory=list)
    idx_med: list[int] = field(default_factory=list)
    eventos_med: int = 0
    # machine learning
    ml: dict = field(default_factory=dict)
    solo_ml: bool = False               # lo marcó el modelo y ninguna regla

    def tecnica(self, *ts: str) -> None:
        for t in ts:
            if t not in self.tecnicas:
                self.tecnicas.append(t)
