"""Adjuntos de foto, audio y video para las denuncias ciudadanas (S15(d)/T18).

Módulo aislado, solo stdlib + lo ya instalado (sqlite3). Las rutas de la API viven en main.py
(/api/publico/adjuntos para subir y /api/denuncias/adjuntos/{id} para que el SOC lo abra).

Almacenamiento local: `estado/adjuntos/adj-<id>.<ext>` con índice propio en
`estado/adjuntos.sqlite3` (mismo patrón sqlite3 puro que app.listas/app.almacen, sin
SQLAlchemy). La ruta base sale de `config.estado()` (SENTINEL_ESTADO), así las pruebas
usan tmp y nunca se escribe en el repositorio.

Validación estricta ANTES de escribir nada — un rechazo es `AdjuntoInvalido` con mensaje
claro, nunca una excepción cruda:
- magic bytes reales: imagen (jpeg/png/webp/gif), audio (ogg/opus, webm, wav, mp3, m4a) y
  video (webm con pista VP8/VP9/AV1, mp4);
- extensión coherente con el contenido (la extensión no manda, mandan los bytes);
- tope de tamaño: imagen 15 MB (igual que verificar.py/portal), audio 25 MB, video 50 MB;
- nombre sin path traversal: sin `..`, sin separadores, sin nulos.

Procesamiento local DEGRADABLE (el diseño central): `procesar(id)` consulta
`importlib.util.find_spec` DENTRO de la función (imports perezosos, nunca al importar el
módulo). Con `faster_whisper` (audio y video) o `rapidocr_onnxruntime` (foto) el texto extraído
queda en estado `procesado`; sin ellas → estado `procesamiento_diferido` con nota clara.
Jamás un error, jamás un alta fallida. Este módulo NUNCA hace red ni descarga modelos:
cualquier descarga de modelo sería un efecto de las librerías opcionales en runtime, con
ellas instaladas (las pruebas NO las instalan). El texto extraído pasa por
`denuncias.proteger` (import perezoso de la función real): cédulas, nombres, correos y teléfonos salen como
[Cédula protegida], [Nombre protegido], etc. Con `descartar_original(id)` se borra el archivo y queda solo el texto.

Contrato (lo consume T17b/T18-wiring):
    guardar(contenido: bytes, nombre_archivo: str) -> dict
        {id, tipo: "imagen"|"audio"|"video", ext, tamano,
         estado: "recibido"|"procesado"|"procesamiento_diferido",
         texto: str | None, creado_en, nota}
        (`nota` es un campo extra informativo: el mensaje claro del estado de procesamiento;
         el resto de claves son exactamente las del contrato.)
    obtener(id) -> dict | None
    ruta(id) -> Path | None          # archivo listo para servir (None si no existe)
    procesar(id) -> dict             # degradación elegante; idempotente

El id es determinista: `adj-` + sha256 del contenido (16 hex). Los mismos bytes producen
el mismo id y la segunda llamada devuelve el registro existente sin duplicar archivos.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
import sqlite3
import threading
from pathlib import Path

from . import config, estado

_log = logging.getLogger(__name__)

MAX_IMAGEN = config.MAX_IMAGEN                      # 15 MB (el mismo tope del portal)
MAX_AUDIO = 25 * 1024 * 1024                        # 25 MB para audio
MAX_VIDEO = 50 * 1024 * 1024                        # 50 MB para video (un minuto grabado en el celular)
LIMITES = {"imagen": MAX_IMAGEN, "audio": MAX_AUDIO, "video": MAX_VIDEO}
ESTADOS = ("recibido", "procesado", "procesamiento_diferido")

_LIBRERIAS = {"audio": "faster_whisper", "video": "faster_whisper", "imagen": "rapidocr_onnxruntime"}

# Formato detectado (magic bytes) -> extensiones coherentes con él (en minúsculas).
_EXTENSIONES = {
    "imagen": {"jpeg": {"jpg", "jpeg"}, "png": {"png"}, "webp": {"webp"}, "gif": {"gif"}},
    "audio": {"ogg": {"ogg"}, "opus": {"opus", "ogg"}, "webm": {"webm"},
              "wav": {"wav"}, "mp3": {"mp3"}, "m4a": {"m4a"}},
    "video": {"webm": {"webm"}, "mp4": {"mp4", "m4v"}},
}
# Tipo de contenido con el que se sirve cada formato (el navegador lo reproduce, nunca lo ejecuta).
MIME = {("imagen", "jpg"): "image/jpeg", ("imagen", "jpeg"): "image/jpeg", ("imagen", "png"): "image/png",
        ("imagen", "webp"): "image/webp", ("imagen", "gif"): "image/gif", ("audio", "ogg"): "audio/ogg",
        ("audio", "opus"): "audio/ogg", ("audio", "webm"): "audio/webm", ("audio", "wav"): "audio/wav",
        ("audio", "mp3"): "audio/mpeg", ("audio", "m4a"): "audio/mp4", ("video", "webm"): "video/webm",
        ("video", "mp4"): "video/mp4", ("video", "m4v"): "video/mp4"}
_PISTAS_VIDEO = (b"V_VP8", b"V_VP9", b"V_AV1", b"V_MPEG4", b"V_MPEGH")
_EXT_CONOCIDAS = {e for sub in _EXTENSIONES.values() for exts in sub.values() for e in exts}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS adjuntos (
    id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL CHECK (tipo IN ('imagen', 'audio', 'video')),
    ext TEXT NOT NULL,
    archivo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    tamano INTEGER NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('recibido', 'procesado', 'procesamiento_diferido')),
    texto TEXT,
    nota TEXT NOT NULL DEFAULT '',
    creado_en TEXT NOT NULL
);
"""

