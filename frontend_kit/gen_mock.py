import hashlib
import json
from pathlib import Path

M = Path("api_mock")
def cod(p, s): return f"{p}-" + hashlib.sha256(("mock" + s).encode()).hexdigest()[:6].upper()
def aid(s): return "A-" + hashlib.sha256(s.encode()).hexdigest()[:8].upper()

MITRE = {"T1110": ("Fuerza bruta", "Acceso a credenciales"),
         "T1046": ("Descubrimiento de servicios de red", "Descubrimiento"),
         "T1021.004": ("Servicios remotos: SSH", "Movimiento lateral"),
         "T1048": ("Exfiltración por protocolo alternativo", "Exfiltración"),
         "T1078": ("Cuentas válidas", "Acceso inicial"),
         "T1098": ("Manipulación de cuentas", "Persistencia"),
         "T1213": ("Datos de repositorios de información", "Recolección")}

def linea(eventos):
    return [{"fecha_hora": t, "fuente": f, "evento": e, "cantidad": n} for t, f, e, n in eventos]

alertas = [
 dict(caso="Caso 3", regla="rafaga_ssh+sistema_medico", titulo="Posible fuga de datos por SSH", gravedad="Crítica",
      puntaje=20, fuente="correlacion", inicio="2026-10-07 13:00:00", fin="2026-10-07 13:00:01",
      ip_origen="10.10.100.50", cuenta="XYZ1111331", usuario_firewall=cod("U","c3u"), persona=cod("P","c3p"),
      tecnicas=["T1021.004","T1048"], eventos_firewall=30, eventos_sistema_medico=3000,
      resumen="30 conexiones SSH permitidas en 1 s hacia el servidor médico; en el sistema médico, 30 transferencias exitosas y 2.970 interrumpidas.",
      acciones=["Bloquear SSH desde 10.10.100.50", "Suspender la cuenta XYZ1111331", "Aislar el equipo y preservar evidencia", "Evaluar la notificación de vulneración (LOPDP)"],
      riesgo="R2", cid=["Confidencialidad"],
      linea=linea([("2026-10-07 13:00:00","Firewall","SSH puerto 22 permitido",15),("2026-10-07 13:00:01","Firewall","SSH puerto 22 permitido",15),
                   ("2026-10-07 13:00:00","Sistema médico","Transferencia exitosa",30),("2026-10-07 13:00:00","Sistema médico","Transferencia interrumpida",2970)])),
 dict(caso="Caso 4", regla="cuenta_rara+firewall", titulo="Cuenta fantasma con descarga", gravedad="Crítica",
      puntaje=25, fuente="correlacion", inicio="2026-10-24 10:40:00", fin="2026-10-24 10:40:15",
      ip_origen="10.10.100.40", cuenta="WXY1210010", usuario_firewall=cod("U","c4u"), persona=cod("P","c4p"),
      tecnicas=["T1078","T1021.004","T1213"], eventos_firewall=1, eventos_sistema_medico=2,
      resumen="La cuenta solo tiene 2 eventos en el mes: ingreso y descarga en 15 s. En el firewall hay 1 conexión SSH permitida desde la misma IP, con el reloj desfasado 12 h.",
      acciones=["Suspender la cuenta WXY1210010", "Aislar el equipo 10.10.100.40", "Revisar quién creó la cuenta", "Evaluar la notificación de vulneración (LOPDP)"],
      riesgo="R1", cid=["Confidencialidad"],
      linea=linea([("2026-10-24 10:40:00","Sistema médico","Ingreso al sistema",1),("2026-10-24 10:40:15","Sistema médico","Descarga",1),
                   ("2026-10-24 22:40:05","Firewall","SSH puerto 22 permitido (reloj +12 h)",1)])),
 dict(caso="Caso 1", regla="fuerza_bruta", titulo="Fuerza bruta por Telnet", gravedad="Alta",
      puntaje=15, fuente="correlacion", inicio="2026-10-10 00:00:00", fin="2026-10-10 00:05:00",
      ip_origen="10.10.100.10", cuenta="XYZ9999021", usuario_firewall=cod("U","c1u"), persona=cod("P","c1p"),
      tecnicas=["T1110"], eventos_firewall=2000, eventos_sistema_medico=2000,
      resumen="2.000 intentos por Telnet en 5 min desde una IP del segmento del servidor; 2.000 accesos fallidos en el sistema médico.",
      acciones=["Bloquear Telnet hacia el servidor", "Bloqueo por intentos fallidos y MFA", "Revisar el equipo 10.10.100.10"],
      riesgo="R4", cid=["Confidencialidad","Disponibilidad"],
      linea=linea([("2026-10-10 00:00:00","Firewall","Telnet puerto 23 negado",400),("2026-10-10 00:01:00","Firewall","Telnet puerto 23 negado",400),
                   ("2026-10-10 00:02:00","Firewall","Telnet puerto 23 negado",400),("2026-10-10 00:03:00","Firewall","Telnet puerto 23 negado",400),
                   ("2026-10-10 00:04:00","Firewall","Telnet puerto 23 negado",400),("2026-10-10 00:00:00","Sistema médico","Acceso fallido",2000)])),
 dict(caso="Caso 2", regla="escaneo", titulo="Escaneo de servicios del servidor", gravedad="Alta",
      puntaje=12, fuente="correlacion", inicio="2026-10-19 14:10:00", fin="2026-10-19 14:10:58",
      ip_origen="10.10.100.20", cuenta="RIMODE1", usuario_firewall=cod("U","c2u"), persona=cod("P","c2p"),
      tecnicas=["T1046","T1110"], eventos_firewall=1000, eventos_sistema_medico=1000,
      resumen="1.000 intentos contra 4 servicios distintos en 58 s; 1.000 accesos fallidos en el sistema médico.",
      acciones=["Cerrar puertos innecesarios del servidor", "Activar la regla Sigma 02", "Revisar el equipo 10.10.100.20"],
      riesgo="R7", cid=["Confidencialidad","Disponibilidad"],
      linea=linea([("2026-10-19 14:10:00","Firewall","Intentos a 4 servicios negados",1000),("2026-10-19 14:10:00","Sistema médico","Acceso fallido",1000)])),
 dict(caso=None, regla="servicios_inseguros", titulo="Servicios sin cifrado permitidos (Telnet, SMBv1, NetBIOS)", gravedad="Media",
      puntaje=9, fuente="firewall", inicio="2026-10-01 00:00:00", fin="2026-10-31 23:59:59",
      ip_origen="", cuenta="", usuario_firewall="", persona="", tecnicas=[], eventos_firewall=744767, eventos_sistema_medico=0,
      resumen="744.767 conexiones permitidas por servicios inseguros durante el mes.",
      acciones=["Bloquear Telnet, SMBv1 y NetBIOS hacia el servidor médico"], riesgo="R3", cid=["Confidencialidad","Disponibilidad"], linea=[]),
 dict(caso=None, regla="cuentas_genericas", titulo="Cuentas genéricas compartidas por muchas personas", gravedad="Media",
      puntaje=9, fuente="sistema_medico", inicio="2026-10-01 00:00:00", fin="2026-10-31 23:59:59",
      ip_origen="", cuenta="XYZ9999xxx", usuario_firewall="", persona="", tecnicas=["T1078"], eventos_firewall=0, eventos_sistema_medico=0,
      resumen="Cuentas genéricas usadas con hasta 1.929 nombres de persona distintos.",
      acciones=["Asignar cada cuenta a una persona o eliminarla"], riesgo="R1", cid=["Confidencialidad","Integridad"], linea=[]),
 dict(caso=None, regla="cambios_privilegios", titulo="Cambios de permisos y activaciones masivas", gravedad="Media",
      puntaje=8, fuente="sistema_medico", inicio="2026-10-01 00:00:00", fin="2026-10-31 23:59:59",
      ip_origen="", cuenta="MINAD, CMAP09002", usuario_firewall="", persona="", tecnicas=["T1098"], eventos_firewall=0, eventos_sistema_medico=1229,
      resumen="131 cambios de nivel de usuario (MINAD) y 1.098 activaciones de usuarios (CMAP09002).",
      acciones=["Doble aprobación para cambios de privilegio", "Revisar los cambios hechos en octubre"], riesgo="R6", cid=["Integridad"], linea=[]),
]
for a in alertas:
    a["id"] = aid(a["regla"] + a["inicio"])
    a["estado"] = "pendiente"
    a["tecnicas_detalle"] = [{"id": t, "nombre": MITRE[t][0], "tactica": MITRE[t][1]} for t in a["tecnicas"]]
    a["aviso_telegram"] = a["gravedad"] == "Crítica"

