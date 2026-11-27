"""ThreatPulse · evaluación local de tendencias del sector salud (T7, S6c).

Traduce el informe F-11 a un score por tendencia: "marca las amenazas que crecen,
son recientes y vienen de fuentes confiables" y "cada tendencia se evalúa por su
relevancia para salud, la exposición del IESS y el impacto posible".

Todo es aritmética sobre el JSON local de fijos/tendencias.json: sin red, sin
llamadas externas y sin datos personales. El resultado es una hipótesis para
revisión humana, nunca una atribución ni una incidencia confirmada.

score = 100 × recencia × relevanciaSalud × exposicionIess × impactoPosible
          × confianzaFuente × crecimiento
"""
from __future__ import annotations

from datetime import date, datetime

# Confianza editorial de cada fuente pública simulada (0-1). Las no listadas
# no se marcan como confiables y quedan con score 0.
CONFIANZA_FUENTE: dict[str, float] = {
    "MITRE ATT&CK": 0.95,
    "CISA": 0.9,
    "ENISA": 0.9,
    "HHS": 0.85,
}
RELEVANCIA_NO_SALUD = 0.3
VIDA_MEDIA_DIAS = 30          # vida media de la recencia
UMBRAL_RECIENTE_DIAS = 30     # "reciente" para la marca del F-11
UMBRAL_CONFIABLE = 0.8
CRECIMIENTO_MIN, CRECIMIENTO_MAX = 0.8, 1.2


def _como_fecha(valor: object) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            return None
    return None


def recencia(tendencia: dict, hoy: date) -> float:
    """0.5 ** (días/30): vida media de 30 días; fechas futuras valen 1.0.

    Fecha inválida o ausente → 0.0 (la tendencia queda al final del ranking).
    """
    fecha = _como_fecha(tendencia.get("fecha"))
    if fecha is None:
        return 0.0
    dias = (hoy - fecha).days
    if dias < 0:
        return 1.0
    return 0.5 ** (dias / VIDA_MEDIA_DIAS)


def crecimiento(tendencia: dict) -> float:
    """Factor 0.8-1.2 según la serie: crece → 1.2, cae → 0.8, plana o sin serie → 1.0."""
    serie = [v for v in tendencia.get("serie") or [] if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(serie) < 2 or serie[0] <= 0:
        return 1.0
    return max(CRECIMIENTO_MIN, min(CRECIMIENTO_MAX, serie[-1] / serie[0]))


def score(tendencia: dict, hoy: date) -> dict:
    """Componentes y score 0-100 de una tendencia, con las marcas del F-11.

    score = 100 × recencia × relevanciaSalud × exposicionIess × impactoPosible
              × confianzaFuente × crecimiento, redondeado a 1 decimal.
    """
    rec = recencia(tendencia, hoy)
    sector = str(tendencia.get("sector", "")).strip().lower()
    relevancia = (float(tendencia.get("relevancia", 0)) / 5) * (1.0 if sector == "salud" else RELEVANCIA_NO_SALUD)
    exposicion = float(tendencia.get("exposicion", 0) or 0) / 5
    impacto = float(tendencia.get("impacto", 0) or 0) / 5
    confianza = CONFIANZA_FUENTE.get(str(tendencia.get("fuente", "")), 0.0)
    crece_factor = crecimiento(tendencia)
    total = round(100 * rec * relevancia * exposicion * impacto * confianza * crece_factor, 1)
    dias = None
    fecha = _como_fecha(tendencia.get("fecha"))
    if fecha is not None:
        dias = (hoy - fecha).days
    return {
        "score": total,
        "recencia": rec,
        "relevanciaSalud": relevancia,
        "exposicionIess": exposicion,
        "impactoPosible": impacto,
        "confianzaFuente": confianza,
        "crecimiento": crece_factor,
        # marcas F-11: crece, es reciente y viene de fuentes confiables
        "crece": bool(serie_crece(tendencia)),
        "reciente": dias is not None and dias >= 0 and dias <= UMBRAL_RECIENTE_DIAS,
        "fuenteConfiable": confianza >= UMBRAL_CONFIABLE,
    }


def serie_crece(tendencia: dict) -> bool:
    """True si la serie termina por encima de donde empezó."""
    serie = [v for v in tendencia.get("serie") or [] if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return len(serie) >= 2 and serie[-1] > serie[0]


def evaluar(tendencias: list[dict], hoy: date | None = None) -> list[dict]:
    """Copia de cada tendencia con sus campos originales + score y marcas, ordenado de mayor a menor.

    Orden total determinista: score descendente y, en empate, id ascendente.
    """
    hoy = hoy or date.today()
    salida = [{**t, **score(t, hoy)} for t in tendencias]
    salida.sort(key=lambda t: (-t["score"], str(t.get("id", ""))))
    return salida