_MIGRAR_V1 = "INSERT INTO adjuntos SELECT * FROM adjuntos_v1; DROP TABLE adjuntos_v1;"

_lock = threading.RLock()


class AdjuntoInvalido(ValueError):
    """Rechazo de adjunto con mensaje claro para quien lo sube (nunca una excepción cruda)."""


# ---------- rutas e índice ----------

def _dir() -> Path:
    return config.estado() / "adjuntos"


def _conexion() -> sqlite3.Connection:
    ruta = config.estado() / "adjuntos.sqlite3"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ruta, timeout=5)
    db.row_factory = sqlite3.Row
    viejo = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'adjuntos'").fetchone()
    if viejo and "'video'" not in viejo["sql"]:
        # Índice creado antes de aceptar video: se rehace con el CHECK nuevo, conservando las filas.
        db.execute("ALTER TABLE adjuntos RENAME TO adjuntos_v1")
        db.executescript(ESQUEMA)
        db.executescript(_MIGRAR_V1)
    db.executescript(ESQUEMA)
    db.commit()
    return db


def _fila_dict(fila: sqlite3.Row) -> dict:
    return {"id": fila["id"], "tipo": fila["tipo"], "ext": fila["ext"], "tamano": fila["tamano"],
            "estado": fila["estado"], "texto": fila["texto"], "creado_en": fila["creado_en"],
            "nota": fila["nota"]}


# ---------- validación estricta ----------

