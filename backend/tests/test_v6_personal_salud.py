"""Personal de salud: panel «Mi panorama», avisos de seguridad y denuncias con voz, video o foto.

Correr desde backend/:  pytest -q tests/test_v6_personal_salud.py
"""
import io
import re
import sqlite3

import pytest
from app import adjuntos

from .test_api import analista, con_analisis, entorno, gen, ingresar  # noqa: F401  (fixtures compartidas)

IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


@pytest.fixture(autouse=True)
def _sin_limite_de_envios():
    """El límite de envíos por equipo es global al proceso: se limpia para no afectar a otros módulos."""
    from app import denuncias
    denuncias._ventana.clear()
    yield
    denuncias._ventana.clear()


# ---------- bytes con magic bytes reales ----------
def webm_video(n: int = 64) -> bytes:
    return b"\x1a\x45\xdf\xa3" + b"\x00" * 40 + b"\x86\x85V_VP8" + b"\x00" * n


def webm_audio(n: int = 64) -> bytes:
    return b"\x1a\x45\xdf\xa3" + b"\x00" * 40 + b"\x86\x86A_OPUS" + b"\x00" * n


def mp4(marca: bytes = b"isom", n: int = 64) -> bytes:
    return b"\x00\x00\x00\x20ftyp" + marca + b"\x00\x00\x02\x00" + b"\x00" * n


def ogg(n: int = 64) -> bytes:
    return b"OggS\x00\x02" + b"\x00" * n


def png(n: int = 64) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * n


# ---------- adjuntos: video ----------
class TestVideo:
    @pytest.fixture(autouse=True)
    def _estado(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))

    @pytest.mark.parametrize("contenido,nombre,tipo", [
        (webm_video(), "video.webm", "video"), (webm_audio(), "voz.webm", "audio"),
        (mp4(), "video.mp4", "video"), (mp4(b"M4A "), "voz.m4a", "audio"), (mp4(b"mp42"), "voz.m4a", "audio"),
    ])
    def test_detecta_video_y_audio_por_contenido(self, contenido, nombre, tipo):
        reg = adjuntos.guardar(contenido, nombre)
        assert reg["tipo"] == tipo
        assert adjuntos.mime(reg).startswith(tipo if tipo != "imagen" else "image")

    def test_video_no_pasa_por_otra_extension(self):
        with pytest.raises(adjuntos.AdjuntoInvalido, match="no coincide"):
            adjuntos.guardar(mp4(), "video.webm")

    def test_tope_de_video_50mb(self, tmp_path):
        assert adjuntos.MAX_VIDEO == 50 * 1024 * 1024
        with pytest.raises(adjuntos.AdjuntoInvalido, match="50 MB"):
            adjuntos.guardar(mp4(n=adjuntos.MAX_VIDEO), "largo.mp4")
        assert not (tmp_path / "adjuntos").exists()

    def test_procesar_video_sin_whisper_degrada(self, monkeypatch):
        reg = adjuntos.guardar(mp4(), "video.mp4")
        monkeypatch.setattr(adjuntos.importlib.util, "find_spec", lambda n: None)
        r = adjuntos.procesar(reg["id"])
        assert r["estado"] == "procesamiento_diferido" and "faster_whisper" in r["nota"]

    def test_indice_viejo_se_migra_sin_perder_filas(self, tmp_path):
        viejo = adjuntos.ESQUEMA.replace("'imagen', 'audio', 'video'", "'imagen', 'audio'")
        db = sqlite3.connect(tmp_path / "adjuntos.sqlite3")
        db.executescript(viejo)
        db.execute("INSERT INTO adjuntos VALUES ('adj-0000000000000001','audio','ogg','a.ogg','a.ogg',3,"
                   "'recibido',NULL,'','2026-11-01T10:00:00')")
        db.commit()
        db.close()
        assert adjuntos.obtener("adj-0000000000000001")["tipo"] == "audio"
        assert adjuntos.guardar(mp4(), "video.mp4")["tipo"] == "video"


