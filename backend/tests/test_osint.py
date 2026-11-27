"""OSINT real en ThreatPulse (T15/S13): recoletores sin claves, caché con TTL por fuente,
sync manual con tolerancia a fallos y endpoint, TODO sin red.

Correr desde backend/:  pytest -q tests/test_osint.py

Garantías que este módulo fija:
- toda la red pasa por recoletores.obtener y aquí está mockeada; una guarda de socket (autouse)
  bloquea y registra cualquier conexión real: si algo abre un socket, el test falla.
- ninguna prueba escribe fuera de tmp_path (SENTINEL_ESTADO aislado por fixture).
- las fixtures viven en tests/fixtures_osint/.
"""
from __future__ import annotations

import ast
import json
import os
import socket
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .test_threatpulse import CAMPOS_PANTALLA

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures_osint"
FIJO = RAIZ / "backend" / "app" / "fijos" / "tendencias.json"
CAMPOS_ITEM = ("fuente", "tipo", "id_externo", "titulo", "resumen", "cvss", "kev",
               "exploit_publico", "enlace", "fecha", "tags")
T0 = datetime(2026, 11, 27, 8, 0, 0)


def _destino_bd() -> tuple[str, int] | None:
    """Host y puerto de la base configurada en SENTINEL_DB_URL (PostgreSQL), si hay una."""
    from urllib.parse import urlsplit
    url = os.environ.get("SENTINEL_DB_URL", "")
    if not url.startswith("postgresql"):
        return None
    u = urlsplit(url)
    return (u.hostname or "localhost"), (u.port or 5432)


class Red:
    """Guarda de socket: bloquea y registra todo intento de red dentro de los tests.

    La única excepción es la base de datos de la consola (SENTINEL_DB_URL): el backend usa PostgreSQL y
    esa conexión local no es tráfico de OSINT. Cualquier otro destino se bloquea y se registra.
    """

    def __init__(self, originales: dict) -> None:
        self.intentos: list[str] = []
        self._orig = originales
        self._bd = _destino_bd()

    def _es_bd(self, host, puerto) -> bool:
        if not self._bd:
            return False
        h, p = self._bd
        locales = {h, "localhost", "127.0.0.1", "::1"} if h in ("localhost", "127.0.0.1", "::1") else {h}
        return str(host) in locales and (puerto is None or int(puerto) == p)

    def _bloquear(self, args):
        self.intentos.append(str(args[:1]))
        raise OSError("red bloqueada por la guarda de tests")

    def getaddrinfo(self, host, port=None, *a, **k):
        if self._es_bd(host, port):
            return self._orig["getaddrinfo"](host, port, *a, **k)
        return self._bloquear((host, port))

    def create_connection(self, address, *a, **k):
        if self._es_bd(*address[:2]):
            return self._orig["create_connection"](address, *a, **k)
        return self._bloquear((address,))

    def connect(self, sock, address):
        if isinstance(address, tuple) and self._es_bd(*address[:2]):
            return self._orig["connect"](sock, address)
        return self._bloquear((address,))


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    r = Red({"getaddrinfo": socket.getaddrinfo, "create_connection": socket.create_connection,
             "connect": socket.socket.connect})
    monkeypatch.setattr(socket, "getaddrinfo", r.getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", r.create_connection)
    monkeypatch.setattr(socket.socket, "connect", lambda sock, address: r.connect(sock, address))
    return r


@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    """Cliente con estado/ y datos/ en tmp: nada de esto toca el repositorio."""
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path / "estado"))
    monkeypatch.setenv("SENTINEL_DATOS", str(tmp_path / "datos"))
    from app.main import app
    return TestClient(app)


