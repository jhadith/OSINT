"""CLI del pipeline (T8/S6d): punto de entrada `python -m motor`.

Correr desde motor/:  pytest -q tests/test_cli.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from motor import pipeline

# Carpeta motor/ que contiene el paquete motor/motor/ (la CLI se lanza desde ahí, nunca desde la raíz del repo).
MOTOR = Path(__file__).resolve().parents[1]


def test_ayuda_python_m_motor() -> None:
    """`python -m motor --help` termina con exit 0 y anuncia las opciones del pipeline."""
    proc = subprocess.run([sys.executable, "-m", "motor", "--help"],
                          cwd=MOTOR, capture_output=True, text=True, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    for opcion in ("--fw", "--med", "--salidas", "--sin-ml"):
        assert opcion in proc.stdout, proc.stdout


def test_fw_inexistente_sale_con_ruta(monkeypatch, tmp_path: Path) -> None:
    """Un --fw que no existe termina con SystemExit y un mensaje claro que nombra la ruta exacta."""
    ruta = tmp_path / "no_existe.csv"
    monkeypatch.setattr(sys, "argv", ["motor", "--fw", str(ruta)])
    with pytest.raises(SystemExit) as exc:
        pipeline.main()
    assert str(ruta) in str(exc.value)
    assert "No existe" in str(exc.value)
