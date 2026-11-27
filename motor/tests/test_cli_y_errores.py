"""Línea de comandos del motor, alertas que solo ve el modelo y tolerancia a fallos de la salida de consola."""
import json
import sys

import pytest

from motor import config, consola, pipeline
from tests import generador as gen
from tests import generador_citas as gen_citas


def test_cli_rechaza_archivos_que_no_existen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["motor", "--fw", str(tmp_path / "no.csv"), "--med", str(tmp_path / "no.csv")])
    with pytest.raises(SystemExit, match="No existe"):
        pipeline.main()
    fw, med = gen.generar(tmp_path / "d", 2000, 2000)
    monkeypatch.setattr(sys, "argv", ["motor", "--fw", str(fw), "--med", str(med), "--citas", str(tmp_path / "no.csv")])
    with pytest.raises(SystemExit, match="No existe"):
        pipeline.main()


def test_cli_completo_con_citas_reportes_y_alertas_solo_ml(tmp_path, monkeypatch, capsys):
    """Corrida por línea de comandos con el módulo de citas, denuncias previas y el umbral de ML al mínimo:
    aparecen alertas que ninguna regla explica, y si la consola web falla las salidas principales igual quedan."""
    fw, med = gen.generar(tmp_path / "d", 60_000, 50_000)
    citas = gen_citas.generar(tmp_path / "d" / "agendamiento.csv", afiliados=600)
    reportes = tmp_path / "reportes.txt"
    reportes.write_text("contacto-de-prueba\n\n", encoding="utf-8")

    def consola_rota(*a, **k):
        raise RuntimeError("consola rota a propósito")
    monkeypatch.setattr(consola, "generar", consola_rota)
    monkeypatch.setattr(config, "ESTRICTO", False)
    monkeypatch.setattr(config, "ML_ALERTA_PUNTAJE", 0)
    salidas = tmp_path / "salidas"
    monkeypatch.setattr(sys, "argv", ["motor", "--fw", str(fw), "--med", str(med), "--salidas", str(salidas),
                                      "--restringido", str(tmp_path / "r"), "--citas", str(citas),
                                      "--reportes", str(reportes)])
    pipeline.main()

    alertas = json.loads((salidas / "alertas.json").read_text(encoding="utf-8"))
    assert {a["fuente"] for a in alertas if a["regla"].startswith("ml_")} >= {"firewall", "sistema_medico"}
    assert (salidas / "agendamiento.json").exists()
    assert (salidas / "resumen_motor.json").exists()
    assert "no se pudo generar salidas/consola" in capsys.readouterr().out


def test_en_modo_estricto_un_error_de_consola_detiene_el_motor(tmp_path, monkeypatch):
    fw, med = gen.generar(tmp_path / "d", 4000, 4000)

    def consola_rota(*a, **k):
        raise RuntimeError("consola rota a propósito")
    monkeypatch.setattr(consola, "generar", consola_rota)
    monkeypatch.setattr(config, "ESTRICTO", True)
    with pytest.raises(RuntimeError, match="consola rota"):
        pipeline.ejecutar(fw, med, tmp_path / "s", con_ml=False, restringido=tmp_path / "r")
