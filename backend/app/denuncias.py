"""Canal de denuncias para afiliados y jubilados, y reportes del personal de salud.

Mínimo necesario (LOPDP): no se pide cédula ni nombre. Al SOC solo le llega lo que pasó: en el texto,
cédulas, nombres, correos y teléfonos se reemplazan por etiquetas completas ([Cédula protegida],
[Nombre protegido], [Correo protegido], [Teléfono protegido]), sin dejar ninguna parte del dato. El contacto sospechoso que la persona reporta se guarda solo
como seudónimo (para cruzarlo con el módulo de agendamiento, patrón HG-07) y en forma enmascarada
para el SOC: el seudónimo se calcula SIEMPRE sobre el valor crudo, antes de cualquier máscara.
La denuncia es anónima: no se pide ni se guarda un correo o teléfono para responder. La persona sigue su
denuncia con el código que recibe. Puede contarlo por voz o con una foto (app.adjuntos): eso se pasa a
texto en el mismo equipo, los datos personales salen como [Cédula protegida] o [Nombre protegido], y al SOC le
llega solo ese texto, como cualquier denuncia escrita. El archivo original se borra en cuanto se pasa a texto.
"""
from __future__ import annotations

import re
import secrets
import threading
import time

from fastapi import HTTPException

from . import estado, verificar

TIPOS = {
    "venta_de_citas": "Me ofrecieron una cita médica a cambio de dinero",
    "pedido_de_datos": "Me llamaron o escribieron pidiendo mis datos o claves",
    "enlace_sospechoso": "Recibí un mensaje o enlace sospechoso",
    "uso_de_mis_datos": "Creo que alguien usó mis datos o mi cita",
    "otro": "Otra situación",
    "contenido_reportado": "Contenido sospechoso reportado por el personal de salud",
}
ESTADOS = {"recibida": "Recibida", "en_revision": "En revisión", "atendida": "Atendida", "descartada": "Cerrada"}
MAX_ADJUNTOS = 3
_ventana: dict[str, list[float]] = {}
_lock = threading.Lock()


def _ref_contacto(texto: str) -> str:
    from motor.agendamiento import referencia_contacto  # misma función y sal que el motor
    return referencia_contacto(texto)


def limitar(ip: str, maximo: int = 5, segundos: int = 600,
            mensaje: str = "Recibimos varias denuncias desde este equipo. Intenta de nuevo en unos minutos.") -> None:
    ahora = time.time()
    with _lock:
        v = [t for t in _ventana.get(ip, []) if ahora - t < segundos]
        if len(v) >= maximo:
            raise HTTPException(429, mensaje)
        v.append(ahora)
        _ventana[ip] = v


def _enmascarar(texto: str) -> str:
    t = texto.strip()
    return ("•" * max(0, len(t) - 4)) + t[-4:] if len(t) > 4 else "••••"


# --- PII en el texto libre (LOPDP): patrones de comun/pii.py de la fuente, adaptados a Sentinel ---
# Cédula ecuatoriana: provincia 01-24 o 30, tercer dígito 0-5 y 10 dígitos (los 9 base más el
# dígito verificador). Los celulares (09 + 8 dígitos) no entran aquí porque se resuelven antes.
PATRON_CEDULA = re.compile(r"(?<!\d)(?:0[1-9]|1\d|2[0-4]|30)[0-5]\d{7}(?!\d)")
# Sin backtracking superlineal: empieza solo al inicio de un token y con longitudes acotadas.
PATRON_EMAIL = re.compile(r"(?<![a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]{1,64}@[a-zA-Z0-9-]{1,63}(?:\.[a-zA-Z0-9-]{1,63}){1,8}")
PATRON_CELULAR = re.compile(r"(?<!\d)09\d{8}(?!\d)")          # celular 09xx
PATRON_FIJO = re.compile(r"(?<!\d)07\d{7}(?!\d)")              # fijo 07xx
PATRON_INTL = re.compile(r"(?<!\d)\+?593\d{9}(?!\d)")           # +593...


def _enmascarar_pii(texto: str) -> str:
    """Cédula, correo y teléfono -> *** conservando solo la estructura mínima (lo demás se conserva).

    El correo conserva su dominio (dato no personal, útil al SOC), el teléfono su prefijo y la
    cédula su provincia. El orden importa: el correo va primero para que sus dígitos no se
    confundan con una cédula, y los teléfonos antes que la cédula para que un 09xx no se lea
    como provincia 09.
    """
    t = PATRON_EMAIL.sub(lambda m: "***@" + m.group(0).rpartition("@")[2], texto)
    t = PATRON_INTL.sub(lambda m: m.group(0)[:4] + "***", t)
    t = PATRON_CELULAR.sub(lambda m: m.group(0)[:4] + "***", t)
    t = PATRON_FIJO.sub(lambda m: m.group(0)[:4] + "***", t)
    t = PATRON_CEDULA.sub(lambda m: m.group(0)[:2] + "***", t)
    return t


