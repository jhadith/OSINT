"""Wiring de exportes (S14/T16) y de listas de comparación (S15/T17b) contra la API real.

Bloque 1: GET /api/exportes/gerencial y /api/exportes/presentacion devuelven el HTML
autocontenido (con `<svg` y @media print) como attachment, alimentado por el análisis
activo, con permisos distintos (estrategico / tecnico).

Bloque 2: CRUD completo de indicadores de lista vía API, bandeja de solicitudes con
aprobar/rechazar siempre con motivo (>=10), 403 sin el permiso apropiado y bitácora
registrada para cada cambio.

Reutiliza el entorno de tests/test_api.py (mismo análisis sintético, mismo patrón que
test_exportes_extra.py) para no reimplementar el montaje del estado.
Correr desde backend/:  pytest -q tests/test_wiring_exportes_listas.py
"""
from __future__ import annotations

from .test_api import analista, con_analisis, entorno, ingresar  # noqa: F401 - fixtures de prueba


# ---------------------------------------------------------------------------
# Bloque 1 · exportes HTML (S14/T16)
# ---------------------------------------------------------------------------
def test_informe_gerencial_es_pdf(entorno, analista, con_analisis):
    r = entorno.get("/api/exportes/gerencial", headers=analista)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf"), r.headers["content-type"]
    assert 'attachment; filename="informe_gerencial.pdf"' in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


def test_presentacion_es_html_con_svg_y_attachment(entorno, analista, con_analisis):
    r = entorno.get("/api/exportes/presentacion", headers=analista)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]
    assert 'attachment; filename="presentacion_soc.html"' in r.headers["content-disposition"]
    assert r.text.startswith("<!DOCTYPE html>")
    assert "<svg" in r.text, "la presentación lleva diagramas SVG"
    for seccion in ("Informe de presentación", "Resumen ejecutivo", "Evidencia condensada",
                    "Matriz de riesgos y asignación actual", "Controles ISO 27002", "Anexo técnico"):
        assert seccion in r.text, f"presentación sin la sección {seccion!r}"
    assert "Fuerza bruta" in r.text


def test_permisos_de_los_informes(entorno, analista, con_analisis):
    salud = ingresar(entorno, "salud")
    jefe = ingresar(entorno, "jefe")
    for ruta in ("/api/exportes/gerencial", "/api/exportes/presentacion"):
        assert entorno.get(ruta).status_code == 401, ruta
        assert entorno.get(ruta, headers=salud).status_code == 403, ruta
    # gerencial: permiso estrategico (lo baja la jefatura); presentación: tecnico (el experto)
    assert entorno.get("/api/exportes/gerencial", headers=jefe).status_code == 200
    assert entorno.get("/api/exportes/presentacion", headers=jefe).status_code == 403


# ---------------------------------------------------------------------------
# Bloque 2 · listas de comparación (S15/T17b)
# ---------------------------------------------------------------------------
def test_listas_crud_completo_de_indicadores(entorno, analista):
    # alta con normalización: esquema/mayúsculas fuera y la lista blanca vive en el host
    r = entorno.post("/api/listas/indicadores", headers=analista,
                     json={"tipo": "blanca", "valor": "https://Portal.Salud.Gob.ec/rutas/internas",
                           "etiqueta": "Alta desde la consola del SOC"})
    assert r.status_code == 200, r.text
    ind = r.json()
    assert ind["tipo"] == "blanca" and ind["valor"] == "portal.salud.gob.ec" and ind["activo"] == 1

    # el listado lo incluye (y la semilla de fijos/listas.json sigue visible)
    filas = entorno.get("/api/listas/indicadores", headers=analista).json()
    assert any(f["id"] == ind["id"] for f in filas)
    assert any(f["valor"] == "gob.ec" for f in filas), "la semilla inicial debe seguir en el catálogo"

    # baja: desaparece del listado activo
    d = entorno.delete(f"/api/listas/indicadores/{ind['id']}", headers=analista)
    assert d.status_code == 200 and d.json()["activo"] == 0
    filas = entorno.get("/api/listas/indicadores", headers=analista).json()
    assert all(f["id"] != ind["id"] for f in filas)

    # alta del mismo valor lo reactiva (alta/baja completos, sin duplicados)
    r2 = entorno.post("/api/listas/indicadores", headers=analista,
                      json={"tipo": "blanca", "valor": "portal.salud.gob.ec", "etiqueta": "Reactivada"})
    assert r2.status_code == 200 and r2.json()["id"] == ind["id"] and r2.json()["activo"] == 1

    # baja de un id inexistente → 404
    assert entorno.delete("/api/listas/indicadores/999999", headers=analista).status_code == 404

    # entradas rechazadas no modifican el catálogo
    antes = len(entorno.get("/api/listas/indicadores", headers=analista).json())
    assert entorno.post("/api/listas/indicadores", headers=analista,
                        json={"tipo": "roja", "valor": "x.ec", "etiqueta": ""}).status_code == 422
    assert entorno.post("/api/listas/indicadores", headers=analista,
                        json={"tipo": "negra", "valor": "valor con espacios", "etiqueta": ""}).status_code == 400
    assert len(entorno.get("/api/listas/indicadores", headers=analista).json()) == antes