def w(nombre, obj):
    p = M / nombre; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

campos_lista = ["id","caso","titulo","gravedad","puntaje","fuente","inicio","fin","ip_origen","cuenta","tecnicas","estado","aviso_telegram"]
w("alertas.json", [{k: a[k] for k in campos_lista} for a in alertas])
for a in alertas: w(f"alertas/{a['id']}.json", a)

w("mitre.json", [{"id": t, "nombre": n, "tactica": ta, "alertas": sum(t in a["tecnicas"] for a in alertas)} for t,(n,ta) in MITRE.items()])

w("riesgos.json", [dict(id=i, riesgo=r, probabilidad=p, impacto=im, nivel=p*im, categoria=c, tratamiento=t) for i,r,p,im,c,t in [
 ("R1","Acceso indebido a historias clínicas",4,5,"Crítico","Cuentas nominales y regla de cuenta de un solo uso"),
 ("R2","Fuga de datos de salud",4,5,"Crítico","Restringir SSH y regla de ráfaga SSH"),
 ("R3","Ransomware que detiene la atención",3,5,"Alto","Bloquear SMBv1 y Telnet, respaldos y segmentación"),
 ("R4","Robo de credenciales por fuerza bruta",5,3,"Alto","Bloqueo por intentos y MFA"),
 ("R5","Movimiento lateral desde el segmento del servidor",4,4,"Alto","Revisar equipos 10.10.100.x y microsegmentar"),
 ("R6","Alteración de permisos y registros",3,4,"Alto","Doble aprobación para cambios de privilegio"),
 ("R7","Escaneo de servicios del servidor",4,3,"Alto","Regla Sigma 02 y cierre de puertos"),
 ("R8","Registros poco confiables para investigar",3,3,"Medio","Sincronizar relojes (NTP)")]])