# --- Texto escrito o que sale de una foto o una nota de voz: los datos personales se reemplazan por etiquetas ---
PROTEGIDO = {"cedula": "[Cédula protegida]", "nombre": "[Nombre protegido]", "correo": "[Correo protegido]",
             "telefono": "[Teléfono protegido]", "fecha": "[Fecha protegida]"}
# El OCR y la transcripción a veces separan los dígitos («171234567-5», «17 1234 5675»).
_CEDULA_FLEX = re.compile(r"(?<![\d+])(?:0[1-9]|1\d|2[0-4]|30)[ .]?[0-5](?:[ .]?\d){6}[ .-]?\d(?![\d])")
_CONTEXTO_CEDULA = re.compile(r"(?i)(?:c[eé]dula|c\.?\s?i\.?|identidad|identificaci[oó]n|n[uú]mero|no\.?)\W{0,12}$")
_CELULAR_FLEX = re.compile(r"(?<![\d])(?:\+?593[ -]?|0)9(?:[ .-]?\d){8}(?![\d])")
_FIJO_FLEX = re.compile(r"(?<![\d])(?:\+?593[ -]?|0)[2-7](?:[ .-]?\d){7}(?![\d])")
_MAY = "A-ZÁÉÍÓÚÑÜ"
_MIN = "a-záéíóúñü"
_PALABRA = rf"(?:[{_MAY}][{_MIN}]+|[{_MAY}]{{2,}})"
_NOMBRE = rf"{_PALABRA}(?:\s+(?:de\s+(?:la\s+|los\s+)?)?{_PALABRA}){{0,3}}"
# «me llamo…», «soy…», «a nombre de…», «la señora…», «el doctor…» seguidos de palabras con mayúscula
_PRESENTA = re.compile(r"(?P<antes>\b(?i:me\s+llamo|mi\s+nombre\s+es|soy|le\s+habla|habla|a\s+nombre\s+de|se\s+llama|"
                       r"llamad[oa]|señora|señor|señorita|sr\.?|sra\.?|srta\.?|don|doña|doctora|doctor|dra\.?|dr\.?|"
                       rf"licenciad[oa]|lcd[oa]\.?|ing\.?)\s+)(?P<nombre>{_NOMBRE})")
# rótulos de un documento de identidad (el OCR a veces pega las palabras: «APELLIDOSYNOMBRES»)
_ROTULO = re.compile(r"(?i)\b(?:apellidos?\s*y\s*nombres?|nombres?\s*y\s*apellidos?|nombres?\s*completos?|"
                     r"nombres?|apellidos?)\b\s*[:.-]?")
_OTRO_ROTULO = re.compile(r"(?i)^\s*(?:fecha|lugar|naciona|sexo|estado|c[eé]dula|firma|profesi|instrucci|condici|"
                          r"domicilio|direcci|nui|no\.|n[uú]mero|documento|tipo\s*de\s*sangre|donante)")
_NACIMIENTO = re.compile(r"(?im)(?P<et>fecha\s*de\s*nacimiento\s*[:.-]?)(?P<sep>[ \t]*\n?[ \t]*)(?P<valor>[^\n]*\d[^\n]*)")
_SOLO_LETRAS = re.compile(rf"^[{_MAY}{_MIN}\s.'-]{{3,}}$")
NOMBRES_COMUNES = set("""
juan jose luis carlos jorge miguel pedro diego david daniel andres fernando francisco javier ricardo roberto mario
manuel oscar pablo raul sergio victor edison edwin fabian cristian christian kevin bryan jonathan xavier santiago
sebastian mateo alejandro gabriel patricio marco marcos hugo cesar julio wilson washington segundo angel rafael
ramiro galo hernan alfredo eduardo enrique gustavo ivan jaime lenin freddy byron holger milton nelson rodrigo rolando
ruben vicente wilmer klever darwin stalin maria ana rosa carmen martha marta lucia patricia gabriela andrea daniela
fernanda veronica monica sandra silvia paola carla karla diana jessica johanna katherine alexandra mercedes gloria
elena laura sofia valentina camila isabel teresa beatriz cecilia cristina susana sonia nancy lorena mayra jenny
blanca piedad rocio ximena gladys margarita esther nelly norma alicia adriana carolina natalia paulina lourdes
tatiana viviana erika maribel janeth magdalena dolores fatima guadalupe
""".split())
_SECUENCIA = re.compile(rf"\b{_PALABRA}(?:\s+{_PALABRA}){{1,3}}\b")


