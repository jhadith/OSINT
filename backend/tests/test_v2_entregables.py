"""PDF con los 8 entregables, tablero con impacto en el negocio y tickets de reglas SOC → TI."""
import pytest

from .test_api import analista, con_analisis, entorno, ingresar  # noqa: F401  (fixtures compartidas)


def test_informe_pdf_ocho_puntos(entorno, analista, con_analisis):
    r = entorno.get("/api/exportes/informe-pdf", headers=analista)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert entorno.get("/api/exportes/informe-pdf", headers=ingresar(entorno, "salud")).status_code == 403


def test_ticket_del_soc_llega_a_ti(entorno, analista, con_analisis):
    t = entorno.post("/api/tickets", headers=analista, json={
        "tipo": "ajustar", "regla": "SIG-01 Fuerza bruta", "titulo": "Bajar umbral de fuerza bruta",
        "descripcion": "El caso C1 muestra miles de intentos en pocos minutos.", "prioridad": "alta", "caso": "C1"})
    assert t.status_code == 200, t.text
    codigo = t.json()["codigo"]
    ti = ingresar(entorno, "ti")
    lista = entorno.get("/api/tickets", headers=ti).json()
    assert any(x["codigo"] == codigo and x["estado"] == "abierto" for x in lista["tickets"])
    # el analista no puede aplicar; TI sí
    assert entorno.post(f"/api/tickets/{codigo}/gestion", headers=analista,
                        json={"estado": "aplicado", "respuesta": "Aplicado en el SIEM"}).status_code == 403
    r = entorno.post(f"/api/tickets/{codigo}/gestion", headers=ti,
                     json={"estado": "aplicado", "respuesta": "Umbral ajustado y probado en el SIEM"})
    assert r.json()["estado"] == "aplicado"
    assert entorno.get("/api/tickets", headers=ingresar(entorno, "salud")).status_code == 403


def test_tablero_conecta_amenazas_con_el_negocio(entorno, analista, con_analisis):
    t = entorno.get("/api/tablero", headers=analista).json()
    assert 0 <= t["indice"] <= 100
    assert {x["id"] for x in t["negocio"]["dimensiones"]} == {"atencion", "datos", "citas", "confianza", "costos"}
    origenes = {a["origen"] for a in t["amenazas"]}
    assert {"Casos", "Citas del chatbot", "Denuncias"} <= origenes
    assert all(a["riesgos"] and isinstance(a["dimensiones"], list) for a in t["amenazas"])
    assert t["baseDatos"]["motor"] in ("sqlite", "postgresql")
    assert entorno.get("/api/tablero", headers=ingresar(entorno, "salud")).status_code == 403


def test_descartar_baja_el_impacto_en_el_negocio(entorno, analista, con_analisis):
    antes = {d["id"]: d for d in entorno.get("/api/tablero", headers=analista).json()["negocio"]["dimensiones"]}
    entorno.post("/api/casos/C3/decision", headers=analista,
                 json={"estado": "descartado", "motivo": "Transferencia autorizada de respaldo"})
    despues = {d["id"]: d for d in entorno.get("/api/tablero", headers=analista).json()["negocio"]["dimensiones"]}
    assert despues["datos"]["exposicion"] <= antes["datos"]["exposicion"]


def test_gerencial_explica_impacto_en_el_negocio(entorno, analista, con_analisis):
    import io
    PdfReader = pytest.importorskip("pypdf").PdfReader
    r = entorno.get("/api/exportes/gerencial", headers=analista)
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Cómo afecta al negocio" in texto and "Decisión recomendada" in texto
