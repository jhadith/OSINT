"""Scoring dinámico de ThreatPulse (T7, S6c): la pantalla Tendencias.tsx sigue leyendo
los mismos campos y el backend añade por tendencia un score numérico y sus marcas
(crece / reciente / fuente confiable), todo local y sin red.

Correr desde backend/:  pytest -q tests/test_threatpulse.py
"""
from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

from app import threatpulse

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO = RAIZ / "backend" / "app" / "fijos" / "tendencias.json"
HOY = date(2026, 11, 25)

# Campos que web/src/pages/Tendencias.tsx (vía api/types.ts) lee hoy: no se quitan ni renombran.
CAMPOS_PANTALLA = ("id", "titulo", "fuente", "fecha", "relevancia", "exposicion", "impacto",
                   "tecnicas", "resumen", "serie", "exposicionLocal")


def _feed() -> dict:
    return json.loads(ARCHIVO.read_text(encoding="utf-8"))


def _base(**campos) -> dict:
    t = {"id": "T-99", "titulo": "Tendencia de prueba", "fuente": "CISA", "fecha": "2026-11-20",
         "sector": "salud", "relevancia": 4, "exposicion": 4, "impacto": 4, "tecnicas": ["T1566"],
         "resumen": "Prueba", "serie": [1, 2, 3, 4], "exposicionLocal": "Ninguno"}
    t.update(campos)
    return t


def test_cada_tendencia_recibe_score_numerico():
    """(a) Cada tendencia del feed real sale con un score numérico 0-100."""
    salida = threatpulse.evaluar(_feed()["tendencias"], hoy=HOY)
    assert len(salida) == len(_feed()["tendencias"])
    for t in salida:
        s = t["score"]
        assert isinstance(s, (int, float)) and not isinstance(s, bool), (t["id"], s)
        assert 0.0 <= s <= 100.0, (t["id"], s)
        for comp in ("recencia", "relevanciaSalud", "exposicionIess", "impactoPosible", "confianzaFuente"):
            assert isinstance(t[comp], (int, float)) and not isinstance(t[comp], bool), (t["id"], comp)


def test_score_baja_con_fecha_mas_antigua():
    """(a) recencia/fecha: una tendencia vieja puntúa menos que la misma reciente."""
    nuevo = threatpulse.score(_base(fecha="2026-11-24"), hoy=HOY)
    viejo = threatpulse.score(_base(fecha="2024-01-01"), hoy=HOY)
    assert nuevo["score"] > viejo["score"]
    assert nuevo["recencia"] > viejo["recencia"]
    assert nuevo["reciente"] is True and viejo["reciente"] is False
    # fecha ausente o inválida → score 0, no crashea
    assert threatpulse.score(_base(fecha="no-es-fecha"), hoy=HOY)["score"] == 0.0


def test_score_depende_de_la_fuente_confiable():
    """(a) fuente: una fuente confiable puntúa más que una desconocida."""
    cisa = threatpulse.score(_base(fuente="CISA"), hoy=HOY)
    desconocida = threatpulse.score(_base(fuente="Foro anónimo sin verificar"), hoy=HOY)
    assert cisa["score"] > desconocida["score"]
    assert cisa["fuenteConfiable"] is True and desconocida["fuenteConfiable"] is False


def test_score_prefiere_el_sector_salud():
    """(a) sector salud: la relevancia para salud eleva el score de lo demás."""
    salud = threatpulse.score(_base(sector="salud"), hoy=HOY)
    banca = threatpulse.score(_base(sector="finanzas"), hoy=HOY)
    sin_sector = threatpulse.score(_base(sector=""), hoy=HOY)
    assert salud["score"] > banca["score"] == sin_sector["score"]
    assert salud["relevanciaSalud"] > banca["relevanciaSalud"]


def test_score_distingue_una_serie_que_crece():
    """F-11: la amenaza que crece se marca y puntúa más que la que cae."""
    crece = threatpulse.score(_base(serie=[1, 2, 3, 8]), hoy=HOY)
    cae = threatpulse.score(_base(serie=[8, 3, 2, 1]), hoy=HOY)
    assert crece["score"] > cae["score"]
    assert crece["crece"] is True and cae["crece"] is False


def test_ordena_de_mayor_a_menor_score():
    """(b) El resultado sale ordenado de mayor a menor score."""
    vieja = _base(id="T-OLD", fecha="2024-01-01")
    nueva = _base(id="T-NEW", fecha="2026-11-24")
    salida = threatpulse.evaluar([vieja, nueva], hoy=HOY)
    assert [t["id"] for t in salida] == ["T-NEW", "T-OLD"]
    scores = [t["score"] for t in threatpulse.evaluar(_feed()["tendencias"], hoy=HOY)]
    assert scores == sorted(scores, reverse=True)


def test_sin_red():
    """(c) El módulo de scoring no importa nada de red (httpx, requests, socket...)."""
    src = (RAIZ / "backend" / "app" / "threatpulse.py").read_text(encoding="utf-8")
    prohibidos = {"httpx", "requests", "urllib", "socket", "http", "aiohttp", "ftplib", "telnetlib", "ssl"}
    encontrados = set()
    for nodo in ast.walk(ast.parse(src)):
        if isinstance(nodo, ast.Import):
            nombres = [a.name.split(".")[0] for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom):
            nombres = [nodo.module.split(".")[0]] if nodo.module else []
        else:
            continue
        encontrados |= set(nombres) & prohibidos
    assert not encontrados, f"imports de red en threatpulse.py: {encontrados}"


def test_contrato_de_la_pantalla_tendencias_tsx(tmp_path, monkeypatch):
    """(d) El contrato que consume Tendencias.tsx queda intacto; solo se añaden campos.

    Con caché OSINT vacía (estado aislado en tmp_path) la respuesta es idéntica a la original:
    el test no depende de si alguien pulsó «Actualizar desde fuentes» en su máquina."""
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    feed = _feed()
    assert set(feed) == {"nota", "tendencias"}
    salida = threatpulse.evaluar(feed["tendencias"], hoy=HOY)
    assert {t["id"] for t in salida} == {t["id"] for t in feed["tendencias"]}
    por_id = {t["id"]: t for t in salida}
    for orig in feed["tendencias"]:
        t = por_id[orig["id"]]
        for campo in CAMPOS_PANTALLA:
            assert t[campo] == orig[campo], (orig["id"], campo)
    # y el endpoint real conserva el contrato, la nota y el orden
    from app.main import tendencias as endpoint
    r = endpoint(None)
    assert r["nota"] == feed["nota"]
    assert len(r["tendencias"]) == len(feed["tendencias"])
    assert all(set(CAMPOS_PANTALLA) <= set(t) for t in r["tendencias"])
    scores = [t["score"] for t in r["tendencias"]]
    assert scores == sorted(scores, reverse=True)
