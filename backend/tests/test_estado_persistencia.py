"""Contrato público de app.estado tras pasar de JSONL a SQLite: mismas firmas, mismo orden, mismo resultado.

Correr desde backend/:  pytest -q
"""
from __future__ import annotations

from app import estado


def test_firmas_publicas_de_estado_conservan_el_contrato(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))

    # leer un stream vacío = [] (como con el archivo inexistente)
    assert estado.leer("decisiones") == []

    reg = {"clave": "AN-1:C3", "estado": "confirmado", "motivo": "x" * 12}
    assert estado.agregar("decisiones", reg) is reg         # devuelve el registro, como antes

    estado.agregar("decisiones", {"clave": "AN-1:C3", "estado": "descartado", "motivo": "y" * 12})
    assert [d["estado"] for d in estado.leer("decisiones")] == ["confirmado", "descartado"]   # orden de inserción
    assert estado.ultimo_por("decisiones", "clave")["AN-1:C3"]["estado"] == "descartado"      # gana la última

    # la bitácora conserva su id correlativo, sus campos, su orden y su formato de fecha
    b1 = estado.bitacora("ana", "SOC", "Ingreso a la consola", "consola", "Sesión de 8 horas")
    b2 = estado.bitacora("ti", "Equipo de TI", "Análisis iniciado", "AN-1", "fw y med")
    assert b1["id"] == "B-00001" and b2["id"] == "B-00002"
    assert list(b1) == ["id", "fecha", "actor", "rol", "accion", "objetivo", "detalle"]
    assert [b["id"] for b in estado.leer("bitacora")] == ["B-00001", "B-00002"]
    assert len(b1["fecha"]) == 19 and b1["fecha"][4] == "-" and b1["fecha"][10] == "T"

    assert estado.leer("telegram") == []
