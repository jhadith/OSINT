"""Puntaje de riesgo (probabilidad x impacto, 1-25), gravedad y textos para el analista. Sin nombres de personas."""
from __future__ import annotations

from .hallazgo import Hallazgo

IMPACTO = {"T1048": 5, "T1213": 5, "T1078": 5, "T1021.004": 4, "T1098": 4, "T1110": 3, "T1046": 3}

# orden de precedencia para nombrar un hallazgo que junta varias reglas
TIPOS = ["cuenta_rara", "rafaga_ssh", "extraccion_masiva", "escaneo", "fuerza_bruta", "fallidos_masivos",
         "rafaga_conexiones", "servicios_inseguros", "cuentas_compartidas", "administracion_concentrada", "ml"]

TITULO = {
    "cuenta_rara": "Cuenta fantasma con descarga de datos",
    "extraccion_masiva": "Extracción masiva de datos del sistema médico",
    "rafaga_ssh": "Posible fuga de datos por SSH",
    "escaneo": "Escaneo de servicios del servidor médico",
    "fuerza_bruta": "Fuerza bruta contra el servidor médico",
    "fallidos_masivos": "Accesos fallidos masivos en el sistema médico",
    "rafaga_conexiones": "Ráfaga de conexiones hacia el servidor médico",
    "servicios_inseguros": "Servicios sin cifrado permitidos (Telnet, SMBv1, NetBIOS)",
    "cuentas_compartidas": "Cuentas usadas por muchas personas",
    "administracion_concentrada": "Acciones administrativas concentradas en pocas cuentas",
    "ml": "Comportamiento anómalo detectado por el modelo",
}
RIESGO = {"cuenta_rara": "R1", "cuentas_compartidas": "R1", "extraccion_masiva": "R2", "rafaga_ssh": "R2",
          "servicios_inseguros": "R3", "fuerza_bruta": "R4", "fallidos_masivos": "R4", "rafaga_conexiones": "R5",
          "ml": "R5", "administracion_concentrada": "R6", "escaneo": "R7"}
CID = {"cuenta_rara": ["Confidencialidad"], "extraccion_masiva": ["Confidencialidad"],
       "rafaga_ssh": ["Confidencialidad"], "escaneo": ["Confidencialidad", "Disponibilidad"],
       "fuerza_bruta": ["Confidencialidad", "Disponibilidad"], "fallidos_masivos": ["Confidencialidad", "Disponibilidad"],
       "rafaga_conexiones": ["Disponibilidad"], "servicios_inseguros": ["Confidencialidad", "Disponibilidad"],
       "cuentas_compartidas": ["Confidencialidad", "Integridad"], "administracion_concentrada": ["Integridad"],
       "ml": ["Confidencialidad"]}
HIPAA = {"cuenta_rara": "Control de acceso", "cuentas_compartidas": "Control de acceso",
         "fuerza_bruta": "Autenticación", "fallidos_masivos": "Autenticación", "escaneo": "Autenticación",
         "rafaga_ssh": "Seguridad en la transmisión", "extraccion_masiva": "Seguridad en la transmisión",
         "servicios_inseguros": "Seguridad en la transmisión", "administracion_concentrada": "Integridad"}


def tipo(h) -> str:
    """Tipo principal de un hallazgo (o de una regla en texto)."""
    partes = (h if isinstance(h, str) else h.regla).split("+")
    for t in TIPOS:
        if any(p.startswith(t) for p in partes):
            return t
    if any(p.startswith("ml_") for p in partes):
        return "ml"
    return "rafaga_conexiones"


def puntaje(h: Hallazgo) -> tuple[int, int]:
    impacto = max([IMPACTO.get(t, 2) for t in h.tecnicas] or [2])
    if h.fuente == "correlacion":
        prob = 5
    elif h.eventos_fw + h.eventos_med >= 1000:
        prob = 4
    else:
        prob = 3
    if h.segmento:
        prob = min(5, prob + 1)
    return prob, impacto


def gravedad(p: int) -> str:
    return "Crítica" if p >= 20 else "Alta" if p >= 10 else "Media" if p >= 5 else "Baja"


def duracion(seg: int) -> str:
    if seg < 1:
        return "menos de 1 s"
    if seg < 120:
        return f"{seg} s"
    if seg < 7200:
        return f"{round(seg / 60)} min"
    return f"{round(seg / 3600)} h"


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def eventos(n) -> str:
    return "1 evento" if int(n) == 1 else f"{miles(n)} eventos"


def _acciones_txt(acc: dict) -> str:
    return ", ".join(f"{miles(v)} {k.lower()}" for k, v in list(acc.items())[:4])