def ingresar(cli, usuario):
    r = cli.post("/api/acceso/ingresar", json={"usuario": usuario, "clave": "demo2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _fixture(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


def _por_url(url: str) -> bytes:
    if "known_exploited" in url:
        return _fixture("kev.json")
    if "services.nvd" in url:
        return _fixture("nvd.json")
    if "exploitdb" in url:
        return _fixture("exploitdb.csv")
    if "otx.alienvault" in url:
        return _fixture("otx.json")
    if "cisa.gov/cybersecurity" in url or "incibe.es" in url:
        return _fixture("cisa.xml")
    if "bleepingcomputer" in url or "thehackernews" in url:
        return _fixture("medio.xml")
    return _fixture("psirt.xml")


def mockear_fetch(monkeypatch, fallar: str | None = None) -> list[str]:
    """Mockea el único punto de red del paquete (recoletores.obtener) devolviendo fixtures."""
    from app.osint import recoletores
    llamadas: list[str] = []

    def fetch(url, **kwargs):
        llamadas.append(url)
        if fallar and fallar in url:
            raise RuntimeError(f"falla simulada para {url}")
        return _por_url(url)

    monkeypatch.setattr(recoletores, "obtener", fetch)
    return llamadas


def _items_crudos():
    from app.osint import recoletores
    return (recoletores.parse_kev(_fixture("kev.json"))
            + recoletores.parse_nvd(_fixture("nvd.json"))
            + recoletores.parse_exploitdb(_fixture("exploitdb.csv")))


def test_normalizacion_por_tipo():
    """Cada tipo de ítem sale con el mismo juego de 11 campos y los tipos correctos."""
    from app.osint import recoletores
    casos = {
        "kev": recoletores.parse_kev(_fixture("kev.json")),
        "cve": recoletores.parse_nvd(_fixture("nvd.json")),
        "exploit": recoletores.parse_exploitdb(_fixture("exploitdb.csv")),
        "boletin": recoletores.parse_rss(_fixture("cisa.xml"), "CISA", "boletin"),
        "psirt": recoletores.parse_rss(_fixture("psirt.xml"), "Microsoft MSRC", "psirt"),
        "medio": recoletores.parse_rss(_fixture("medio.xml"), "BleepingComputer", "medio"),
        "pulso": recoletores.parse_otx(_fixture("otx.json")),
    }
    for tipo, items in casos.items():
        assert items, tipo
        for it in items:
            assert set(it) == set(CAMPOS_ITEM), (tipo, set(it))
            assert it["tipo"] == tipo
            assert it["fuente"] and it["id_externo"] and it["titulo"]
            assert isinstance(it["resumen"], str)
            assert it["cvss"] is None or (isinstance(it["cvss"], float) and 0.0 <= it["cvss"] <= 10.0)
            assert isinstance(it["kev"], bool) and isinstance(it["exploit_publico"], bool)
            assert it["fecha"] is None or (len(it["fecha"]) == 10 and it["fecha"][4] == "-")
            assert isinstance(it["tags"], list) and all(isinstance(t, str) for t in it["tags"])
    assert all(i["kev"] for i in casos["kev"])
    assert all(i["exploit_publico"] for i in casos["exploit"])
    for tipo in ("cve", "boletin", "psirt", "medio", "pulso"):
        assert all(not i["kev"] and not i["exploit_publico"] for i in casos[tipo]), tipo
    # el átomo también se lee (feeds Atom de CERT)
    atom = recoletores.parse_rss(_fixture("atom.xml"), "CERT", "boletin")
    assert len(atom) == 2 and atom[0]["fecha"] == "2026-11-26"


def test_cruce_kev_y_exploit():
    """Un CVE en KEV queda kev=true; en Exploit-DB queda exploit_publico=true (en cualquier ficha)."""
    from app.osint import adaptador
    items = adaptador.cruzar(_items_crudos())
    por = {(i["fuente"], i["id_externo"]): i for i in items}
    # NVD cruzado con ambos catálogos
    assert por[("NVD", "CVE-2026-111111")]["kev"] is True
    assert por[("NVD", "CVE-2026-111111")]["exploit_publico"] is True
    assert por[("NVD", "CVE-2026-444444")]["kev"] is False
    assert por[("NVD", "CVE-2026-444444")]["exploit_publico"] is True
    assert por[("NVD", "CVE-2026-333333")]["kev"] is False
    assert por[("NVD", "CVE-2026-333333")]["exploit_publico"] is False
    # la ficha del propio KEV gana la marca de exploit público
    assert por[("CISA", "CVE-2026-111111")]["exploit_publico"] is True
    assert por[("CISA", "CVE-2026-222222")]["exploit_publico"] is False
    # y el sello que verá la pantalla
    assert adaptador.sello(por[("CISA", "CVE-2026-222222")]) == "real (KEV)"
    assert adaptador.sello(por[("NVD", "CVE-2026-333333")]) == "real (NVD)"


def test_adaptador_entrega_los_campos_de_la_pantalla():
    """Las tendencias reales traen los 11 campos del feed, ids únicos y su sello."""
    from app.osint import adaptador
    tend = [adaptador.a_tendencia(i) for i in adaptador.seleccion(adaptador.cruzar(_items_crudos()))]
    assert len(tend) >= 6
    vistos: set[str] = set()
    for t in tend:
        assert set(CAMPOS_PANTALLA) <= set(t), set(CAMPOS_PANTALLA) - set(t)
        assert t["id"] not in vistos, t["id"]
        vistos.add(t["id"])
        assert t["sello"].startswith("real ("), t["sello"]
        # sin atribución inventada al sector salud: la relevancia se calcula honesta
        assert t["sector"] == ""
        assert isinstance(t["serie"], list) and t["serie"] == []
    cve111 = next(t for t in tend if "111111" in t["id"])
    assert cve111["sello"] == "real (KEV)" and cve111["kev"] is True and cve111["cvss"] == 9.8
    cve444 = next(t for t in tend if "444444" in t["id"])
    assert cve444["sello"] == "real (NVD)" and cve444["exploitPublico"] is True
    # una ficha por CVE: el gemelo de menor datos no aparece dos veces
    assert sum(1 for t in tend if "111111" in t["id"]) == 1


def test_adaptador_solo_anade_confianzas_nuevas():
    """(PRESERVE) El adaptador completa el mapa público de threatpulse sin tocar su archivo
    ni cambiar la confianza de las 4 fuentes del feed fijo: sus scores quedan idénticos."""
    from app import (
        osint,  # noqa: F401 - el adaptador extiende el mapa al importar el paquete
        threatpulse,
    )
    fijas = {"MITRE ATT&CK": 0.95, "CISA": 0.9, "ENISA": 0.9, "HHS": 0.85}
    assert {k: threatpulse.CONFIANZA_FUENTE[k] for k in fijas} == fijas
    assert {"NVD", "INCIBE-CERT", "Fortinet PSIRT"} <= set(threatpulse.CONFIANZA_FUENTE)


def test_ttl_la_fuente_fresca_no_se_vuelve_a_bajar(entorno, sin_red, monkeypatch):
    """TTL: dentro del plazo no se vuelve a bajar nada (y fetched_at no baja); vencida sí.
    KEV tiene TTL de 24 h; el resto 6 h."""
    from app.osint import cache, sincronizar
    llamadas = mockear_fetch(monkeypatch)
    r1 = sincronizar(ahora=T0)
    assert r1["totales"] >= 7 and r1["fallidas"] == 0
    assert r1["actualizadas"] == r1["totales"]
    assert len(llamadas) == r1["totales"]          # una petición por fuente en el primer sync
    estado1 = {f["fuente"]: f["fetched_at"] for f in cache.resumen()}
    # 2 h después: nada vencido, ninguna petición nueva y fetched_at intacto
    r2 = sincronizar(ahora=T0 + timedelta(hours=2))
    assert r2["actualizadas"] == r2["totales"] and r2["fallidas"] == 0
    assert len(llamadas) == r1["totales"]
    assert {f["fuente"]: f["fetched_at"] for f in cache.resumen()} == estado1
    # 7 h después: vencen las de 6 h (NVD sí se refetch) pero la KEV de 24 h sigue fresca
    r3 = sincronizar(ahora=T0 + timedelta(hours=7))
    assert r3["fallidas"] == 0
    assert len([u for u in llamadas if "services.nvd" in u]) == 2
    assert len([u for u in llamadas if "known_exploited" in u]) == 1
    # 25 h después: también vence y se vuelve a bajar la KEV
    sincronizar(ahora=T0 + timedelta(hours=25))
    assert len([u for u in llamadas if "known_exploited" in u]) == 2
    assert sin_red.intentos == []                   # todo mockeado: ni un socket real


def test_fuente_fallida_no_rompe_el_sincronizado(entorno, sin_red, monkeypatch):
    """Una fuente caída no rompe las demás: su caché previa se conserva y la API sigue respondiendo."""
    from app.osint import cache, sincronizar
    mockear_fetch(monkeypatch)
    r1 = sincronizar(ahora=T0)
    assert r1["fallidas"] == 0
    nvd_antes = [i for i in cache.leer() if i["fuente"] == "NVD"]
    assert nvd_antes
    # ahora solo NVD falla (todas vencidas a las 7 h)
    mockear_fetch(monkeypatch, fallar="services.nvd")
    r2 = sincronizar(ahora=T0 + timedelta(hours=7))
    assert r2["fallidas"] == 1
    assert r2["actualizadas"] == r2["totales"] - 1
    nvd_despues = [i for i in cache.leer() if i["fuente"] == "NVD"]
    assert nvd_despues == nvd_antes                 # la caché previa sigue intacta
    fila = next(f for f in cache.resumen() if f["fuente"] == "NVD")
    assert fila["error"]                            # el fallo queda registrado
    assert fila["fetched_at"].startswith("2026-11-27T08:00")   # y el fetched_at no se movió
    # la API responde con lo que hay, sin excepción
    cli = entorno
    ti = ingresar(cli, "ti")
    g = cli.get("/api/threatpulse", headers=ti)
    assert g.status_code == 200, g.text
    assert "osint" in g.json()
    assert sin_red.intentos == []


def test_endpoint_actualiza_con_fetch_mockeado(entorno, sin_red, monkeypatch):
    """POST /api/threatpulse/actualizar (permiso técnico, bitácora) y GET fusionado con sello."""
    from app import estado
    cli = entorno
    llamadas = mockear_fetch(monkeypatch)
    # el permiso es del backend, no del botón: jefe (sin 'tecnico') recibe 403
    jefe = ingresar(cli, "jefe")
    assert cli.post("/api/threatpulse/actualizar", headers=jefe).status_code == 403
    ti = ingresar(cli, "ti")
    r = cli.post("/api/threatpulse/actualizar", headers=ti)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"actualizadas", "fallidas", "totales", "sincronizado_en"}
    assert cuerpo["totales"] >= 7
    assert cuerpo["fallidas"] == 0
    assert cuerpo["actualizadas"] == cuerpo["totales"]
    datetime.fromisoformat(cuerpo["sincronizado_en"])
    assert len(llamadas) == cuerpo["totales"]       # una petición por fuente
    eventos = [e for e in estado.leer("bitacora") if e["accion"] == "OSINT actualizado"]
    assert eventos and eventos[-1]["objetivo"] == "THREATPULSE"
    # segunda actualización dentro del TTL: no vuelve a bajar nada
    r2 = cli.post("/api/threatpulse/actualizar", headers=ti)
    assert r2.status_code == 200
    assert r2.json()["actualizadas"] == r2.json()["totales"]
    assert len(llamadas) == cuerpo["totales"]
    # GET con caché: meta + ítems reales con sello, feed fijo intacto y ordenado
    g = cli.get("/api/threatpulse", headers=ti)
    assert g.status_code == 200, g.text
    d = g.json()
    assert set(d) == {"nota", "tendencias", "osint"}
    meta = d["osint"]
    assert set(meta) == {"sincronizadoEn", "items", "fuentes", "notas"}
    datetime.fromisoformat(meta["sincronizadoEn"])
    assert meta["items"] >= 8 and meta["fuentes"] >= 5
    assert isinstance(meta["notas"], list) and any("oficiales" in n for n in meta["notas"])
    assert "lecturas reales" in d["nota"]
    fijo = json.loads(FIJO.read_text(encoding="utf-8"))
    por_id = {t["id"]: t for t in d["tendencias"]}
    for orig in fijo["tendencias"]:
        t = por_id[orig["id"]]
        for campo in CAMPOS_PANTALLA:
            assert t[campo] == orig[campo], (orig["id"], campo)
        assert t["sello"] == "simulado"
    assert any(t["sello"] == "real (KEV)" for t in d["tendencias"])
    assert any(t["sello"] == "real (NVD)" for t in d["tendencias"])
    scores = [t["score"] for t in d["tendencias"]]
    assert scores == sorted(scores, reverse=True)
    assert sin_red.intentos == []                   # endpoint enteramente mockeado


def test_sin_red_total_falla_controlada_y_feed_fijo_intacto(entorno, sin_red):
    """Sin mock y sin red: el sync falla controlado por fuente y GET responde idéntico a hoy."""
    cli = entorno
    ti = ingresar(cli, "ti")
    r = cli.post("/api/threatpulse/actualizar", headers=ti)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["totales"] >= 7
    assert c["fallidas"] == c["totales"] and c["actualizadas"] == 0
    assert sin_red.intentos                         # intentó abrir red y la guarda lo bloqueó
    g = cli.get("/api/threatpulse", headers=ti)
    assert g.status_code == 200, g.text
    d = g.json()
    fijo = json.loads(FIJO.read_text(encoding="utf-8"))
    assert set(d) == {"nota", "tendencias"}         # sin caché: respuesta idéntica a la de hoy
    assert d["nota"] == fijo["nota"]
    # el orden lo decide el score (igual que antes de existir OSINT): mismos ids, mismo contrato
    assert {t["id"] for t in d["tendencias"]} == {t["id"] for t in fijo["tendencias"]}
    assert all(set(CAMPOS_PANTALLA) <= set(t) for t in d["tendencias"])
    scores = [t["score"] for t in d["tendencias"]]
    assert scores == sorted(scores, reverse=True)


def test_guarda_de_socket_bloquea_y_registra(sin_red):
    """La guarda funciona: cualquier intento de conexión real levanta error y queda registrado."""
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", 9))
    with pytest.raises(OSError):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(OSError):
        s = socket.socket()
        try:
            s.connect(("127.0.0.1", 9))
        finally:
            s.close()
    assert len(sin_red.intentos) == 3


def test_cero_sincronizacion_automatica_al_importar():
    """Ningún módulo dispara sync/red a nivel de módulo (import/startup): solo bajo demanda."""
    prohibidas = {"sincronizar", "recolectar", "obtener"}

    def llamadas_nivel_modulo(arbol):
        for nodo in arbol.body:
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                 ast.Import, ast.ImportFrom)):
                continue
            yield from _recorrer(nodo)

    def _recorrer(nodo):
        if isinstance(nodo, ast.Call):
            yield nodo
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield from _recorrer(hijo)

    revisados = 0
    for ruta in sorted((RAIZ / "backend" / "app").rglob("*.py")):
        revisados += 1
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for llamada in llamadas_nivel_modulo(arbol):
            func = llamada.func
            nombre = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else "")
            assert nombre not in prohibidas, f"{ruta.name}: llamada de nivel módulo a {nombre}()"
    assert revisados >= 20


def test_solo_fuentes_oficiales():
    """Solo CTI/TECHINT oficial: sin medios, blogs, Exploit-DB ni feeds comunitarios."""
    from app.osint import recoletores
    ids = {f["id"] for f in recoletores.fuentes()}
    assert {"cisa_kev", "nvd", "cisa_alertas", "incibe"} <= ids
    assert not ids & {"exploitdb", "bleeping", "hackernews", "otx", "msrc", "cisco", "vmware"}
    assert any("oficiales" in n for n in recoletores.notas_omitidas())

