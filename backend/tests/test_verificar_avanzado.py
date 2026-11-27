"""verificar.enlace() elevado (S15/T17a): clasificación de 5 estados contra el repositorio
dinámico, typosquatting/homógrafos, técnicas MITRE y el enmascarado de PII de denuncias.crear().

Correr desde backend/:  pytest -q tests/test_verificar_avanzado.py

imagen() queda intacto (su prueba sigue en test_api.py) y ninguna prueba toca el repositorio:
las bases viven en tmp vía SENTINEL_ESTADO. Las pruebas de PII viven aquí porque la lista de
superficies editables de T17a no incluye un archivo de pruebas de denuncias propio.
"""
from __future__ import annotations

import pytest

CLAVES_CONTRATO = {"entrada", "tipo", "veredicto", "puntuacion", "lista", "senales", "recomendacion"}


@pytest.fixture()
def aislado(tmp_path, monkeypatch):
    """Estado aislado en tmp: nada escribe en el repositorio (las listas se abren solas al usarlas)."""
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    return tmp_path


def _verificar(entrada: str) -> dict:
    from app import verificar
    return verificar.enlace(entrada)


# ---------- los 5 estados ----------

def test_estado_blanca(aislado):
    r = _verificar("https://www.espe.edu.ec/salud")
    assert r["clasificacion"] == "blanca"
    assert r["veredicto"] == "seguro", r
    assert r["lista"] == "blanca" and r["tecnicas"] == []
    assert r["recomendacion"]          # el legítimo sigue ofreciendo "seguro" y su recomendación


def test_estado_negra(aislado):
    r = _verificar("http://secure-login-portal.xyz/login")
    assert r["clasificacion"] == "negra"
    assert r["veredicto"] == "malicioso", r
    assert r["lista"] == "negra"
    assert any(s["texto"].startswith("El dominio está en la lista negra") for s in r["senales"])


def test_estado_desconocido(aislado):
    r = _verificar("https://tienda-municipal.com/producto")
    assert r["clasificacion"] == "desconocido"
    assert r["veredicto"] == "seguro", r        # sin señales conocidas no hay pánico, pero tampoco es "lista"
    assert r["tecnicas"] == []


def test_estado_typosquatting_por_marca(aislado):
    r = _verificar("https://micr0soft-login.com/acceso")
    assert r["clasificacion"] == "typosquatting", r
    assert r["veredicto"] != "seguro", r
    assert r["referencia"] is None              # imita una marca, no un dominio de la blanca


def test_estado_typosquatting_similitud_con_la_blanca(aislado):
    r = _verificar("https://espe-edu.ec/")
    assert r["clasificacion"] == "typosquatting", r
    assert r["referencia"] == "espe.edu.ec"
    assert r["veredicto"] in ("sospechoso", "malicioso")


def test_estado_typosquatting_punycode_y_homografo(aislado):
    puny = _verificar("https://xn--espe-obra.edu.ec/")
    assert puny["clasificacion"] == "typosquatting", puny
    assert any("punycode" in s["texto"] for s in puny["senales"])
    # homógrafo con letras cirílicas (о de "оrchid") que imita a google
    homografo = _verificar("https://gооgle-support.com/")
    assert homografo["clasificacion"] == "typosquatting", homografo


def test_estado_conflicto(aislado):
    from app import listas
    listas.añadir("blanca", "secure-login-portal.xyz", "Caso en revisión")
    r = _verificar("http://secure-login-portal.xyz/a")
    assert r["clasificacion"] == "conflicto"
    assert r["veredicto"] == "sospechoso", r    # ni bueno ni malo: revisión humana
    assert any("lista blanca y en la negra" in s["texto"] for s in r["senales"])


# ---------- técnicas MITRE ----------

def test_tecnicas_mitre(aislado):
    negra = _verificar("http://secure-login-portal.xyz/login")
    assert [t["id"] for t in negra["tecnicas"]] == ["T1566.002"]
    typos = _verificar("https://micr0soft-login.com/acceso")
    assert [t["id"] for t in typos["tecnicas"]] == ["T1583.001"]
    blanca = _verificar("https://www.espe.edu.ec/")
    assert blanca["tecnicas"] == []
    desconocido = _verificar("https://tienda-municipal.com/producto")
    assert desconocido["tecnicas"] == []


# ---------- contrato público ----------

def test_contrato_publico_de_enlace(aislado):
    for entrada in ("https://www.espe.edu.ec/", "http://secure-login-portal.xyz/a",
                    "esto no es un enlace", "https://tienda-municipal.com/"):
        r = _verificar(entrada)
        assert CLAVES_CONTRATO <= set(r), r
        assert r["tipo"] == "enlace" and r["entrada"] is not None
        assert r["veredicto"] in ("seguro", "sospechoso", "malicioso")
        assert isinstance(r["senales"], list) and r["senales"]


# ---------- PII en denuncias.crear() (S15/T17c) ----------

def test_denuncia_enmascara_pii_antes_de_persistir(aislado):
    from app import denuncias
    descripcion = ("Me pidieron mi cédula 1712345675, mi correo juan.perez@gmail.com, "
                   "el celular 0987654321 y el teléfono +593987123456 para agendar.")
    r = denuncias.crear({"tipo": "pedido_de_datos", "descripcion": descripcion}, origen="ciudadano")
    texto = r["descripcion"]
    # al SOC no le llega ninguna parte del dato: ni prefijos ni dominios, solo la etiqueta
    assert "1712345675" not in texto and "17***" not in texto and "[Cédula protegida]" in texto
    assert "juan.perez" not in texto and "gmail.com" not in texto and "[Correo protegido]" in texto
    assert "0987654321" not in texto and "0987" not in texto and texto.count("[Teléfono protegido]") == 2
    assert "+593987123456" not in texto and "+593" not in texto
    assert "agendar" in texto                  # el resto del relato se conserva
    # lo que quedó guardado en la base es exactamente el texto enmascarado
    assert denuncias.una(r["codigo"])["descripcion"] == texto


def test_denuncia_con_servicios_fijos_y_formatos(aislado):
    from app import denuncias
    r = denuncias.crear({"tipo": "otro", "descripcion": "Llamaron del 072345678 y de 593987123456."},
                        origen="ciudadano")
    texto = r["descripcion"]
    assert "072345678" not in texto and "0723" not in texto
    assert "593987123456" not in texto and "5939" not in texto
    assert texto == "Llamaron del [Teléfono protegido] y de [Teléfono protegido]."


def test_denuncia_contrato_publico_y_hg07_intactos(aislado):
    from app import denuncias
    r = denuncias.crear({"tipo": "venta_de_citas", "contacto_sospechoso": "0981234567",
                         "descripcion": "Me cobraron por una cita"}, origen="ciudadano")
    # contrato de respuesta pública: mismas claves de siempre, sin el texto libre
    assert set(denuncias.publica(r["codigo"])) == {"codigo", "fecha", "tipo", "estado", "respuesta"}
    # cruce HG-07: el seudónimo sale del valor CRUDO (antes de cualquier máscara)
    assert r["contacto_sospechoso_ref"] == denuncias._ref_contacto("0981234567")
    assert r["contacto_sospechoso_ref"].startswith("CT-")
    assert "0981234567" not in r["contacto_sospechoso_mascara"]
    assert denuncias.contactos_reportados() == {r["contacto_sospechoso_ref"]: [r["codigo"]]}