def test_listas_solicitudes_se_resuelven_con_motivo(entorno, analista):
    # alta de solicitud: queda PENDIENTE y todavía no crea el indicador
    r = entorno.post("/api/listas/solicitudes", headers=analista,
                     json={"tipo": "negra", "valor": "https://PHISH-Banco.top/login",
                           "justificacion": "Dominio reportado en denuncia de phishing", "fuente": "denuncia"})
    assert r.status_code == 200, r.text
    sol = r.json()
    assert sol["estado"] == "PENDIENTE" and sol["valor"] == "phish-banco.top/login"
    pend = entorno.get("/api/listas/solicitudes?estado=PENDIENTE", headers=analista).json()
    assert any(s["id"] == sol["id"] for s in pend)
    assert all(f["valor"] != "phish-banco.top/login"
               for f in entorno.get("/api/listas/indicadores", headers=analista).json())

    # motivo corto → 422 y la solicitud sigue PENDIENTE (nada cambia)
    assert entorno.post(f"/api/listas/solicitudes/{sol['id']}/resolver", headers=analista,
                        json={"aprobar": True, "motivo": "corto"}).status_code == 422
    pend = entorno.get("/api/listas/solicitudes?estado=PENDIENTE", headers=analista).json()
    assert any(s["id"] == sol["id"] for s in pend), "un motivo rechazado no resuelve la solicitud"

    # aprobar con motivo ≥10 activa el indicador en la lista negra
    r2 = entorno.post(f"/api/listas/solicitudes/{sol['id']}/resolver", headers=analista,
                      json={"aprobar": True, "motivo": "Confirmado por el SOC en la revisión semanal"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["estado"] == "APROBADA"
    assert r2.json()["resolucion"].startswith("Confirmado")
    assert any(f["valor"] == "phish-banco.top/login"
               for f in entorno.get("/api/listas/indicadores", headers=analista).json())

    # una solicitud ya resuelta no se vuelve a resolver → 400
    assert entorno.post(f"/api/listas/solicitudes/{sol['id']}/resolver", headers=analista,
                        json={"aprobar": False, "motivo": "Segunda resolución sin efecto"}).status_code == 400

    # rechazar: queda RECHAZADA y NO activa ningún indicador
    r3 = entorno.post("/api/listas/solicitudes", headers=analista,
                      json={"tipo": "blanca", "valor": "otro-hospital.gob.ec",
                            "justificacion": "Lo pidió el área médica"})
    assert r3.status_code == 200, r3.text
    id2 = r3.json()["id"]
    r4 = entorno.post(f"/api/listas/solicitudes/{id2}/resolver", headers=analista,
                      json={"aprobar": False, "motivo": "Sin evidencia suficiente por ahora"})
    assert r4.status_code == 200 and r4.json()["estado"] == "RECHAZADA"
    assert all(f["valor"] != "otro-hospital.gob.ec"
               for f in entorno.get("/api/listas/indicadores", headers=analista).json())

    # sin sesión → 401
    assert entorno.get("/api/listas/solicitudes").status_code == 401
    assert entorno.post("/api/listas/solicitudes", json={}).status_code == 401


def test_listas_requieren_el_permiso_de_gestion(entorno):
    salud = ingresar(entorno, "salud")
    jefe = ingresar(entorno, "jefe")
    ti = ingresar(entorno, "ti")
    for ruta in ("/api/listas/indicadores", "/api/listas/solicitudes"):
        assert entorno.get(ruta).status_code == 401, ruta
        assert entorno.get(ruta, headers=salud).status_code == 403, ruta
    # el rol TI es quien gestiona las listas: su permiso es «tecnico»
    assert entorno.get("/api/listas/indicadores", headers=ti).status_code == 200
    assert entorno.post("/api/listas/indicadores", headers=ti,
                        json={"tipo": "blanca", "valor": "gestion-ti.gob.ec",
                              "etiqueta": "Alta del rol TI"}).status_code == 200
    assert entorno.post("/api/listas/indicadores", headers=salud,
                        json={"tipo": "blanca", "valor": "sin-permiso.gob.ec", "etiqueta": ""}).status_code == 403
    # la jefatura no tiene «tecnico»: no gestiona listas (queda registrado para el reporte)
    assert entorno.get("/api/listas/indicadores", headers=jefe).status_code == 403


def test_listas_dejan_bitacora_en_cada_cambio(entorno, analista):
    r = entorno.post("/api/listas/indicadores", headers=analista,
                     json={"tipo": "negra", "valor": "bitacora-prueba.xyz", "etiqueta": "Prueba"})
    assert r.status_code == 200, r.text
    id_ind = r.json()["id"]
    assert entorno.delete(f"/api/listas/indicadores/{id_ind}", headers=analista).status_code == 200
    sol = entorno.post("/api/listas/solicitudes", headers=analista,
                       json={"tipo": "blanca", "valor": "solicitud-bitacora.gob.ec",
                             "justificacion": "Solicitud para comprobar la bitácora"}).json()
    assert entorno.post(f"/api/listas/solicitudes/{sol['id']}/resolver", headers=analista,
                        json={"aprobar": False,
                              "motivo": "Rechazo de prueba con motivo suficiente"}).status_code == 200

    jefe = ingresar(entorno, "jefe")
    entradas = entorno.get("/api/bitacora", headers=jefe).json()
    acciones = {b["accion"] for b in entradas}
    assert "Indicador de lista negra añadido" in acciones
    assert "Indicador de lista negra quitado" in acciones
    assert "Solicitud de lista nueva" in acciones
    assert "Solicitud de lista rechazada" in acciones
    motivos = {b["detalle"] for b in entradas}
    assert "Rechazo de prueba con motivo suficiente" in motivos, "el motivo debe quedar en la bitácora"