def _detectar(contenido: bytes, ext: str = "") -> tuple[str, str] | None:
    """(tipo, formato) según los magic bytes reales; None si no es una imagen, audio o video conocido."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return "imagen", "jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "imagen", "png"
    if contenido.startswith((b"GIF87a", b"GIF89a")):
        return "imagen", "gif"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "imagen", "webp"
    if contenido[:4] == b"OggS":
        # Opus vive en un contenedor Ogg: el paquete de cabecera identifica el códec.
        return "audio", "opus" if b"OpusHead" in contenido[:64] else "ogg"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WAVE":
        return "audio", "wav"
    if contenido[:4] == b"\x1a\x45\xdf\xa3":
        # EBML/Matroska (WebM): la pista de video declara su códec (V_VP8, V_VP9...) al inicio.
        cabecera = contenido[:262144]
        return ("video" if any(p in cabecera for p in _PISTAS_VIDEO) else "audio"), "webm"
    if contenido[4:8] == b"ftyp":
        # MP4/ISO-BMFF: marca M4A (o extensión .m4a, como graba Safari) es audio; lo demás, video.
        marca = contenido[8:12]
        return ("audio", "m4a") if marca in (b"M4A ", b"M4B ") or ext == "m4a" else ("video", "mp4")
    if contenido.startswith(b"ID3"):
        return "audio", "mp3"
    if len(contenido) >= 2 and contenido[0] == 0xFF and contenido[1] & 0xE0 == 0xE0:
        return "audio", "mp3"                         # sincronización de trama MPEG sin etiqueta ID3
    return None


def tipo_de(contenido: bytes, nombre_archivo: str) -> str | None:
    """«imagen», «audio» o «video» según los bytes reales; None si no es un formato conocido."""
    n = str(nombre_archivo or "")
    detectado = _detectar(bytes(contenido or b""), n.rsplit(".", 1)[-1].lower() if "." in n else "")
    return detectado[0] if detectado else None


def _validar_nombre(nombre) -> str:
    """Nombre de archivo sin path traversal: sin `..`, sin separadores, sin nulos, con extensión."""
    n = str(nombre if nombre is not None else "").strip()
    if not n:
        raise AdjuntoInvalido("El archivo no tiene nombre.")
    if "\x00" in n:
        raise AdjuntoInvalido("El nombre del archivo no puede contener caracteres nulos.")
    if "/" in n or "\\" in n:
        raise AdjuntoInvalido("El nombre del archivo no puede contener separadores de ruta.")
    if ".." in n:
        raise AdjuntoInvalido("El nombre del archivo no puede contener '..'.")
    if "." not in n or not n.rsplit(".", 1)[0]:
        raise AdjuntoInvalido("El archivo debe llamarse como 'foto.jpg': nombre y extensión.")
    ext = n.rsplit(".", 1)[1].lower()
    if ext not in _EXT_CONOCIDAS:
        raise AdjuntoInvalido(
            f"Extensión .{ext} no reconocida: use una imagen (jpg, png, gif, webp), "
            "un audio (ogg, opus, webm, wav, mp3, m4a) o un video (mp4, webm).")
    return n, ext


# ---------- contrato público ----------

def guardar(contenido: bytes, nombre_archivo: str) -> dict:
    """Valida estrictamente, guarda el archivo en estado/adjuntos/ y lo registra en el índice.

    Estado inicial `recibido`. El id depende solo del contenido: validar antes de escribir
    deja el repositorio intacto ante cualquier rechazo.
    """
    if not isinstance(contenido, (bytes, bytearray)) or not len(contenido):
        raise AdjuntoInvalido("El archivo está vacío: no se recibió contenido.")
    datos = bytes(contenido)
    nombre, ext = _validar_nombre(nombre_archivo)
    detectado = _detectar(datos, ext)
    if detectado is None:
        raise AdjuntoInvalido(
            "El contenido no corresponde a una imagen, audio o video conocido "
            "(se revisan los bytes reales del archivo, no la extensión que dice el nombre).")
    tipo, formato = detectado
    if ext not in _EXTENSIONES[tipo][formato]:
        raise AdjuntoInvalido(f"La extensión .{ext} no coincide con el contenido real ({tipo}/{formato}).")
    limite = LIMITES[tipo]
    if len(datos) > limite:
        mb = limite // (1024 * 1024)
        raise AdjuntoInvalido(
            f"El archivo pesa {len(datos) // (1024 * 1024)} MB: el tope para {tipo} es {mb} MB.")

    id_adj = "adj-" + hashlib.sha256(datos).hexdigest()[:16]
    archivo = f"{id_adj}.{ext}"
    with _lock:
        db = _conexion()
        try:
            fila = db.execute("SELECT * FROM adjuntos WHERE id = ?", (id_adj,)).fetchone()
            if fila is not None:
                return _fila_dict(fila)               # mismos bytes: registro existente, sin duplicar
            destino = _dir() / archivo
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(datos)
            db.execute(
                "INSERT INTO adjuntos (id, tipo, ext, archivo, nombre, tamano, estado, texto, nota, creado_en) "
                "VALUES (?, ?, ?, ?, ?, ?, 'recibido', NULL, '', ?)",
                (id_adj, tipo, ext, archivo, nombre, len(datos), estado.ahora()))
            db.commit()
            fila = db.execute("SELECT * FROM adjuntos WHERE id = ?", (id_adj,)).fetchone()
            return _fila_dict(fila)
        finally:
            db.close()


def obtener(adjunto_id: str) -> dict | None:
    """Registro del adjunto; None si el id no existe."""
    with _lock:
        db = _conexion()
        try:
            fila = db.execute("SELECT * FROM adjuntos WHERE id = ?",
                              (str(adjunto_id or ""),)).fetchone()
            return None if fila is None else _fila_dict(fila)
        finally:
            db.close()


def mime(reg: dict) -> str:
    """Tipo de contenido para servir el adjunto."""
    return MIME.get((reg["tipo"], reg["ext"]), "application/octet-stream")


def ruta(adjunto_id: str) -> Path | None:
    """Archivo listo para servir; None si el id no existe o el archivo falta en disco."""
    with _lock:
        db = _conexion()
        try:
            fila = db.execute("SELECT archivo FROM adjuntos WHERE id = ?",
                              (str(adjunto_id or ""),)).fetchone()
        finally:
            db.close()
    if fila is None:
        return None
    destino = _dir() / fila["archivo"]
    return destino if destino.is_file() else None


# ---------- procesamiento local degradable ----------

def _lib_requerida(tipo: str) -> str | None:
    """Nombre de la librería opcional si está instalada. find_spec DENTRO de la función."""
    nombre = _LIBRERIAS[tipo]
    try:
        return nombre if importlib.util.find_spec(nombre) else None
    except Exception:
        return None


def _extraer_texto(reg: dict) -> str:
    """Transcripción (faster-whisper) o OCR (rapidocr-onnxruntime): imports perezosos DENTRO.

    Este módulo no hace red ni descarga modelos: con las librerías instaladas, cualquier
    descarga de modelo es un efecto de la propia librería en runtime.
    """
    archivo = ruta(reg["id"])
    if archivo is None:
        raise AdjuntoInvalido(f"Adjunto desconocido: {reg['id']!r}.")
    if reg["tipo"] in ("audio", "video"):          # whisper lee la pista de audio del video
        from faster_whisper import WhisperModel
        modelo = WhisperModel(os.environ.get("SENTINEL_WHISPER_MODEL", "small"),
                              device="cpu", compute_type="int8")
        segmentos, _ = modelo.transcribe(str(archivo), language="es", beam_size=1, vad_filter=False)
        return " ".join(s.text.strip() for s in segmentos).strip()
    from rapidocr_onnxruntime import RapidOCR
    resultado, _ = RapidOCR()(str(archivo))
    if not resultado:
        return ""
    return "\n".join(str(t) for _, t, _ in resultado)


def _enmascarar_texto(texto: str) -> str:
    """Datos personales del texto extraído -> [Cédula protegida], [Nombre protegido], etc.

    Usa la MISMA función de denuncias (no se duplica la lógica)."""
    from . import denuncias  # import perezoso: evita ciclos con el wiring T17b
    return denuncias.proteger(texto)


def descartar_original(adjunto_id: str) -> dict | None:
    """Borra el archivo original y deja solo el texto protegido (minimización de datos, LOPDP).

    Solo actúa si el adjunto ya está procesado: sin texto no se pierde lo que la persona contó."""
    reg = obtener(adjunto_id)
    if reg is None or reg["estado"] != "procesado":
        return reg
    archivo = ruta(adjunto_id)
    if archivo is not None:
        archivo.unlink(missing_ok=True)
    return _actualizar(reg, "procesado", texto=reg["texto"],
                       nota="El archivo original se borró: solo queda el texto con los datos personales protegidos.")


def _actualizar(reg: dict, nuevo_estado: str, *, texto: str | None = None, nota: str = "") -> dict:
    with _lock:
        db = _conexion()
        try:
            db.execute("UPDATE adjuntos SET estado = ?, texto = ?, nota = ? WHERE id = ?",
                       (nuevo_estado, texto, nota, reg["id"]))
            db.commit()
            fila = db.execute("SELECT * FROM adjuntos WHERE id = ?", (reg["id"],)).fetchone()
            return _fila_dict(fila)
        finally:
            db.close()


def procesar(adjunto_id: str) -> dict:
    """Extrae texto localmente si las librerías opcionales están; si no, degrada a
    `procesamiento_diferido` con nota clara. Jamás lanza por falta de librerías ni por un
    fallo del procesamiento: el adjunto ya está guardado y el alta nunca falla.
    Idempotente: un adjunto ya `procesado` no se vuelve a procesar.
    """
    reg = obtener(adjunto_id)
    if reg is None:
        raise AdjuntoInvalido(f"Adjunto desconocido: {adjunto_id!r}.")
    if reg["estado"] == "procesado":
        return reg
    modulo = _lib_requerida(reg["tipo"])
    if modulo is None:
        lib = _LIBRERIAS[reg["tipo"]]
        accion = {"audio": "transcribir el audio", "video": "transcribir el audio del video"}.get(
            reg["tipo"], "leer la foto por OCR")
        return _actualizar(
            reg, "procesamiento_diferido",
            nota=(f"Procesamiento diferido: falta la librería opcional {lib} para {accion} "
                  "localmente. El adjunto está guardado; se procesará cuando se instale."))
    try:
        crudo = _extraer_texto(reg)
        texto = _enmascarar_texto(str(crudo or ""))
    except Exception as e:
        _log.warning("procesamiento local falló para %s: %s", reg["id"], e)
        return _actualizar(
            reg, "procesamiento_diferido",
            nota=(f"Procesamiento diferido: falló el procesamiento local con {modulo} "
                  f"({type(e).__name__}). El adjunto está guardado."))
    return _actualizar(reg, "procesado", texto=texto, nota="")