# ---------- protección de datos personales en lo que sale de una foto, voz o video ----------
@pytest.mark.parametrize("crudo,sale,no_sale", [
    # documento de identidad leído por OCR (el OCR pega palabras)
    ("CEDULANo.\n171234567-5\nAPELLIDOSYNOMBRES\nPEREZLOPEZ\nJUANCARLOS\nFECHADENACIMIENTO\n12 MAR 1980",
     ["[Cédula protegida]", "[Nombre protegido]", "FECHADENACIMIENTO\n[Fecha protegida]"],
     ["171234567", "PEREZ", "JUANCARLOS", "1980"]),
    ("NOMBRES: ANA LUCIA\nAPELLIDOS: VERA CEDEÑO\nLUGAR DE NACIMIENTO: QUITO\nFECHA DE NACIMIENTO: 1985-04-02",
     ["NOMBRES: [Nombre protegido]", "APELLIDOS: [Nombre protegido]", "QUITO", "NACIMIENTO: [Fecha protegida]"],
     ["ANA LUCIA", "VERA", "1985"]),
    # captura de WhatsApp: cédula de Guayas (09…) y celular (09…) tienen 10 dígitos
    ("Hola, soy Maria Fernanda Torres del centro de citas. Envíe su cedula 0912345675 al 0991234567.",
     ["soy [Nombre protegido] del centro", "[Cédula protegida]", "[Teléfono protegido]"],
     ["Maria", "Torres", "0912345675", "0991234567"]),
    # transcripción de una nota de voz
    ("Me llamó un señor Pedro Andrade, me pidió mi cédula 17 1234 5675 y escribir a cobros@citas.com o al 02 234 5678",
     ["señor [Nombre protegido]", "[Cédula protegida]", "[Correo protegido]", "[Teléfono protegido]"],
     ["Pedro", "Andrade", "5675", "cobros@"]),
])
def test_proteger_reemplaza_por_etiquetas(crudo, sale, no_sale):
    from app.denuncias import proteger
    t = proteger(crudo)
    assert all(x in t for x in sale), t
    assert not any(x in t for x in no_sale), t


def test_proteger_no_toca_lo_que_no_es_personal():
    from app.denuncias import proteger
    t = "Me pidieron 20 dólares por una cita en el Hospital del Sur. El turno era el 14 de diciembre, Quito."
    assert proteger(t) == t


def test_cedula_valida():
    from app.denuncias import cedula_valida
    assert cedula_valida("1712345675") and not cedula_valida("1712345678") and not cedula_valida("17123")


def test_ocr_real_de_una_cedula_sintetica(tmp_path, monkeypatch):
    """Con la lectura local instalada (requirements-ia.txt) se prueba de punta a punta; si no, se omite."""
    pytest.importorskip("rapidocr_onnxruntime")
    pil = pytest.importorskip("PIL.Image")
    from PIL import ImageDraw, ImageFont
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path))
    im = pil.new("RGB", (860, 360), (236, 242, 248))
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 34)
    except OSError:
        pytest.skip("sin fuente para dibujar la cédula de muestra")
    for y, txt in [(20, "CEDULA No."), (70, "171234567-5"), (130, "APELLIDOS Y NOMBRES"), (180, "PEREZ LOPEZ"),
                   (230, "JUAN CARLOS")]:
        d.text((30, y), txt, font=f, fill="black")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    reg = adjuntos.guardar(buf.getvalue(), "cedula.png")
    r = adjuntos.procesar(reg["id"])
    assert r["estado"] == "procesado"
    assert "[Cédula protegida]" in r["texto"] and "[Nombre protegido]" in r["texto"]
    assert "171234567" not in r["texto"] and "PEREZ" not in r["texto"].replace(" ", "")


# ---------- denuncia por voz, video o foto (API) ----------
def _con_lectura(monkeypatch, texto):
    """Simula la lectura local (OCR o transcripción) sin instalar las librerías."""
    monkeypatch.setattr(adjuntos, "_lib_requerida", lambda tipo: "simulada")
    monkeypatch.setattr(adjuntos, "_extraer_texto", lambda reg: texto)


