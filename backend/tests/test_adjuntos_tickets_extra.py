"""Casos de borde de adjuntos (validación, extracción local de texto) y de tickets de reglas para TI."""
import sys
import types

import pytest
from app import adjuntos, config, tickets
from fastapi import HTTPException

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
OGG = b"OggS" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _estado(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))


# ---------- adjuntos ----------
def test_mp3_sin_etiqueta_id3_se_reconoce_por_la_trama():
    reg = adjuntos.guardar(b"\xff\xfb\x90\x00" + b"\x00" * 64, "nota.mp3")
    assert (reg["tipo"], reg["ext"]) == ("audio", "mp3")


@pytest.mark.parametrize(("nombre", "mensaje"), [
    ("foto\x00.png", "nulos"),
    ("foto..png", "'..'"),
])
def test_nombres_peligrosos(nombre, mensaje):
    with pytest.raises(adjuntos.AdjuntoInvalido, match=mensaje):
        adjuntos.guardar(PNG, nombre)


def test_lib_requerida_tolera_errores_de_importacion(monkeypatch):
    def falla(_):
        raise ImportError("roto")
    monkeypatch.setattr(adjuntos.importlib.util, "find_spec", falla)
    assert adjuntos._lib_requerida("audio") is None


def test_extraer_texto_de_adjunto_desconocido():
    with pytest.raises(adjuntos.AdjuntoInvalido, match="desconocido"):
        adjuntos._extraer_texto({"id": "adj-no-existe", "tipo": "imagen"})


def test_transcripcion_de_audio_con_whisper_simulado(monkeypatch):
    class Modelo:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, *a, **k):
            return [types.SimpleNamespace(text=" llámame al 0991234567 "), types.SimpleNamespace(text="hoy")], None
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Modelo))
    monkeypatch.setattr(adjuntos, "_lib_requerida", lambda tipo: "faster_whisper")
    reg = adjuntos.procesar(adjuntos.guardar(OGG, "audio.ogg")["id"])
    assert reg["estado"] == "procesado"
    assert "0991234567" not in reg["texto"] and "hoy" in reg["texto"]          # la PII sale enmascarada


@pytest.mark.parametrize(("resultado", "esperado"), [
    ([[None, "Factura", 0.9], [None, "pague ya", 0.8]], "Factura\npague ya"),
    (None, ""),
])
def test_ocr_de_imagen_con_rapidocr_simulado(monkeypatch, resultado, esperado):
    class OCR:
        def __call__(self, ruta):
            return resultado, None
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", types.SimpleNamespace(RapidOCR=OCR))
    reg = adjuntos.guardar(PNG + esperado.encode(), "foto.png")
    assert adjuntos._extraer_texto(reg) == esperado


def test_si_el_procesamiento_falla_queda_diferido(monkeypatch):
    def falla(reg):
        raise RuntimeError("modelo dañado")
    monkeypatch.setattr(adjuntos, "_lib_requerida", lambda tipo: "rapidocr_onnxruntime")
    monkeypatch.setattr(adjuntos, "_extraer_texto", falla)
    reg = adjuntos.procesar(adjuntos.guardar(PNG + b"x", "foto.png")["id"])
    assert reg["estado"] == "procesamiento_diferido" and "falló" in reg["nota"]


# ---------- tickets ----------
def _datos():
    return {"tipo": "ajustar", "regla": "Sigma 01", "titulo": "Bajar umbral de Telnet", "descripcion": "x",
            "prioridad": "alta"}


def test_ticket_inexistente():
    with pytest.raises(HTTPException) as e:
        tickets.uno("TK-000000")
    assert e.value.status_code == 404


def test_ticket_cerrado_no_se_reabre(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_ENVIAR", False)
    t = tickets.crear(_datos(), "Analista", "SOC")
    assert tickets.gestionar(t["codigo"], "aplicado", "Regla ajustada", "TI", "TI")["estado"] == "aplicado"
    with pytest.raises(HTTPException) as e:
        tickets.gestionar(t["codigo"], "en_progreso", "otra vez", "TI", "TI")
    assert e.value.status_code == 400


@pytest.mark.parametrize("falla", [False, True])
def test_aviso_a_ti_por_telegram(monkeypatch, falla):
    from app import estado, telegram
    enviados = []

    def enviar(texto):
        if falla:
            raise RuntimeError("sin red")
        enviados.append(texto)
    monkeypatch.setattr(config, "TELEGRAM_ENVIAR", True)
    monkeypatch.setattr(telegram, "_enviar", enviar)
    t = tickets.crear(_datos(), "Analista", "SOC")
    aviso = [b for b in estado.leer("bitacora") if b["accion"] == "Aviso a TI" and b["objetivo"] == t["codigo"]][-1]
    if falla:
        assert "No se pudo enviar" in aviso["detalle"]
    else:
        assert enviados and t["codigo"] in enviados[0] and "Enviado por Telegram" in aviso["detalle"]
