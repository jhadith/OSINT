"""Productos de difusión nuevos (S10/T12): tablas planas para Power BI y export del grafo para Maltego CE.

Se prueban las funciones generadoras con fixtures pequeños, sin correr el pipeline completo.
Correr desde motor/:  pytest -q tests/test_consola_exportes.py
"""
from __future__ import annotations

import csv
import io

from motor import consola
from motor.salida import Seudonimos

RAW_USUARIO = "carlos.mena"
RAW_NOMBRE = "MENA SALAZAR CARLOS ANDRES"

# Encabezados fijos: el tablero de Power BI y sus consultas dependen de estos nombres.
ESPERADAS = {
    "alertas.csv": ["id", "caso", "regla", "titulo", "gravedad", "puntaje", "probabilidad", "impacto", "fuente",
                    "inicio", "fin", "ip_origen", "cuenta", "usuario_firewall", "persona",
                    "eventos_firewall", "eventos_sistema_medico", "riesgo", "desfase_reloj_h"],
    "casos.csv": ["id", "titulo", "tipo", "gravedad", "inicio", "duracion", "ipOrigen", "cuenta", "seudonimo",
                  "protocolo", "tecnicas", "riesgos", "detectadoPor", "estado"],
    "tendencias.csv": ["ts", "puntuacion", "fallidos", "ssh", "transferencias"],
    "indicadores.csv": ["nombre", "valor", "refMin", "refMax", "unidad", "nota"],
    "pilares.csv": ["pilar", "riesgo", "evidencia", "casos"],
    "resumen.csv": ["periodo", "registrosAnalizados", "registrosFirewall", "registrosSistemaMedico",
                    "minutosProcesamiento", "usuariosFirewall", "cuentasSistemaMedico",
                    "cuentasSospechosas", "controlesConBrecha"],
}


def _resumen() -> dict:
    return {
        "periodo": "Octubre 2026", "registrosAnalizados": 1234, "registrosFirewall": 700,
        "registrosSistemaMedico": 534, "minutosProcesamiento": 1.5, "usuariosFirewall": 42,
        "cuentasSistemaMedico": 17, "cuentasSospechosas": 2, "controlesConBrecha": 0,
        "indicadores": [{"nombre": "Accesos fallidos por hora (pico)", "valor": 12.0, "refMin": 0.0,
                         "refMax": 10.0, "unidad": "/h", "nota": "10/10 08:00"}],
        "pilares": [{"pilar": "Confidencialidad", "riesgo": "Historias clínicas vistas sin permiso",
                     "evidencia": "C1 fuerza bruta", "casos": ["C1"]}],
    }


def _caso(seud) -> dict:
    return {"id": "C1", "titulo": "Fuerza bruta", "tipo": "Fuerza bruta por SSH", "gravedad": "critica",
            "inicio": "2026-10-10T00:00:00", "duracion": "5 min", "ipOrigen": "10.10.100.11", "cuenta": "GEN0000021",
            "seudonimo": seud(RAW_NOMBRE, "P"), "protocolo": "SSH/22", "estado": "pendiente",
            "tecnicas": [{"id": "T1110", "nombre": "Fuerza bruta"}], "riesgos": ["R4"],
            "detectadoPor": ["Reglas", "Machine learning"]}


def _alerta(seud) -> dict:
    return {"id": "A-01234567", "caso": "Caso 1", "regla": "rafaga_ssh", "titulo": "Fuerza bruta",
            "gravedad": "Crítica", "puntaje": 25, "probabilidad": 5, "impacto": 5, "fuente": "correlacion",
            "inicio": "2026-10-10 00:00:00", "fin": "2026-10-10 00:05:00", "ip_origen": "10.10.100.11",
            "cuenta": "GEN0000021", "usuario_firewall": seud(RAW_USUARIO, "U"), "persona": seud(RAW_NOMBRE, "P"),
            "eventos_firewall": 2000, "eventos_sistema_medico": 2000, "riesgo": "R4", "desfase_reloj_h": 0}


def _serie() -> list[dict]:
    return [{"ts": "2026-10-10T00:00:00", "puntuacion": 0.9, "fallidos": 12, "ssh": 3, "transferencias": 0}]