def test_foto_con_cedula_llega_al_soc_solo_como_texto_protegido(entorno, analista, monkeypatch):
    _con_lectura(monkeypatch, "Hola, soy Maria Fernanda Torres. Mande su cedula 1712345675 y 20 dolares al 0991234567")
    r = entorno.post("/api/publico/adjuntos", files={"archivo": ("captura.png", io.BytesIO(png()), "image/png")})
    assert r.status_code == 200, r.text
    foto = r.json()
    # la persona ve, antes de enviar, cómo le llega al equipo de seguridad
    assert foto["estado"] == "procesado" and "[Cédula protegida]" in foto["texto"] and "[Nombre protegido]" in foto["texto"]
    assert adjuntos.ruta(foto["id"]) is None                        # el archivo original ya se borró
    r = entorno.post("/api/publico/denuncias", json={"tipo": "venta_de_citas", "descripcion": "Me cobraban la cita",
                                                     "adjuntos": [foto["id"]], "acepta_privacidad": True})
    assert r.status_code == 200, r.text
    cod = r.json()["codigo"]
    bandeja = entorno.get("/api/denuncias", headers=analista)
    d = next(x for x in bandeja.json() if x["codigo"] == cod)
    assert d["descripcion"].startswith("Me cobraban la cita\n\n[Foto] Hola, soy [Nombre protegido].")
    assert "1712345675" not in bandeja.text and "Maria" not in bandeja.text and "0991234567" not in bandeja.text
    assert d["contadoCon"] == ["Foto"] and "adjuntos" not in d and "responder_a" not in d
    # ya no existe una ruta para abrir el archivo: al SOC le llega solo el texto
    assert entorno.get(f"/api/denuncias/adjuntos/{foto['id']}", headers=analista).status_code in (404, 405)


def test_nota_de_voz_pendiente_se_completa_cuando_hay_transcripcion(entorno, analista, monkeypatch):
    monkeypatch.setattr(adjuntos, "_lib_requerida", lambda tipo: None)      # equipo sin transcripción local
    r = entorno.post("/api/publico/adjuntos", files={"archivo": ("voz.ogg", io.BytesIO(ogg(80)), "audio/ogg")})
    voz = r.json()
    assert voz["estado"] == "procesamiento_diferido" and voz["texto"] is None
    assert adjuntos.ruta(voz["id"]) is not None                     # sin texto todavía: el archivo se conserva
    cod = entorno.post("/api/publico/denuncias", json={"tipo": "pedido_de_datos", "adjuntos": [voz["id"]],
                                                       "acepta_privacidad": True}).json()["codigo"]
    d = next(x for x in entorno.get("/api/denuncias", headers=analista).json() if x["codigo"] == cod)
    assert "[Nota de voz] Recibida" in d["descripcion"]
    # se instala la transcripción: la próxima vez que el SOC abre la bandeja, la denuncia ya trae el texto
    _con_lectura(monkeypatch, "Me llamó la señora Rosa Paredes pidiendo mi cédula 17 1234 5675")
    d = next(x for x in entorno.get("/api/denuncias", headers=analista).json() if x["codigo"] == cod)
    assert d["descripcion"] == "[Nota de voz] Me llamó la señora [Nombre protegido] pidiendo mi cédula [Cédula protegida]"
    assert adjuntos.ruta(voz["id"]) is None and d["contadoCon"] == ["Nota de voz"]


def test_video_y_archivos_rechazados(entorno, monkeypatch):
    _con_lectura(monkeypatch, "Este es el mensaje que me llegó")
    r = entorno.post("/api/publico/adjuntos", files={"archivo": ("video.webm", io.BytesIO(webm_video()), "video/webm")})
    assert r.status_code == 200 and r.json()["tipo"] == "video"
    assert entorno.post("/api/publico/adjuntos",
                        files={"archivo": ("x.jpg", io.BytesIO(b"<script>"), "image/jpeg")}).status_code == 400


def test_denuncia_con_adjunto_inexistente_o_de_mas(entorno):
    base = {"tipo": "otro", "acepta_privacidad": True}
    assert entorno.post("/api/publico/denuncias", json={**base, "adjuntos": ["adj-0123456789abcdef"]}).status_code == 400
    assert entorno.post("/api/publico/denuncias", json={**base, "adjuntos": ["../../etc/passwd"]}).status_code == 422
    assert entorno.post("/api/publico/denuncias", json={**base, "adjuntos": ["adj-0123456789abcdef"] * 4}).status_code == 422


def test_cabeceras_permiten_grabar_solo_en_el_mismo_sitio(entorno):
    r = entorno.get("/api/acceso/roles")
    assert "camera=(self)" in r.headers["permissions-policy"] and "microphone=(self)" in r.headers["permissions-policy"]
    assert "media-src 'self' blob:" in r.headers["content-security-policy"]