def cedula_valida(digitos: str) -> bool:
    """Dígito verificador de la cédula ecuatoriana (módulo 10)."""
    if len(digitos) != 10 or not digitos.isdigit():
        return False
    suma = 0
    for i, d in enumerate(digitos[:9]):
        v = int(d) * (2 if i % 2 == 0 else 1)
        suma += v - 9 if v > 9 else v
    return (10 - suma % 10) % 10 == int(digitos[9])


def _cedulas(texto: str) -> str:
    """Una cédula y un celular 09… tienen 10 dígitos: es cédula si cuadra el dígito verificador o si el texto
    dice «cédula» justo antes; si no, se deja para la regla de teléfonos."""
    def cambiar(m: re.Match) -> str:
        digitos = re.sub(r"\D", "", m.group(0))
        antes = texto[max(0, m.start() - 30):m.start()]
        es_celular = digitos.startswith("09") and digitos[2] in "6789"
        if cedula_valida(digitos) or _CONTEXTO_CEDULA.search(antes) or not es_celular:
            return PROTEGIDO["cedula"]
        return m.group(0)
    return _CEDULA_FLEX.sub(cambiar, texto)


def _sin_tildes(t: str) -> str:
    return t.lower().translate(str.maketrans("áéíóúü", "aeiouu"))


def _nombres_en_rotulos(texto: str) -> str:
    """En un documento: lo que sigue a «APELLIDOS Y NOMBRES» (en la misma línea o en las dos siguientes)."""
    lineas, out, pendientes = texto.split("\n"), [], 0
    for linea in lineas:
        m = _ROTULO.search(linea)
        if m and not _OTRO_ROTULO.match(linea[m.end():]):
            resto = linea[m.end():].strip()
            if resto and _SOLO_LETRAS.match(resto):
                out.append(linea[:m.end()].rstrip() + " " + PROTEGIDO["nombre"])
                pendientes = 1
            else:
                out.append(linea)
                pendientes = 2
            continue
        if pendientes and _SOLO_LETRAS.match(linea.strip()) and not _OTRO_ROTULO.match(linea):
            if not out or not out[-1].endswith(PROTEGIDO["nombre"]):
                out.append(PROTEGIDO["nombre"])
            pendientes -= 1
            continue
        pendientes = 0
        out.append(linea)
    return "\n".join(out)


# Restos de copiar y pegar un mensaje del celular o del correo: «0990… (tel:0990…)»,
# «http://x.net (https://www.google.com/search?q=http://x.net)». Duplican el dato y no aportan nada.
_PEGADO = re.compile(r"[ \t]*\((?:tel|sms|mailto|callto):[^)\s]*\)"
                     r"|[ \t]*\(https?://(?:www\.)?google\.[a-z.]+/(?:search|url)\?[^)\s]*\)", re.I)


def limpiar_pegado(texto: str) -> str:
    return _PEGADO.sub("", texto or "")


def proteger(texto: str) -> str:
    """Texto escrito o que salió de una foto o nota de voz: cédulas, nombres, correos y teléfonos se reemplazan
    por etiquetas como [Cédula protegida] y [Nombre protegido]; la fecha de nacimiento de un documento sale como
    [Fecha protegida]. Lo demás se conserva tal cual."""
    t = PATRON_EMAIL.sub(PROTEGIDO["correo"], limpiar_pegado(texto))
    t = _cedulas(t)
    t = _CELULAR_FLEX.sub(PROTEGIDO["telefono"], t)
    t = _FIJO_FLEX.sub(PROTEGIDO["telefono"], t)
    t = _NACIMIENTO.sub(lambda m: m.group("et") + m.group("sep") + PROTEGIDO["fecha"], t)
    t = _nombres_en_rotulos(t)
    t = _PRESENTA.sub(lambda m: m.group("antes") + PROTEGIDO["nombre"], t)
    t = _SECUENCIA.sub(lambda m: PROTEGIDO["nombre"] if _sin_tildes(m.group(0).split()[0]) in NOMBRES_COMUNES
                       else m.group(0), t)
    return t


ETIQUETA_ADJUNTO = {"audio": "Nota de voz", "video": "Video", "imagen": "Foto"}


