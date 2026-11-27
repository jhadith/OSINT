"""Exportes gerencial y de presentación (S14/T16): dos plantillas HTML autocontenidas
con diagramas SVG, solo stdlib, sin recursos externos.

Genéricidad anti-hardcode (requisito central): DOS fixtures de dataset distintos —otras
fechas, IPs, cuentas y títulos— verifican que cada informe genera sin error, contiene los
valores de SU dataset y ningún literal del otro. Además: tolerancia a campos faltantes,
escape de HTML, prohibición de datos técnicos en el gerencial (MITRE/IPs), estructura
válida para html.parser, `<svg` y `@media print`.

Nada escribe en el repositorio y no hay red.

Correr desde backend/:  pytest -q tests/test_reportes.py
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from app import reportes

# ---------------------------------------------------------------------------
# Dataset A — "marzo": fechas, IPs, cuentas y títulos propios de este dataset.
# ---------------------------------------------------------------------------
DATOS_A = {
    "periodo": "2025-03-01 a 2025-03-31",
    "resumen": ("En marzo el laboratorio regional resistió una ráfaga de intentos nocturnos "
                "y una descarga de registros clínicos."),
    "kpis": {"alertas": {"critica": 3, "alta": 5, "media": 2, "baja": 1},
             "cuentas_a_revisar": 1483,
             "conexiones_inseguras": 4821},
    "casos": [
        {"titulo": "Ráfaga de accesos fallidos en el laboratorio regional",
         "fecha": "2025-03-04", "gravedad": "alta",
         "frase": "Alguien probó cientos de contraseñas en la madrugada.",
         "ipOrigen": "10.44.19.55", "cuenta": "terminal_laboratorio"},
        {"titulo": "Descarga nocturna de registros clínicos",
         "fecha": "2025-03-19", "gravedad": "critica",
         "frase": "Se extrajeron miles de registros mientras el hospital dormía.",
         "ipOrigen": "10.44.19.55", "cuenta": "terminal_laboratorio"},
        {"titulo": "Escaneo de servicios del servidor de archivo",
         "fecha": "2025-03-27", "gravedad": "media",
         "frase": "Revisaron puerta por puerta qué servicios estaban abiertos.",
         "ipOrigen": "10.44.19.61", "cuenta": "monitorizacion_cuenta"},
    ],
    "riesgos": [
        {"id": "R1", "nombre": "Acceso indebido a historias clínicas", "probabilidad": 4,
         "impacto": 5, "nivel": 20,
         "recomendacion": "Eliminar cuentas genéricas y exigir un solo uso por persona."},
        {"id": "R2", "nombre": "Fuga de información de salud", "probabilidad": 3,
         "impacto": 5, "nivel": 15,
         "recomendacion": "Restringir accesos remotos y cifrar las transferencias."},
        {"id": "R3", "nombre": "Detención de la atención por ransomware", "probabilidad": 2,
         "impacto": 5, "nivel": 10,
         "recomendacion": "Aislar la red hospitalaria y probar los respaldos cada mes."},
    ],
    "tendencias": [
        {"titulo": "Ransomware que entra por SMB expuesto en hospitales", "fuente": "CISA",
         "estado": "creciente", "marca": "real"},
        {"titulo": "Facturas falsas por correo para robar accesos", "fuente": "ENISA",
         "estado": "estable", "marca": "simulado"},
    ],
    "controles": [
        {"control": "A.5.15 Control de acceso", "estado": "con brecha"},
        {"control": "A.8.16 Actividades de monitoreo", "estado": "con brecha"},
        {"control": "A.5.10 Políticas de tecnología de la información", "estado": "conforme"},
    ],
    "tecnicas": [
        {"id": "T1110.003", "nombre": "Contraseñas repetidas",
         "detalle": "Miles de intentos en pocos minutos contra el mismo servicio."},
        {"id": "T1566.002", "nombre": "Phishing por enlace",
         "detalle": "Correos con facturas falsas hacia el personal administrativo."},
    ],
    "indicadores": [
        {"nombre": "ip_origen", "valor": "10.44.19.7", "nota": "Origen de la ráfaga nocturna."},
        {"nombre": "cuenta_sospechosa", "valor": "lab_regional_svc", "nota": "Cuenta fuera de horario."},
        {"nombre": "hash_muestra", "valor": "a1b2c3d4e5f60718", "nota": "Muestra del descargador."},
    ],
    "clave_que_no_se_usa": {"anidada": ["ignorada"]},
}

# ---------------------------------------------------------------------------
# Dataset B — "agosto": dataset distinto, sin un solo literal en común con A.
# ---------------------------------------------------------------------------
DATOS_B = {
    "periodo": "2026-08-01 a 2026-08-31",
    "resumen": ("En agosto la terminal de admisión tuvo sesiones fuera de horario "
                "y el servidor de archivo fue explorado en silencio."),
    "kpis": {"alertas": {"critica": 12, "alta": 7, "media": 9, "baja": 4},
             "cuentas_a_revisar": 2607,
             "conexiones_inseguras": 90317},
    "casos": [
        {"titulo": "Sesiones fuera de horario en la terminal de admisión",
         "fecha": "2026-08-06", "gravedad": "alta",
         "frase": "Se abrió la terminal cuando la admisión estaba cerrada.",
         "ipOrigen": "192.168.77.50", "cuenta": "terminal_admision"},
        {"titulo": "Exploración silenciosa del servidor de archivo",
         "fecha": "2026-08-21", "gravedad": "critica",
         "frase": "Alguien enumeró los recursos del archivo sin dejar rastro.",
         "ipOrigen": "192.168.77.50", "cuenta": "respaldo_cuenta"},
    ],
    "riesgos": [
        {"id": "R4", "nombre": "Suplantación del personal de admisión", "probabilidad": 5,
         "impacto": 4, "nivel": 20, "recomendacion": "Activar segundo factor para las sesiones de admisión."},
        {"id": "R5", "nombre": "Interrupción del archivo clínico", "probabilidad": 3,
         "impacto": 4, "nivel": 12, "recomendacion": "Mantener copias de seguridad fuera de línea."},
        {"id": "R6", "nombre": "Uso indebido de terminales compartidas", "probabilidad": 2,
         "impacto": 3, "nivel": 6, "recomendacion": "Asignar sesiones individuales por terminal."},
    ],
    "tendencias": [
        {"titulo": "Robo de accesos mediante soporte técnico falso", "fuente": "CISA",
         "estado": "creciente", "marca": "simulado"},
        {"titulo": "Ataques a equipos médicos conectados en red", "fuente": "HHS",
         "estado": "estable", "marca": "real"},
    ],
    "controles": [
        {"control": "A.5.14 Información de seguridad en servicios", "estado": "con brecha"},
        {"control": "A.8.5 Seguridad autenticada", "estado": "conforme"},
    ],
    "tecnicas": [
        {"id": "T1078", "nombre": "Cuentas válidas",
         "detalle": "Se usó una cuenta legítima fuera del turno."},
        {"id": "T1046", "nombre": "Descubrimiento de servicios",
         "detalle": "Exploración de puertos del servidor de archivo."},
    ],
    "indicadores": [
        {"nombre": "ip_origen", "valor": "192.168.77.201", "nota": "Origen de la exploración."},
        {"nombre": "cuenta_sospechosa", "valor": "adm_turno_cuenta", "nota": "Cuenta con sesión fuera de turno."},
        {"nombre": "hash_muestra", "valor": "f0e1d2c3b4a59687", "nota": "Muestra del explorador."},
    ],
}

# Solo omisiones: periodo dict, casos incompletos y una entrada corrupta (string en la lista).
PARCIAL = {
    "periodo": {"desde": "2026-01-01", "hasta": "2026-01-31"},
    "casos": [{"titulo": "Caso sin fecha ni gravedad"}, {"fecha": "2026-01-15"}, "entrada-corrupta"],
    "riesgos": [{"id": "R9"}],
    "kpis": {},
    "clave_extra": {"anidada": True},
}

PELIGRO = "<script>alert('hola')</script> y <b>negrita</b>"

PATRON_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


# ---------------------------------------------------------------------------
# Literales de cada dataset, por lo que cada informe debe (o no) renderizar.
# ---------------------------------------------------------------------------
def _lit_gerencial(d):
    lit = [d["periodo"], d["resumen"], str(d["kpis"]["cuentas_a_revisar"]),
           str(d["kpis"]["conexiones_inseguras"])]
    for c in d["casos"]:
        lit += [c["titulo"], c["fecha"], c["frase"]]
    for r in d["riesgos"]:
        lit += [r["id"], r["nombre"], r["recomendacion"]]
    return lit


def _lit_presentacion(d):
    lit = [d["periodo"], d["resumen"]]
    for c in d["casos"]:
        lit += [c["titulo"], c["fecha"], c["frase"]]
    for r in d["riesgos"]:
        lit += [r["id"], r["nombre"], r["recomendacion"]]
    for t in d["tendencias"]:
        lit.append(t["titulo"])
    for k in d["controles"]:
        lit.append(k["control"])
    for t in d["tecnicas"]:
        lit.append(t["id"])
    for i in d["indicadores"]:
        lit.append(i["valor"])
    return lit


def _prohibidos_en_gerencial(d):
    """Lo que el gerencial jamás debe mostrar: IPs, cuentas y técnicas MITRE del dataset."""
    lit = []
    for c in d["casos"]:
        lit += [c["ipOrigen"], c["cuenta"]]
    for i in d["indicadores"]:
        lit.append(i["valor"])
    for t in d["tecnicas"]:
        lit.append(t["id"])
    return lit


def _unicos(*listas):
    return list(dict.fromkeys(x for l in listas for x in l))


LIT_GER_A, LIT_GER_B = _lit_gerencial(DATOS_A), _lit_gerencial(DATOS_B)
LIT_PRES_A, LIT_PRES_B = _lit_presentacion(DATOS_A), _lit_presentacion(DATOS_B)
PROH_A, PROH_B = _prohibidos_en_gerencial(DATOS_A), _prohibidos_en_gerencial(DATOS_B)
TODOS_A = _unicos(LIT_GER_A, LIT_PRES_A, PROH_A)
TODOS_B = _unicos(LIT_GER_B, LIT_PRES_B, PROH_B)

GENERADORES = [reportes.informe_gerencial, reportes.informe_presentacion]


# ---------------------------------------------------------------------------
# Validación de estructura: html.parser es tolerante, así que el test exige
# anidamiento balanceado (etiquetas que se abren se cierran, en orden).
# ---------------------------------------------------------------------------
class _Estructura(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self._VOID:
            self.pila.append(tag)

    def handle_endtag(self, tag):
        if tag in self._VOID:
            return
        assert self.pila, f"cierre sin apertura: </{tag}>"
        assert self.pila[-1] == tag, f"mal anidada: <{self.pila[-1]}> cerrada por </{tag}>"
        self.pila.pop()


def validar(markup: str) -> None:
    p = _Estructura()
    p.feed(markup)
    p.close()
    assert not p.pila, f"etiquetas sin cerrar: {p.pila}"


# ---------------------------------------------------------------------------
# Genéricidad anti-hardcode: dos datasets distintos, cero literales cruzados.
# ---------------------------------------------------------------------------
def test_gerencial_es_generico_no_hardcodeado():
    ga = reportes.informe_gerencial(DATOS_A)
    gb = reportes.informe_gerencial(DATOS_B)
    for lit in LIT_GER_A:
        assert lit in ga, f"gerencial A no muestra su propio literal {lit!r}"
    for lit in LIT_GER_B:
        assert lit in gb, f"gerencial B no muestra su propio literal {lit!r}"
    for lit in TODOS_B:
        assert lit not in ga, f"gerencial A filtra un literal del dataset B: {lit!r}"
    for lit in TODOS_A:
        assert lit not in gb, f"gerencial B filtra un literal del dataset A: {lit!r}"


def test_presentacion_es_generica_no_hardcodeada():
    pa = reportes.informe_presentacion(DATOS_A)
    pb = reportes.informe_presentacion(DATOS_B)
    for lit in LIT_PRES_A:
        assert lit in pa, f"presentación A no muestra su propio literal {lit!r}"
    for lit in LIT_PRES_B:
        assert lit in pb, f"presentación B no muestra su propio literal {lit!r}"
    for lit in TODOS_B:
        assert lit not in pa, f"presentación A filtra un literal del dataset B: {lit!r}"
    for lit in TODOS_A:
        assert lit not in pb, f"presentación B filtra un literal del dataset A: {lit!r}"


# ---------------------------------------------------------------------------
# Prohibición en gerencial / anexo técnico permitido en presentación.
# ---------------------------------------------------------------------------
def test_gerencial_sin_tecnicas_mitre_ni_ips():
    for datos in (DATOS_A, DATOS_B, {}):
        out = reportes.informe_gerencial(datos)
        assert "T1" not in out, "el gerencial no debe mencionar técnicas MITRE"
        assert "MITRE" not in out
        assert not PATRON_IP.search(out), "el gerencial no debe contener direcciones IP"
    # ni los literales técnicos de NINGÚN dataset (se ignoran, no se renderizan)
    for out in (reportes.informe_gerencial(DATOS_A), reportes.informe_gerencial(DATOS_B)):
        for lit in _unicos(PROH_A, PROH_B):
            assert lit not in out, f"el gerencial expone dato técnico {lit!r}"


def test_presentacion_con_anexo_tecnico_al_final():
    pa = reportes.informe_presentacion(DATOS_A)
    # MITRE e IPs sí viven en el presentación, pero solo en el anexo separado al final
    assert "T1110.003" in pa and "T1566.002" in pa
    assert PATRON_IP.search(pa)
    assert "lab_regional_svc" in pa
    antes, anexo = pa.split('id="anexo"')
    assert "T1110.003" not in antes and "10.44.19.7" not in antes, "el anexo debe venir al final"
    assert "T1110.003" in anexo and "10.44.19.7" in anexo
    # la evidencia condensada no arrastra IPs
    evidencia = pa[pa.index("Evidencia condensada"):pa.index("Matriz de riesgos")]
    assert not PATRON_IP.search(evidencia)


# ---------------------------------------------------------------------------
# Tolerancia a campos faltantes: sin KeyError, siempre "sin datos".
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("generador", GENERADORES, ids=["gerencial", "presentacion"])
def test_tolerancia_a_campos_faltantes(generador):
    vacio = generador({})
    validar(vacio)
    assert "sin datos" in vacio
    parcial = generador(PARCIAL)
    validar(parcial)
    assert "sin datos" in parcial
    assert "2026-01-01" in parcial and "2026-01-31" in parcial
    minimo = generador({"casos": [{"titulo": "Solo tiene título"}, {"fecha": "2026-02-02"}],
                        "riesgos": [{"id": "R9"}], "kpis": {"alertas": {}}})
    validar(minimo)
    assert "sin datos" in minimo


# ---------------------------------------------------------------------------
# Escape: ningún valor de datos se inyecta como HTML.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("generador", GENERADORES, ids=["gerencial", "presentacion"])
def test_escape_de_html(generador):
    datos = {
        "periodo": PELIGRO, "resumen": PELIGRO,
        "casos": [{"titulo": PELIGRO, "fecha": "2026-05-05", "gravedad": "alta", "frase": PELIGRO}],
        "riesgos": [{"id": "R1", "nombre": PELIGRO, "probabilidad": 3, "impacto": 4,
                     "nivel": 12, "recomendacion": PELIGRO}],
        "tendencias": [{"titulo": PELIGRO, "fuente": PELIGRO, "estado": PELIGRO, "marca": "real"}],
        "controles": [{"control": PELIGRO, "estado": PELIGRO}],
        "tecnicas": [{"id": PELIGRO, "nombre": PELIGRO, "detalle": PELIGRO}],
        "indicadores": [{"nombre": PELIGRO, "valor": PELIGRO, "nota": PELIGRO}],
    }
    out = generador(datos)
    validar(out)
    assert "<script>" not in out
    assert "</script>" not in out
    assert "<b>negrita</b>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;negrita&lt;/b&gt;" in out


# ---------------------------------------------------------------------------
# Estructura válida, SVG, print a PDF y cero recursos externos.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("datos", [DATOS_A, DATOS_B, {}], ids=["A", "B", "vacio"])
@pytest.mark.parametrize("generador", GENERADORES, ids=["gerencial", "presentacion"])
def test_estructura_html_valida_con_svg_y_print(generador, datos):
    out = generador(datos)
    validar(out)
    assert out.startswith("<!DOCTYPE html>")
    assert "<svg" in out, "cada informe lleva al menos un diagrama SVG"
    assert "@media print" in out, "Guardar como PDF del navegador debe dar un documento pulido"
    assert "page-break" in out
    for externo in ("http://", "https://", "<script", "<link", "@import", "url("):
        assert externo not in out, f"recurso externo prohibido: {externo}"
    assert generador(datos) == out, "salida determinista, sin reloj ni fechas de emisión"


# ---------------------------------------------------------------------------
# Secciones pedidas en cada informe.
# ---------------------------------------------------------------------------
def test_secciones_de_cada_informe():
    g = reportes.informe_gerencial(DATOS_A)
    for seccion in ("Informe gerencial", "Periodo:", "Qué pasó este mes",
                    "Cómo se ven los riesgos", "Probabilidad", "Impacto",
                    "Los casos del período", "Semáforo del período",
                    "Alertas por gravedad", "Cuentas a revisar", "Conexiones inseguras",
                    "Qué recomendamos hacer"):
        assert seccion in g, f"gerencial sin la sección {seccion!r}"
    p = reportes.informe_presentacion(DATOS_A)
    for seccion in ("Resumen ejecutivo", "Evidencia condensada",
                    "Matriz de riesgos y asignación actual", "Tendencias",
                    "Controles ISO 27002", "Flujo de detección", "Anexo técnico",
                    "Ingesta", "Privacidad", "Detección", "Priorización", "Decisión",
                    "Difusión"):
        assert seccion in p, f"presentación sin la sección {seccion!r}"
    assert p.index("Anexo técnico") > p.index("Controles ISO 27002")
    # marcas real/simulado de las tendencias
    assert 'marca real' in p and 'marca simulado' in p