CONTROLES = [
 ("5.7 Inteligencia de amenazas","Toda la plataforma","Se implementa"),
 ("5.9 Inventario de activos","Inventario de activos de información","Propuesto"),
 ("5.15, 5.16 y 5.18 Acceso, identidades y derechos","Cuentas genéricas y cuenta de un solo uso","Brecha"),
 ("5.17 y 8.5 Autenticación","Fuerza bruta de los casos 1 y 2","Brecha"),
 ("5.24 a 5.28 Gestión de incidentes","Casos 3 y 4","Propuesto"),
 ("5.34 Privacidad y datos personales","Seudónimos y LOPDP","Cubierto"),
 ("8.2 Accesos privilegiados","131 cambios de nivel de usuario","Brecha"),
 ("8.7 y 8.13 Malware y respaldos","Riesgo de ransomware","Por verificar"),
 ("8.11 Enmascaramiento de datos","Seudónimos en reportes y tableros","Cubierto"),
 ("8.12 Prevención de fuga de datos","Caso 3","Brecha"),
 ("8.15 y 8.16 Registro y monitoreo","Reglas y machine learning","Se implementa"),
 ("8.17 Sincronización de relojes","12 horas de diferencia en el caso 4","Brecha"),
 ("8.20 a 8.22 Redes y segregación","Servicios inseguros permitidos; atacantes junto al servidor","Brecha"),
 ("8.25 y 8.28 Desarrollo seguro","Ciclo DevSecOps","Cubierto")]
