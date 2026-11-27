"""Adjuntos de foto y audio para denuncias (S15(d)/T18): validación estricta por magic bytes,
almacenamiento local en estado/adjuntos y procesamiento local DEGRADABLE.

Correr desde backend/:  pytest -q tests/test_adjuntos.py

Ninguna prueba toca el repositorio: el índice y los archivos viven en tmp vía SENTINEL_ESTADO.
Las librerías opcionales (faster_whisper, rapidocr_onnxruntime) NO están instaladas: la
degradación se verifica con find_spec devolviendo None, y el camino "procesado" simula la
librería parchando find_spec y el extractor.
"""
from __future__ import annotations

import importlib.util

import pytest
from app import adjuntos


@pytest.fixture(autouse=True)
def estado_tmp(tmp_path, monkeypatch):
    """Cada prueba trabaja con su propio estado en tmp: nada se escribe en el repositorio."""
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))


# ---------- fixtures: bytes con magic bytes reales ----------
def jpeg(n: int = 64) -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * n


def png(n: int = 64) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * n


def gif(n: int = 64) -> bytes:
    return b"GIF89a" + b"\x00" * n


def webp(n: int = 64) -> bytes:
    return b"RIFF" + (n + 4).to_bytes(4, "little") + b"WEBP" + b"\x00" * n


def ogg(n: int = 64) -> bytes:
    return b"OggS\x00\x02" + b"\x00" * n


def opus(n: int = 64) -> bytes:
    return b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * n


def wav(n: int = 64) -> bytes:
    return b"RIFF" + (n + 4).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * n


def mp3(n: int = 64) -> bytes:
    return b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * n


def webm(n: int = 64) -> bytes:
    return b"\x1a\x45\xdf\xa3" + b"\x00" * n


# ---------- almacenamiento y contrato ----------

@pytest.mark.parametrize("contenido,ext,tipo", [
    (jpeg(), "jpg", "imagen"), (jpeg(), "jpeg", "imagen"), (png(), "png", "imagen"),
    (gif(), "gif", "imagen"), (webp(), "webp", "imagen"),
    (ogg(), "ogg", "audio"), (opus(), "opus", "audio"), (opus(), "ogg", "audio"),
    (wav(), "wav", "audio"), (mp3(), "mp3", "audio"), (webm(), "webm", "audio"),
])
def test_formatos_validos(contenido, ext, tipo):
    reg = adjuntos.guardar(contenido, f"archivo.{ext}")
    assert reg["tipo"] == tipo and reg["ext"] == ext
    assert reg["tamano"] == len(contenido) and reg["estado"] == "recibido"
    assert adjuntos.ruta(reg["id"]).read_bytes() == contenido


def test_contrato_de_guardar():
    reg = adjuntos.guardar(jpeg(), "foto.jpg")
    assert {"id", "tipo", "ext", "tamano", "estado", "texto", "creado_en"} <= set(reg)
    assert reg["estado"] == "recibido" and reg["texto"] is None
    assert reg["nota"] == "" and reg["creado_en"]
    assert adjuntos.obtener(reg["id"]) == reg


def test_almacenamiento_en_estado(tmp_path):
    reg = adjuntos.guardar(jpeg(), "foto.jpg")
    assert (tmp_path / "adjuntos" / f"{reg['id']}.jpg").is_file()
    assert (tmp_path / "adjuntos.sqlite3").is_file()
    assert adjuntos.ruta(reg["id"]) == tmp_path / "adjuntos" / f"{reg['id']}.jpg"


def test_id_determinista_y_unico():
    a = adjuntos.guardar(jpeg(), "uno.jpg")
    b = adjuntos.guardar(jpeg(), "otro_nombre.jpg")   # mismos bytes → mismo id, sin duplicar
    c = adjuntos.guardar(png(), "dos.png")
    assert a["id"] == b["id"] and b == a
    assert a["id"] != c["id"]
    assert a["id"].startswith("adj-") and len(a["id"]) == len("adj-") + 16


def test_obtener_y_ruta_desconocidos():
    assert adjuntos.obtener("adj-0000000000000000") is None
    assert adjuntos.ruta("adj-0000000000000000") is None
    with pytest.raises(adjuntos.AdjuntoInvalido):
        adjuntos.procesar("adj-0000000000000000")


# ---------- validación estricta ----------

@pytest.mark.parametrize("contenido,ext", [
    (png(), "jpg"), (jpeg(), "png"), (ogg(), "mp3"), (mp3(), "wav"), (wav(), "ogg"),
])
def test_rechazo_extension_no_coincide_con_contenido(contenido, ext):
    with pytest.raises(adjuntos.AdjuntoInvalido) as e:
        adjuntos.guardar(contenido, f"foto.{ext}")
    assert "no coincide" in str(e.value)


def test_rechazo_contenido_desconocido(tmp_path):
    with pytest.raises(adjuntos.AdjuntoInvalido) as e:
        adjuntos.guardar(b"<html><script>alert(1)</script></html>", "foto.jpg")
    assert str(e.value)
    assert not (tmp_path / "adjuntos").exists()
    assert not (tmp_path / "adjuntos.sqlite3").exists()


def test_rechazo_extension_desconocida():
    with pytest.raises(adjuntos.AdjuntoInvalido) as e:
        adjuntos.guardar(jpeg(), "foto.bmp")
    assert str(e.value)