# ---------- avisos al personal de salud ----------
def test_aviso_automatico_tras_el_analisis_y_entendido(entorno, analista, con_analisis):
    salud = ingresar(entorno, "salud")
    lista = entorno.get("/api/avisos", headers=salud).json()
    titulos = {a["titulo"] for a in lista}
    assert "Posible salida de información del sistema médico" in titulos
    assert all(set(a) == {"codigo", "fecha", "nivel", "titulo", "texto", "consejo", "origen", "leido"} for a in lista)
    assert lista[0]["nivel"] == "alto" and not lista[0]["leido"]      # lo importante y sin leer va arriba
    fuga = next(a for a in lista if "salida de información" in a["titulo"])
    assert not fuga["leido"] and not IP.search(fuga["texto"] + fuga["consejo"])
    assert entorno.post(f"/api/avisos/{fuga['codigo']}/leido", headers=salud).json()["leido"] is True
    assert next(a for a in entorno.get("/api/avisos", headers=salud).json() if a["codigo"] == fuga["codigo"])["leido"]
    acciones = {(b["accion"], b["objetivo"]) for b in entorno.get("/api/bitacora", headers=ingresar(entorno, "jefe")).json()}
    assert ("Aviso leído", fuga["codigo"]) in acciones
    # un mismo análisis no repite el aviso
    from app import avisos, datos
    assert avisos.tras_analisis(con_analisis["id"], datos.casos(), datos.agendamiento()) == []


def test_aviso_manual_desde_un_caso(entorno, analista, con_analisis):
    s = entorno.get("/api/avisos/sugerido/C3", headers=analista).json()
    assert s["titulo"] and s["texto"] and s["nivel"] in ("alto", "medio", "info")
    r = entorno.post("/api/avisos", headers=analista, json={**s, "texto": s["texto"] + " Origen 10.0.5.23.", "caso": "C3"})
    assert r.status_code == 200, r.text
    assert "10.0.5.23" not in r.json()["texto"] and r.json()["origen"] == "manual"
    salud = ingresar(entorno, "salud")
    assert any(a["codigo"] == r.json()["codigo"] for a in entorno.get("/api/avisos", headers=salud).json())
    # el personal de salud no crea avisos y TI no los ve
    assert entorno.post("/api/avisos", headers=salud, json=s).status_code == 403
    assert entorno.get("/api/avisos", headers=ingresar(entorno, "ti")).status_code == 403
    assert entorno.get("/api/avisos/sugerido/C3", headers=salud).status_code == 403


def test_varias_denuncias_de_engano_avisan_una_vez(entorno, con_analisis):
    for _ in range(3):
        assert entorno.post("/api/publico/denuncias", json={"tipo": "enlace_sospechoso", "enlace": "http://cita-gratis.xyz",
                                                            "acepta_privacidad": True}).status_code == 200
    salud = ingresar(entorno, "salud")
    enganos = [a for a in entorno.get("/api/avisos", headers=salud).json() if a["titulo"].startswith("Circulan")]
    assert len(enganos) == 1


# ---------- panel «Mi panorama» ----------
def test_panorama_solo_para_salud_y_sin_datos_tecnicos(entorno, analista, con_analisis):
    salud = ingresar(entorno, "salud")
    entorno.post("/api/verificar/reportar", headers=salud,
                 json={"entrada": "http://bono-medico.xyz/clave", "veredicto": "sospechoso", "comentario": "llegó por SMS"})
    r = entorno.get("/api/panorama-salud", headers=salud)
    assert r.status_code == 200
    p = r.json()
    assert p["hayAnalisis"] and p["total"] > 0
    assert {a["id"] for a in p["amenazas"]} == {"claves", "cuenta", "fuga", "red", "citas", "engano"}
    assert {d["id"] for d in p["dimensiones"]} == {"atencion", "datos", "citas"}
    assert p["porDia"] and set(p["porDia"][0]) == {"dia", "intentos"}
    assert p["consejos"] and any("Verificar contenido" in c or "contraseña" in c for c in p["consejos"])
    assert any(m["que"].startswith("http://bono-medico.xyz") for m in p["misReportes"])
    # nada técnico ni personal: sin IPs, cuentas, nombres, seudónimos ni ids de casos
    texto = r.text
    assert not IP.search(texto) and "SEU-" not in texto and "ipOrigen" not in texto and '"C1"' not in texto
    for usuario, nombre, _, _ in gen.ATACANTES.values():
        assert usuario not in texto and nombre not in texto
    # otros roles no lo ven
    assert entorno.get("/api/panorama-salud", headers=analista).status_code == 403
    assert entorno.get("/api/panorama-salud").status_code == 401


def test_rol_salud_tiene_panorama_y_verificar():
    from app.seguridad import ROLES
    assert ROLES["salud"]["permisos"] == ["panorama_salud", "verificar"]
    assert "avisar_personal" in ROLES["analista"]["permisos"]