def _grafo() -> dict:
    return {
        "nodos": [
            {"id": "srv", "tipo": "servidor", "etiqueta": "10.10.100.30", "detalle": "Servidor del sistema médico",
             "casoId": None, "gravedad": None},
            {"id": "ip-10.10.100.11", "tipo": "ip", "etiqueta": "10.10.100.11", "detalle": "Fuerza bruta por SSH",
             "casoId": "C1", "gravedad": "critica"},
            {"id": "cta-GEN0000021", "tipo": "cuenta", "etiqueta": "GEN0000021", "detalle": "Fuerza bruta",
             "casoId": "C1", "gravedad": "critica", "personas": 3},
        ],
        "aristas": [
            {"origen": "ip-10.10.100.11", "destino": "srv", "etiqueta": "SSH/22", "eventos": 42},
            {"origen": "ip-10.10.100.11", "destino": "cta-GEN0000021", "etiqueta": "usa", "eventos": 10},
        ],
    }


def test_tablas_powerbi_existen_con_encabezados_estables(tmp_path):
    seud = Seudonimos(tmp_path / "restringido")
    tablas = consola.tablas_powerbi(_resumen(), [_caso(seud)], _serie(), [_alerta(seud)])
    assert set(tablas) == set(ESPERADAS) == set(consola.TABLAS_POWERBI)
    consola.escribir_powerbi(tmp_path, tablas)
    for nombre, columnas in ESPERADAS.items():
        f = tmp_path / "powerbi" / nombre
        assert f.is_file(), nombre
        with open(f, encoding="utf-8", newline="") as fh:
            filas = list(csv.reader(fh))
        assert filas[0] == columnas, nombre
        assert len(filas) >= 2, nombre          # cada tabla trae al menos una fila de datos


def test_powerbi_no_cruza_con_la_tabla_de_reidentificacion(tmp_path):
    seud = Seudonimos(tmp_path / "restringido")
    caso, alerta = _caso(seud), _alerta(seud)
    seud.guardar()
    consola.escribir_powerbi(tmp_path, consola.tablas_powerbi(_resumen(), [caso], _serie(), [alerta]))
    with open(tmp_path / "restringido" / "tabla_reidentificacion.csv", encoding="utf-8", newline="") as f:
        reales = [r["valor_real"] for r in csv.DictReader(f)]
    assert RAW_USUARIO in reales and RAW_NOMBRE in reales        # control: la tabla sí tiene valores reales
    texto = "".join(f.read_text(encoding="utf-8") for f in sorted((tmp_path / "powerbi").glob("*.csv")))
    assert caso["seudonimo"] in texto and alerta["persona"] in texto   # los seudónimos sí viajan
    for v in reales:
        assert v not in texto, v


def test_grafo_maltego_formato_y_coherencia_con_el_grafo():
    g = _grafo()
    filas = list(csv.reader(io.StringIO(consola.maltego(g))))
    assert filas[0] == ["EntityType", "Property Name", "Value"]
    assert all(len(f) == 3 for f in filas)
    # entidades primero y relaciones después, separadas
    i = next(k for k, f in enumerate(filas) if f[0] == "maltego.Link")
    assert all(f[0] != "maltego.Link" for f in filas[1:i])
    assert all(f[0] == "maltego.Link" for f in filas[i:])
    entidades, enlaces = filas[1:i], filas[i:]
    assert {f[0] for f in entidades} <= {"maltego.IPv4Address", "maltego.Alias"}
    valores = {f[2] for f in entidades if f[1] in ("ipaddress", "alias")}
    assert valores == {"10.10.100.30", "10.10.100.11", "GEN0000021"}
    assert ["caseId", "C1"] in [f[1:] for f in entidades]
    assert ["gravedad", "critica"] in [f[1:] for f in entidades]
    desde = [f[2] for f in enlaces if f[1] == "link.from"]
    hasta = [f[2] for f in enlaces if f[1] == "link.to"]
    etiquetas = [f[2] for f in enlaces if f[1] == "link.label"]
    assert len(desde) == len(hasta) == len(etiquetas) == len(g["aristas"])
    assert desde == ["10.10.100.11", "10.10.100.11"] and hasta == ["10.10.100.30", "GEN0000021"]
    assert set(desde) | set(hasta) <= valores