def test_rechazo_vacio():
    with pytest.raises(adjuntos.AdjuntoInvalido):
        adjuntos.guardar(b"", "foto.jpg")


@pytest.mark.parametrize("nombre", [
    "../../etc/passwd.jpg", "carpeta/foto.jpg", "carpeta\\foto.jpg", "foto\x00.jpg",
    "..", "sub/../foto.jpg",
])
def test_rechazo_path_traversal(nombre, tmp_path):
    with pytest.raises(adjuntos.AdjuntoInvalido) as e:
        adjuntos.guardar(jpeg(), nombre)
    assert str(e.value)                      # mensaje claro, nunca una excepción cruda
    assert not (tmp_path / "adjuntos").exists()
    assert not (tmp_path / "adjuntos.sqlite3").exists()


def test_umbrales_de_tamano():
    assert adjuntos.MAX_IMAGEN == 15 * 1024 * 1024      # el mismo tope del portal (verificar.py)
    assert adjuntos.MAX_AUDIO == 25 * 1024 * 1024


def test_rechazo_imagen_sobre_15mb(tmp_path):
    grande = b"\xff\xd8\xff\xe0" + b"\x00" * adjuntos.MAX_IMAGEN
    with pytest.raises(adjuntos.AdjuntoInvalido) as e:
        adjuntos.guardar(grande, "grande.jpg")
    assert "15 MB" in str(e.value)
    assert not (tmp_path / "adjuntos").exists()


def test_rechazo_audio_sobre_25mb(tmp_path):
    grande = b"OggS" + b"\x00" * adjuntos.MAX_AUDIO
    with pytest.raises(adjuntos.AdjuntoInvalido) as e:
        adjuntos.guardar(grande, "grande.ogg")
    assert "25 MB" in str(e.value)
    assert not (tmp_path / "adjuntos").exists()


# ---------- procesamiento degradable ----------

@pytest.mark.parametrize("contenido,nombre,lib", [
    (png(), "foto.png", "rapidocr_onnxruntime"),
    (ogg(), "graba.ogg", "faster_whisper"),
])
def test_procesar_sin_librerias_degrada(contenido, nombre, lib, monkeypatch):
    reg = adjuntos.guardar(contenido, nombre)
    assert reg["estado"] == "recibido"
    consultas: list[str] = []

    def _sin_libreria(n):
        consultas.append(n)
        return None

    monkeypatch.setattr(importlib.util, "find_spec", _sin_libreria)
    degradado = adjuntos.procesar(reg["id"])           # jamás lanza por falta de librerías
    assert lib in consultas, "procesar consulta la librería opcional con find_spec"
    assert degradado["estado"] == "procesamiento_diferido"
    assert degradado["texto"] is None
    assert lib in degradado["nota"] and "diferido" in degradado["nota"]
    # el alta nunca falla: el registro y el archivo siguen intactos
    assert adjuntos.obtener(reg["id"])["estado"] == "procesamiento_diferido"
    assert adjuntos.ruta(reg["id"]).is_file()


def test_texto_extraido_sale_enmascarado(monkeypatch):
    from app import denuncias
    reg = adjuntos.guardar(ogg(), "graba.ogg")
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda nombre: object() if nombre == "faster_whisper" else None)
    crudo = "Mi cédula 1712345678, correo juan.perez@ejemplo.com y teléfono 0987654321"
    monkeypatch.setattr(adjuntos, "_extraer_texto", lambda r: crudo)
    procesado = adjuntos.procesar(reg["id"])
    assert procesado["estado"] == "procesado"
    assert procesado["texto"] == denuncias._enmascarar_pii(crudo)   # la función real, no una copia
    assert "1712345678" not in procesado["texto"]
    assert "juan.perez" not in procesado["texto"]
    assert "0987654321" not in procesado["texto"]
    assert "@ejemplo.com" in procesado["texto"]


def test_el_texto_pasa_por_enmascarar_pii_de_denuncias(monkeypatch):
    from app import denuncias
    reg = adjuntos.guardar(ogg(), "graba.ogg")
    monkeypatch.setattr(importlib.util, "find_spec", lambda nombre: object())
    monkeypatch.setattr(adjuntos, "_extraer_texto", lambda r: "texto crudo")
    monkeypatch.setattr(denuncias, "_enmascarar_pii", lambda t: f"«{t}»")
    procesado = adjuntos.procesar(reg["id"])
    assert procesado["texto"] == "«texto crudo»"


def test_procesar_idempotente(monkeypatch):
    reg = adjuntos.guardar(ogg(), "graba.ogg")
    monkeypatch.setattr(importlib.util, "find_spec", lambda nombre: object())
    monkeypatch.setattr(adjuntos, "_extraer_texto", lambda r: "hola")
    primero = adjuntos.procesar(reg["id"])
    assert primero["estado"] == "procesado"
    # sin librerías y con un extractor que fallaría: ya procesado no se vuelve a tocar
    monkeypatch.setattr(importlib.util, "find_spec", lambda nombre: None)
    monkeypatch.setattr(adjuntos, "_extraer_texto",
                        lambda r: (_ for _ in ()).throw(AssertionError("no debe reprocesar")))
    assert adjuntos.procesar(reg["id"]) == primero
