"""Exportes nuevos de difusión (S10/T12): tablas Power BI en ZIP y grafo del análisis en CSV para Maltego CE.

Reutiliza el entorno de tests/test_api.py (mismo análisis sintético, mismo patrón que test_exportes) para no
correr el pipeline dos veces por módulo.
Correr desde backend/:  pytest -q tests/test_exportes_extra.py
"""
from __future__ import annotations

import io
import zipfile

from .test_api import analista, con_analisis, entorno, gen, ingresar  # noqa: F401 - son fixtures y datos de prueba

# Encabezados estables de todas las tablas del ZIP (las seis del motor + las tres del estado del backend).
CABECERAS = {
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
    "riesgos.csv": ["id", "nombre", "probabilidad", "impacto", "nivel", "tratamiento", "evidencia", "casos"],
    "controles.csv": ["id", "nombre", "hallazgo", "estado"],
    "decisiones.csv": ["casoId", "estado", "motivo", "analista", "fecha"],
}


def test_exporte_powerbi_es_un_libro_excel_con_las_tablas(entorno, analista, con_analisis):
    from openpyxl import load_workbook
    r = entorno.get("/api/exportes/powerbi", headers=analista)
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"
    assert 'attachment; filename="sentinel_powerbi.xlsx"' in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    hojas = {n.rsplit(".", 1)[0]: c for n, c in CABECERAS.items()}
    assert set(hojas) <= set(wb.sheetnames)
    texto = ""
    for hoja, columnas in hojas.items():
        ws = wb[hoja]
        filas = [[("" if v is None else str(v)) for v in f] for f in ws.iter_rows(values_only=True)]
        texto += str(filas)
        assert filas[0] == columnas, hoja
        assert ws.tables, f"la hoja {hoja} debe tener una tabla de Excel para Power BI"
    for usuario, nombre, _, _ in gen.ATACANTES.values():     # política de seudónimos: nada real en la difusión
        assert usuario not in texto and nombre not in texto
    assert "IESS" not in texto.upper()
    casos = [f[0] for f in wb["casos"].iter_rows(min_row=2, values_only=True)]
    assert casos == ["C1", "C2", "C3", "C4"]
    riesgos = {f[0] for f in wb["riesgos"].iter_rows(min_row=2, values_only=True)}
    assert riesgos >= {"R1", "R2", "R4"}


def test_exporte_maltego_es_un_grafo_mtgx_coherente(entorno, analista, con_analisis):
    import xml.etree.ElementTree as ET  # nosec B405 - XML generado por la propia API en la prueba
    g = entorno.get("/api/grafo", headers=analista).json()
    r = entorno.get("/api/exportes/maltego", headers=analista)
    assert r.status_code == 200, r.text
    assert 'attachment; filename="sentinel_maltego.mtgx"' in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"Version.properties", "Graphs/Graph1.graphml"} <= set(z.namelist())
    raiz = ET.fromstring(z.read("Graphs/Graph1.graphml"))  # nosec B314
    ns = {"g": "http://graphml.graphdrawing.org/xmlns", "mtg": "http://maltego.paterva.com/xml/mtgx"}
    nodos = raiz.findall(".//g:node", ns)
    aristas = raiz.findall(".//g:edge", ns)
    assert len(nodos) == len(g["nodos"]) and len(aristas) == len(g["aristas"])
    valores = {v.text for v in raiz.findall(".//mtg:MaltegoEntity/mtg:Properties/mtg:Property/mtg:Value", ns)}
    assert {n["etiqueta"] for n in g["nodos"]} <= valores
    texto = z.read("Graphs/Graph1.graphml").decode("utf-8")
    for usuario, nombre, _, _ in gen.ATACANTES.values():
        assert usuario not in texto and nombre not in texto


def test_permisos_de_los_nuevos_exportes(entorno):
    salud = ingresar(entorno, "salud")
    for ruta in ("/api/exportes/powerbi", "/api/exportes/maltego"):
        assert entorno.get(ruta).status_code == 401, ruta
        assert entorno.get(ruta, headers=salud).status_code == 403, ruta


def test_los_exportes_cti_siguen_iguales(entorno, analista, con_analisis):
    for tipo in ("stix", "misp", "sigma"):
        r = entorno.get(f"/api/exportes/{tipo}", headers=analista)
        assert r.status_code == 200, tipo
    assert entorno.get("/api/exportes/stix", headers=analista).headers["content-type"].startswith("application/json")
    assert entorno.get("/api/exportes/sigma", headers=analista).content[:2] == b"PK"
