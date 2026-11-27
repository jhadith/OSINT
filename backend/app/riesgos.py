"""Matriz de riesgos dinámica: el impacto lo define el negocio y la probabilidad la calculan los datos del análisis activo.

Escala de probabilidad (1-5) según la evidencia vigente:
  1  sin evidencia en este análisis
  2  solo señales débiles (alertas bajas del modelo, observaciones)
  3  debilidad de configuración presente (exposición)
  4  ataque o caso de gravedad alta
  5  caso crítico, o dos o más casos altos
Un caso que el analista descarta deja de contar; uno confirmado cuenta como crítico. Así la matriz cambia con cada
dataset y con cada decisión.
"""
from __future__ import annotations

from . import datos

RIESGOS = [
    ("R1", "Acceso indebido a historias clínicas", 5, "Cuentas nominales, eliminar las genéricas y regla de cuenta de un solo uso"),
    ("R2", "Fuga de datos de salud", 5, "Restringir SSH, regla de ráfaga SSH y evaluar la notificación (LOPDP)"),
    ("R3", "Ransomware que detiene la atención", 5, "Bloquear SMBv1 y Telnet, respaldos y segmentación"),
    ("R4", "Robo de credenciales por fuerza bruta", 3, "Bloqueo por intentos, MFA y reglas Sigma 01 y 04"),
    ("R5", "Movimiento lateral desde el segmento del servidor", 4, "Revisar los equipos del segmento y microsegmentar"),
    ("R6", "Alteración de permisos y registros", 4, "Doble aprobación para cambios de privilegio"),
    ("R7", "Escaneo de servicios del servidor", 3, "Regla Sigma 02 y cierre de puertos innecesarios"),
    ("R8", "Registros poco confiables para investigar", 3, "Sincronizar relojes (NTP) y usar un formato único"),
    ("R9", "Acaparamiento y reventa de citas", 4, "Confirmación con el afiliado, límite por origen y revisión humana"),
    ("R10", "Falsas alertas que dificulten la atención legítima", 4, "Validación HBVF, explicaciones legítimas y nada automático"),
    ("R11", "Asociación errónea de sesiones o divulgación de contactos", 4, "Contactos seudonimizados y puntos como hipótesis"),
]
TIPO_A_RIESGO = {"cuenta_rara": ["R1"], "rafaga_ssh": ["R2"], "extraccion_masiva": ["R2"], "fuerza_bruta": ["R4"],
                 "fallidos_masivos": ["R4"], "escaneo": ["R7"]}
GRAV = {"critica": 5, "alta": 4, "media": 3, "baja": 2}


def calcular() -> list[dict]:
    ev: dict[str, list[tuple[int, str, str | None]]] = {r[0]: [] for r in RIESGOS}

    def sumar(rid, nivel, texto, caso=None):
        ev[rid].append((nivel, texto, caso))

    for c in datos.casos():
        if c["estado"] == "descartado":
            continue
        nivel = 5 if c["estado"] == "confirmado" else GRAV[c["gravedad"]]
        texto = f"{c['id']} {c['titulo'].lower()}" + (" (confirmado)" if c["estado"] == "confirmado" else "")
        for rid in c["riesgos"]:
            if rid in ev:
                sumar(rid, nivel if rid not in ("R5", "R8") else min(nivel, 4), texto, c["id"])
    for a in datos.motor("alertas.json", []):
        t = a.get("tipo", "")
        if t == "servicios_inseguros":
            sumar("R3", 3, f"{a['eventos_firewall']:,} conexiones sin cifrado permitidas".replace(",", "."))
        elif t == "cuentas_compartidas":
            sumar("R1", 3, "Cuentas genéricas usadas por muchas personas")
        elif t == "administracion_concentrada":
            sumar("R6", 3, "Acciones administrativas concentradas en pocas cuentas")
        elif t == "ml" and a["gravedad"] == "Baja":
            sumar("R5", 2, "Comportamiento anómalo señalado por el modelo")
    cal = datos.motor("resumen_motor.json", {}).get("calidad", {})
    if cal.get("ip_mal_escrita_sistema_medico"):
        sumar("R8", 3, f"{cal['ip_mal_escrita_sistema_medico']:,} registros con IP mal escrita".replace(",", "."))
    ag = datos.agendamiento()
    if ag:
        rev = [c for c in ag["casos"] if c["review_required"] and not c["status"].startswith("Indeterminado")]
        if rev:
            sumar("R9", 5 if any(c["status"] == "Revisión prioritaria" for c in rev) else 4,
                  f"{len(rev)} orígenes de agendamiento requieren revisión")
        indet = [c for c in ag["casos"] if c["status"].startswith("Indeterminado") or c["status"] == "Observación"]
        sumar("R10", 2, f"{len(indet)} orígenes en observación o sin información suficiente")
        sumar("R11", 2, "Agrupaciones por contacto, huella o red tratadas como hipótesis")
    out = []
    for rid, nombre, impacto, trat in RIESGOS:
        e = ev[rid]
        if not e:
            prob = 1
        else:
            prob = max(n for n, _, _ in e)
            if prob == 4 and sum(1 for n, _, _ in e if n >= 4) >= 2:
                prob = 5
        out.append({"id": rid, "nombre": nombre, "probabilidad": prob, "impacto": impacto, "nivel": prob * impacto,
                    "tratamiento": trat, "evidencia": [t for _, t, _ in e] or ["Sin evidencia en este análisis"],
                    "casos": sorted({c for _, _, c in e if c})})
    return out
