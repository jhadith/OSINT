"""Parámetros del motor.

Los umbrales de detección NO viven aquí: están en `rules/*.yml` (S3/S12) para que el SOC los
calibre sin tocar código. Este módulo solo los carga y los expone con los mismos nombres de
siempre, más las rutas y constantes operativas que sí son parte del motor.

Calibración original (octubre de 2026): el tráfico normal del firewall llega desde IPs casi
únicas (máximo 7 eventos por IP en el mes) y cada cuenta del sistema médico tiene ~500 eventos
al mes repartidos al azar entre 9 acciones (máximo 83 accesos fallidos en el mes).
"""
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
SALIDAS = RAIZ / "salidas"
RESTRINGIDO = RAIZ / "restringido"
ARCHIVO_FW = DATOS / "Registros_conexiones_FW_10_2026.csv"
ARCHIVO_MED = DATOS / "Registros_conexiones_sist_med_iess.csv"
REDES = Path(__file__).resolve().parent / "datos_fijos" / "redes_ejemplo.csv"
TAM_PARTE = 500_000
ESTRICTO = False                   # True en las pruebas: un error en la salida de la consola detiene el motor
EPOCA = "2020-01-01"               # origen de los segundos internos (int32 alcanza hasta 2088)

# --- Carga de umbrales desde rules/*.yml (raíz del repositorio) ---
REGLAS_DIR = RAIZ.parent / "rules"

# Claves que YAML entrega como list y el motor necesita como tipos de Python
_A_CONJUNTO = {"PUERTOS_SSH", "CITAS_REDES_OCULTAS"}
_A_TUPLA = {"DESFASES_HORAS"}


def _cargar_umbrales() -> None:
    if not REGLAS_DIR.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de umbrales: {REGLAS_DIR}")
    for ruta in sorted(REGLAS_DIR.glob("*.yml")):
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        if not isinstance(datos, dict):
            raise ValueError(f"{ruta.name}: se esperaba un mapeo nombre → valor")
        for nombre, valor in datos.items():
            if nombre in _A_CONJUNTO:
                valor = set(valor)
            elif nombre in _A_TUPLA:
                valor = tuple(valor)
            globals()[nombre] = valor


_cargar_umbrales()

SAL_CONTACTO = "sentinel-demo"     # en producción: secreto de la institución para seudonimizar contactos