def texto_de_adjuntos(regs: list[dict]) -> str:
    """Lo que la persona contó por voz o con una foto, ya en texto protegido, para sumarlo a la denuncia."""
    partes = []
    for r in regs:
        nombre = ETIQUETA_ADJUNTO.get(r["tipo"], "Archivo")
        if r["estado"] == "procesado":
            partes.append(f"[{nombre}] {r['texto'] or '(sin texto reconocible)'}")
        else:
            partes.append(f"[{nombre}] Recibida. Se pasará a texto cuando el equipo tenga instalada la lectura local.")
    return "\n\n".join(partes)


def unir(escrita: str, de_adjuntos: str) -> str:
    return "\n\n".join(x for x in (escrita.strip(), de_adjuntos.strip()) if x)


def completar_texto(codigo: str, de_adjuntos: str) -> dict:
    """Cuando una nota de voz se pasa a texto después, la denuncia se actualiza (nueva línea, solo agregar)."""
    d = dict(una(codigo))
    d["descripcion"] = unir(d.get("descripcion_escrita", ""), de_adjuntos)
    estado.agregar("denuncias", d)
    estado.bitacora("Sentinel Salud", "Canal de denuncias", "Archivo pasado a texto", codigo,
                    "Se sumó a la denuncia el texto protegido de un archivo pendiente")
    return d


def crear(datos: dict, origen: str = "ciudadano") -> dict:
    codigo = "DN-" + secrets.token_hex(3).upper()
    # Al SOC solo le llega lo que pasó: ningún dato personal, ni siquiera una parte (nada de «17***»).
    escrita = proteger((datos.get("descripcion") or "").strip())
    sospechoso = (datos.get("contacto_sospechoso") or "").strip()
    enlace = (datos.get("enlace") or "").strip()
    reg = {
        "codigo": codigo, "fecha": estado.ahora(), "origen": origen, "tipo": datos["tipo"],
        "tipo_texto": TIPOS[datos["tipo"]], "descripcion_escrita": escrita,
        "descripcion": unir(escrita, datos.get("texto_adjuntos") or ""),
        "cuando": datos.get("cuando") or "", "medio": datos.get("medio") or "",
        "contacto_sospechoso_ref": _ref_contacto(sospechoso) if sospechoso else "",
        "contacto_sospechoso_mascara": _enmascarar(sospechoso) if sospechoso else "",
        "enlace": enlace, "verificacion": verificar.enlace(enlace) if enlace else None,
        "adjuntos": list(dict.fromkeys(datos.get("adjuntos") or []))[:MAX_ADJUNTOS],
        "reportado_por": datos.get("usuario", "") if origen != "ciudadano" else "", "estado": "recibida",
        "respuesta_publica": "Recibimos tu denuncia. El equipo de seguridad la revisará.",
        "nota_interna": "", "gestionado_por": "",
    }
    estado.agregar("denuncias", reg)
    estado.bitacora("Ciudadanía" if origen == "ciudadano" else datos.get("actor", "Personal de salud"),
                    "Canal de denuncias", "Denuncia recibida", codigo, reg["tipo_texto"])
    return reg


def todas() -> list[dict]:
    return sorted(estado.ultimo_por("denuncias", "codigo").values(), key=lambda d: d["fecha"], reverse=True)


def una(codigo: str) -> dict:
    d = estado.ultimo_por("denuncias", "codigo").get(codigo)
    if not d:
        raise HTTPException(404, "No encontramos una denuncia con ese código. Revisa que esté bien escrito.")
    return d


def publica(codigo: str) -> dict:
    d = una(codigo)
    return {"codigo": d["codigo"], "fecha": d["fecha"], "tipo": d["tipo_texto"], "estado": ESTADOS[d["estado"]],
            "respuesta": d["respuesta_publica"]}


def gestionar(codigo: str, nuevo_estado: str, respuesta: str, nota: str, actor: str, rol: str) -> dict:
    d = dict(una(codigo))
    d.update(estado=nuevo_estado, respuesta_publica=respuesta or d["respuesta_publica"], nota_interna=nota,
             gestionado_por=actor, actualizado=estado.ahora())
    estado.agregar("denuncias", d)
    estado.bitacora(actor, rol, "Denuncia gestionada", codigo, f"Estado: {ESTADOS[nuevo_estado]}")
    return d


def contactos_reportados() -> dict[str, list[str]]:
    """Seudónimo de contacto -> códigos de denuncia que lo mencionan (para el patrón HG-07)."""
    out: dict[str, list[str]] = {}
    for d in todas():
        if d["contacto_sospechoso_ref"] and d["estado"] != "descartada":
            out.setdefault(d["contacto_sospechoso_ref"], []).append(d["codigo"])
    return out
