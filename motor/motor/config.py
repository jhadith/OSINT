"""Parámetros del motor. Los umbrales están calibrados con lo que mostró el análisis de octubre de 2026:
el tráfico normal llega desde IPs casi únicas (máximo 7 eventos por IP en el mes) y cada cuenta del sistema médico
tiene ~500 eventos al mes repartidos al azar entre 9 acciones (máximo 83 accesos fallidos en el mes)."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
SALIDAS = RAIZ / "salidas"
RESTRINGIDO = RAIZ / "restringido"
ARCHIVO_FW = DATOS / "Registros_conexiones_FW_10_2026.csv"
ARCHIVO_MED = DATOS / "Registros_conexiones_sist_med_iess.csv"
REDES = Path(__file__).resolve().parent / "datos_fijos" / "redes_ejemplo.csv"
TAM_PARTE = 500_000
ESTRICTO = False                   # True en las pruebas: un error en la salida de la consola detiene el motor

SERVIDOR = "10.10.100.30"
SEGMENTO_SERVIDOR = "10.10.100."   # equipos en el mismo segmento que el servidor médico
EPOCA = "2020-01-01"               # origen de los segundos internos (int32 alcanza hasta 2088)

# --- Firewall: ráfagas por IP de origen hacia el servidor ---
RAFAGA_IP_SEG, RAFAGA_IP_MIN = 300, 100      # >= 100 intentos en 5 min desde una IP
RAFAGA_SSH_SEG, RAFAGA_SSH_MIN = 5, 20       # >= 20 SSH permitidos en 5 s desde una IP
ESCANEO_PUERTOS_MIN = 3                      # una ráfaga contra >= 3 puertos distintos es escaneo
FUERZA_BRUTA_PCT_NEGADO = 0.8                # una ráfaga con >= 80 % negado contra 1-2 puertos es fuerza bruta
PUERTOS_SSH = {22}
PUERTOS_INSEGUROS = {23: "Telnet", 445: "SMBv1", 137: "NetBIOS", 138: "NetBIOS", 139: "NetBIOS"}

# --- Sistema médico ---
FALLIDOS_SEG, FALLIDOS_MIN = 86_400, 100     # >= 100 accesos fallidos de una cuenta en 24 h
MASIVO_SEG, MASIVO_MIN = 60, 20              # >= 20 transferencias o descargas de una cuenta en 1 min
CUENTA_RARA_MAX = 5                          # cuenta con <= 5 eventos en el mes...
PATRON_SENSIBLE = r"DESCARGA|TRANSFER|TRANFER|EXPORT"   # ...y alguna acción que saca datos
PATRON_FALLIDO = r"FALLID"
PATRON_ADMIN = r"nivel|activ|inactiv|reactiv|permiso|rol"
NOMBRES_CUENTA_COMPARTIDA = 50               # una cuenta usada con >= 50 nombres distintos es compartida
ADMIN_VECES_MEDIANA = 5                      # una acción administrativa >= 5 veces la mediana por cuenta

# --- Correlación ---
CORRELACION_TOLERANCIA_SEG = 600             # +-10 min entre firewall y sistema médico
DESFASES_HORAS = (0, -12, 12)                # relojes de las fuentes desfasados hasta 12 h

# --- Machine learning ---
SEMILLA = 42
ML_TOP = 10
ML_ALERTA_PUNTAJE = 95                       # ventanas con puntaje >= 95 sin regla que las explique
ML_ALERTAS_MAX = 3

# --- Agendamiento médico (HBVF, informe apartado 14) ---
CITAS_REDES_OCULTAS = {"nube", "vpn"}
CITAS_CADENA_MIN = 5               # sesiones seguidas a <= 5 min con la misma huella y red
CITAS_CADENA_PREVALENCIA = 0.05    # ...si esa combinación no es de las comunes
CITAS_CADENA_SESIONES = 3          # cadena: >= 3 sesiones seguidas con IPs distintas
CITAS_REASIGNACION_SEG = 600       # cancelada y reservada para otro paciente en <= 10 min (HG-05)
CITAS_HORA_APERTURA = 7            # hora en que se abre la agenda (HG-04)
CITAS_AL_ABRIR = 3                 # reservas en los primeros minutos de apertura
CITAS_MINUTOS_APERTURA = 5
CITAS_PACIENTES_SEMANA = 4         # más de 4 pacientes distintos por semana (HG-01)
CITAS_LIMITE_30_DIAS = 10          # límite institucional anunciado: 10 citas en 30 días
CITAS_IPS_ROTACION = 5             # HG-06
CITAS_RESPUESTA_HUMANA_MS = 1500   # HG-02
CITAS_CANCELACIONES = 3            # HG-03
SAL_CONTACTO = "sentinel-demo"     # en producción: secreto de la institución para seudonimizar contactos