w("controles.json", [dict(control=c, hallazgo=h, estado=e) for c,h,e in CONTROLES])

grav = {g: sum(a["gravedad"] == g for a in alertas) for g in ["Crítica","Alta","Media","Baja"]}
w("resumen.json", {
  "periodo": {"desde": "2026-10-01", "hasta": "2026-10-31"},
  "generado": "2026-11-26 15:00:00",
  "registros": {"firewall": 5009031, "sistema_medico": 5014501, "total": 10023532},
  "tiempo_analisis_min": 2.8,
  "alertas_por_gravedad": grav,
  "ataques_confirmables": 4, "criticas_pendientes": grav["Crítica"],
  "cuentas_sospechosas": 16, "conexiones_inseguras": 744767,
  "brechas_hipaa": 5, "grupos_controles_con_brecha": sum(e == "Brecha" for _,_,e in CONTROLES),
  "por_cid": {"Confidencialidad": 6, "Integridad": 2, "Disponibilidad": 3},
  "por_dia": [{"fecha": d, "Crítica": c, "Alta": h} for d, c, h in
              [("2026-10-07",1,0),("2026-10-10",0,1),("2026-10-19",0,1),("2026-10-24",1,0)]]})

w("ml.json", {"modelo": "Isolation Forest", "random_state": 42,
  "usuarios_firewall": [dict(puesto=i+1, usuario=cod("U",f"c{c}u"), puntaje=s, explicacion=e) for i,(c,s,e) in enumerate([
      (3,0.31,"conexiones SSH por segundo, % permitidas al servidor, horas activas"),
      (1,0.29,"intentos negados, uso de Telnet, ráfaga en 5 min"),
      (2,0.27,"puertos distintos, intentos negados, ráfaga en 58 s")])],
  "total_usuarios_firewall": 934,
  "cuentas_sistema_medico": [dict(puesto=i+1, cuenta=c, puntaje=round(0.33-i*0.01,2)) for i,c in enumerate(
      ["XYZ1111331","XYZ9999021","RIMODE1","MINAD","CMAP09002"])],
  "total_cuentas": 10016, "cuentas_sospechosas": 16})

w("iocs.json", {"ips": [dict(valor=a["ip_origen"], alerta=a["id"], tecnicas=a["tecnicas"]) for a in alertas if a["ip_origen"]],
  "cuentas": [dict(valor=a["cuenta"], alerta=a["id"]) for a in alertas if a["caso"]],
  "reglas_sigma": [dict(archivo=f, titulo=t) for f,t in [
      ("01_fuerza_bruta_hacia_el_sistema_medico.yml","Fuerza bruta hacia el sistema médico"),
      ("02_escaneo_de_servicios_del_servidor_medico.yml","Escaneo de servicios del servidor médico"),
      ("03_rafaga_ssh_permitida_hacia_el_servidor_medico.yml","Ráfaga SSH permitida hacia el servidor médico"),
      ("04_accesos_fallidos_masivos_en_el_sistema_medico.yml","Accesos fallidos masivos en el sistema médico"),
      ("05_servicio_inseguro_permitido.yml","Servicio inseguro permitido")]],
  "descargas": {"stix": "/api/exportes/stix", "misp": "/api/exportes/misp", "sigma": "/api/exportes/sigma"}})

w("bitacora.json", {"decisiones": [],
  "avisos_telegram": [dict(fecha_envio="2026-11-26 15:00:05", alerta=a["id"], estado="simulado") for a in alertas if a["gravedad"]=="Crítica"]})
print(len(alertas), "alertas")