def resumen(h: Hallazgo, t: str) -> str:
    ev = h.evidencia
    efw = ev.get("firewall", ev if h.fuente == "firewall" else {})
    emed = ev.get("sistema_medico", ev if h.fuente == "sistema_medico" else {})
    if t == "servicios_inseguros":
        return (f"{miles(ev['permitidas_total'])} conexiones permitidas por servicios sin cifrado en el periodo, "
                f"{miles(ev['permitidas_al_servidor'])} de ellas hacia el servidor médico.")
    if t == "cuentas_compartidas":
        return (f"{ev['cuentas']} cuentas aparecen con 50 o más nombres de persona distintos; la que más tiene "
                f"llega a {miles(ev['max_nombres'])}. Una cuenta típica tiene {ev['mediana_nombres_por_cuenta']:.0f}.")
    if t == "administracion_concentrada":
        return (f"{ev['cuentas']} cuentas hacen alguna acción administrativa (activar, inactivar o cambiar nivel de "
                f"usuarios) cinco o más veces por encima de la cuenta típica.")
    partes = []
    if t == "cuenta_rara":
        partes.append(f"La cuenta {h.cuenta} solo tiene {emed.get('eventos_en_el_mes', h.eventos_med)} eventos en todo "
                      f"el mes: {_acciones_txt(emed.get('acciones', {}))}, en {duracion(emed.get('duracion_seg', 0))}.")
    if efw and efw.get("eventos"):
        puertos = ", ".join(map(str, efw.get("puertos", [])))
        detalle = (f"{miles(efw['negados'])} negados y {miles(efw['permitidos'])} permitidos" if "negados" in efw
                   else efw.get("accion", ""))
        partes.append(f"Firewall: {eventos(efw['eventos'])} desde {h.ip or 'una IP'} hacia el servidor médico "
                      f"en {duracion(efw.get('duracion_seg', 0))}, puerto {puertos} ({detalle}).")
    if emed and t != "cuenta_rara" and emed.get("eventos"):
        partes.append(f"Sistema médico: la cuenta {h.cuenta} registró {_acciones_txt(emed.get('acciones', {}))} "
                      f"en {duracion(emed.get('duracion_seg', 0))}.")
    if h.desfase_h:
        partes.append(f"El reloj del firewall está desfasado {abs(h.desfase_h)} h respecto del sistema médico.")
    if h.segmento:
        partes.append("La IP de origen está en el mismo segmento de red que el servidor médico.")
    if t == "ml":
        m = h.ml.get("fw") or h.ml.get("med") or {}
        partes.append(f"Ninguna regla la confirma. Variables más raras: {m.get('por_que', '')}.")
        return " ".join(partes)
    for clave, nombre in (("fw", "firewall"), ("med", "sistema médico")):
        m = h.ml.get(clave, {})
        if m.get("puesto"):
            partes.append(f"El modelo puso esta ventana del {nombre} en el puesto {miles(m['puesto'])} de "
                          f"{miles(m['de'])}.")
    return " ".join(partes)


def acciones(h: Hallazgo, t: str) -> list[str]:
    ip, c = h.ip, h.cuenta
    base = {
        "cuenta_rara": [f"Suspender la cuenta {c}", "Revisar quién creó la cuenta y con qué permisos"],
        "extraccion_masiva": [f"Suspender la cuenta {c}", "Revisar qué historias clínicas se transfirieron"],
        "rafaga_ssh": ["Restringir SSH hacia el servidor a equipos de administración"],
        "escaneo": ["Cerrar los puertos innecesarios del servidor", "Activar la regla Sigma de escaneo"],
        "fuerza_bruta": ["Bloqueo por intentos fallidos y MFA", "Bloquear Telnet hacia el servidor"],
        "fallidos_masivos": [f"Bloquear temporalmente la cuenta {c}", "Bloqueo por intentos fallidos y MFA"],
        "rafaga_conexiones": ["Revisar el origen del tráfico"],
        "servicios_inseguros": ["Bloquear Telnet, SMBv1 y NetBIOS hacia el servidor médico"],
        "cuentas_compartidas": ["Asignar cada cuenta a una sola persona o eliminarla"],
        "administracion_concentrada": ["Doble aprobación para cambios de privilegio",
                                       "Revisar los cambios hechos en el periodo"],
        "ml": ["Revisar la ventana marcada por el modelo"],
    }[t]
    extra = []
    if ip:
        extra.append(f"Aislar y revisar el equipo {ip}")
    if t in ("cuenta_rara", "extraccion_masiva", "rafaga_ssh") and not h.general:
        extra.append("Preservar evidencia y evaluar la notificación de vulneración (LOPDP)")
    if h.desfase_h:
        extra.append("Sincronizar los relojes del firewall y del sistema médico (NTP)")
    return base + extra
