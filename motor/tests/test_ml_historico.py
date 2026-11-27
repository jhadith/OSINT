"""Histórico acumulativo de ventanas y reentrenamiento del Isolation Forest (ml.acumular / reentrenar)."""
import numpy as np
import pandas as pd
import pytest

from motor import config, ml


def _ventanas(n=60, desde=0, anomala=False):
    rng = np.random.default_rng(7 + desde)
    idx = pd.MultiIndex.from_tuples([(f"U{i % 6}", (desde + i) * 3600) for i in range(n)], names=["u", "v"])
    f = pd.DataFrame({"eventos": rng.integers(5, 15, n), "puertos": rng.integers(1, 3, n),
                      "pct_negado": rng.uniform(0, 0.1, n)}, index=idx)
    if anomala:
        f.iloc[0] = [5000, 40, 0.99]
    return f


def test_ruta_por_defecto_y_fuente_desconocida(tmp_path):
    assert ml.ruta_historico("firewall") == config.DATOS / "historico_firewall.csv"
    assert ml.ruta_historico("sistema_medico", tmp_path / "h.csv") == tmp_path / "h.csv"
    with pytest.raises(ValueError, match="fuente desconocida"):
        ml.ruta_historico("correo")


def test_acumular_es_idempotente(tmp_path):
    ruta = tmp_path / "hist" / "fw.csv"
    ml.acumular(_ventanas(), "firewall", ruta)
    ml.acumular(_ventanas(), "firewall", ruta)                     # misma corrida: no duplica
    assert len(pd.read_csv(ruta)) == 60
    ml.acumular(_ventanas(desde=60), "firewall", ruta)             # ventanas nuevas: se agregan
    df = ml.leer_historico("firewall", ruta)
    assert len(df) == 120 and list(df.columns[:2]) == ["entidad", "ventana"]


def test_leer_historico_sin_datos(tmp_path):
    with pytest.raises(ValueError, match="No hay histórico"):
        ml.leer_historico("firewall", tmp_path / "no.csv")
    vacio = tmp_path / "vacio.csv"
    vacio.write_text("entidad,ventana,eventos\n")
    with pytest.raises(ValueError, match="vacío"):
        ml.leer_historico("firewall", vacio)


def test_reentrenar_sin_variables(tmp_path):
    ruta = tmp_path / "solo_ids.csv"
    pd.DataFrame({"entidad": ["U1"], "ventana": [0]}).to_csv(ruta, index=False)
    with pytest.raises(ValueError, match="no tiene variables"):
        ml.reentrenar("firewall", ruta)


def test_reentrenar_es_determinista_y_puntua_la_anomalia_mas_alto(tmp_path):
    ruta = tmp_path / "fw.csv"
    ml.acumular(_ventanas(200), "firewall", ruta)
    m1 = ml.reentrenar("firewall", ruta)
    m2 = ml.reentrenar("firewall", ruta)
    assert m1.ventanas == 200 and m1.semilla == config.SEMILLA
    nuevas = _ventanas(30, desde=500, anomala=True)
    p1, p2 = ml.puntuar_modelo(m1, nuevas), ml.puntuar_modelo(m2, nuevas)
    assert np.allclose(p1, p2)                                       # misma semilla y datos: mismo modelo
    assert p1[0] == pytest.approx(100) and p1.argmax() == 0         # la ventana anómala queda arriba


def test_puntuar_con_variables_desconocidas(tmp_path):
    ruta = tmp_path / "fw.csv"
    ml.acumular(_ventanas(), "firewall", ruta)
    m = ml.reentrenar("firewall", ruta)
    with pytest.raises(ValueError, match="no conoce"):
        ml.puntuar_modelo(m, _ventanas().drop(columns=["puertos"]))


def test_puesto_sin_ranking_o_sin_coincidencia():
    assert ml.puesto(None, "u", "U1", 0, 3600) == {}
    r = ml.Ranking(tabla=pd.DataFrame({"u": ["U1"], "ventana": [0], "puesto": [1], "puntaje": [99.0],
                                       "por_que": ["mucho tráfico"]}), total=10, entidades=3)
    assert ml.puesto(r, "u", "U1", 100, 3600) == {"puesto": 1, "de": 10, "puntaje": 99.0, "por_que": "mucho tráfico"}
    assert ml.puesto(r, "u", "U9", 100, 3600) == {}
