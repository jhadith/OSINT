"""Generador de datos sintéticos con la misma forma que los CSV del reto y 4 ataques plantados.

Imita lo que se vio en octubre de 2026: IPs de origen casi únicas, 13 etiquetas de aplicación que no siempre
corresponden al puerto, cuentas con ~500 eventos al mes repartidos entre 9 acciones, IP del servidor en el sistema
médico y un reloj del firewall desfasado 12 h en el caso de la cuenta fantasma. Los nombres son inventados.

Uso suelto:  python -m tests.generador carpeta 5000000 5000000
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SERVIDOR = "10.10.100.30"
INICIO = pd.Timestamp("2026-10-01")
APPS = [("Acceso_Remoto_Telnet", 23), ("Base_Datos", 8471), ("Comando_Remoto", 8475),
        ("Comparticion_Archivos_SMBv1", 445), ("Inicio_Sesion", 8472), ("Mapeo_Servidores", 8473),
        ("Resolucion_Nombres_NetBIOS", 137), ("Servicio_Central", 8470), ("Sesion_Incompleta", 3389),
        ("Trafico_TCP_Desconocido", 8474), ("No_Aplica", 40612), ("Datos_Insuficientes", 2144)]
ACCIONES = ["ACCESO FALLIDO", "Inactivacion de usuarios", "Reactivacion de usuarios", "TRANFERENCIA INTERRUMPIDA",
            "DESCARGA EXITOSA", "USUARIOS - Activar usuario", "TRANFERENCIA EXITOSA",
            "USUARIOS - Actualizar nivel de Usuario", "INGRESO SIST_MED_IESS"]
NOMBRES = ["CARLOS", "LUCIA", "MATEO", "SOFIA", "DIEGO", "VALERIA", "ANDRES", "CAMILA", "JORGE", "PAULA", "RAUL",
           "ELENA", "TOMAS", "NORA", "BRUNO", "IRENE", "HUGO", "ALBA", "LEO", "MARA"]
APELLIDOS = ["MENA", "SALAZAR", "TORRES", "VEGA", "ROJAS", "CORDOVA", "PAZ", "LEON", "NAVAS", "ARIAS", "MOLINA",
             "PONCE", "VERA", "CAMPOS", "SUAREZ", "IBARRA", "LUNA", "OCHOA", "PADILLA", "QUIROGA"]

# atacantes: usuario del firewall, nombre en el sistema médico, IP, cuenta
ATACANTES = {
    "fuerza_bruta": ("carlos.mena", "MENA SALAZAR CARLOS ANDRES", "10.10.100.11", "GEN0000021"),
    "escaneo": ("lucia.torres", "TORRES VEGA LUCIA ELENA", "10.10.100.22", "RIMODX1"),
    "fuga": ("mateo.rojas", "ROJAS CORDOVA MATEO JOSE", "10.10.100.55", "GEN1111999"),
    "fantasma": ("sofia.navas", "NAVAS ARIAS SOFIA ISABEL", "10.10.100.44", "QWE1234567"),
}


def _ts(rng, n):
    return INICIO + pd.to_timedelta(rng.integers(0, 31 * 86400, n), unit="s")


def _ips(rng, n):
    a = rng.integers(0, 256, (n, 3))
    return pd.Series(["10.%d.%d.%d" % tuple(r) for r in a]) if n < 200_000 else \
        "10." + pd.Series(a[:, 0]).astype(str) + "." + pd.Series(a[:, 1]).astype(str) + "." + pd.Series(a[:, 2]).astype(str)


def usuarios_fw(n=900):
    rng = np.random.default_rng(1)
    base = {f"{NOMBRES[i % 20].lower()}.{APELLIDOS[(i // 20) % 20].lower()}"
            + ("" if i < 400 else "." + APELLIDOS[(i // 7) % 20].lower()) for i in range(n)}
    return sorted(base | {a[0] for a in ATACANTES.values()})


def firewall(n: int, semilla: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    usuarios = usuarios_fw()
    app = rng.integers(0, len(APPS), n)
    df = pd.DataFrame({
        "Fecha_Generacion": _ts(rng, n).strftime("%Y-%m-%d %H:%M:%S"),
        "IP_Origen": _ips(rng, n),
        "IP_Destino": np.where(rng.random(n) < 0.6, SERVIDOR, "10.20.0.%d" % 5),
        "Usuario_Origen": np.array(usuarios)[rng.integers(0, len(usuarios), n)],
        "Usuario_Destino": "sist_med",
        "Aplicacion": np.array([a for a, _ in APPS])[app],
        "Puerto_Destino": np.array([p for _, p in APPS])[app].astype(str),
        "Protocolo": "tcp",
        "Accion": np.where(rng.random(n) < 0.6, "permitido", "negado"),
    })
    # SSH legítimo y escaso
    k = max(5, n // 6000)
    ssh = df.sample(k, random_state=3).assign(Aplicacion="SSH", Puerto_Destino="22", Accion="permitido",
                                               IP_Destino=SERVIDOR)
    filas = [df, ssh]

    def bloque(usuario, ip, inicio, segundos, n, puertos, accion, app="Sesion_Incompleta", proto="tcp"):
        t = pd.Timestamp(inicio) + pd.to_timedelta(np.sort(rng.integers(0, segundos + 1, n)), unit="s")
        p = np.resize(np.array(puertos), n)
        return pd.DataFrame({"Fecha_Generacion": t.strftime("%Y-%m-%d %H:%M:%S"), "IP_Origen": ip,
                             "IP_Destino": SERVIDOR, "Usuario_Origen": usuario, "Usuario_Destino": "sist_med",
                             "Aplicacion": app, "Puerto_Destino": p.astype(str), "Protocolo": proto, "Accion": accion})
    u, _, ip, _ = ATACANTES["fuerza_bruta"]
    filas.append(bloque(u, ip, "2026-10-10 00:00:00", 300, 2000, [23], "negado"))
    u, _, ip, _ = ATACANTES["escaneo"]
    filas.append(bloque(u, ip, "2026-10-19 14:10:00", 58, 1000, [8471, 445, 137, 3389], "negado"))
    u, _, ip, _ = ATACANTES["fuga"]
    filas.append(bloque(u, ip, "2026-10-07 13:00:00", 1, 30, [22], "permitido", app="No_Aplica", proto="SSH"))
    u, _, ip, _ = ATACANTES["fantasma"]
    filas.append(bloque(u, ip, "2026-10-24 22:40:00", 0, 1, [22], "permitido", app="SSH"))  # reloj +12 h
    # dos eventos sueltos desde el segmento del servidor, sin ataque
    filas.append(bloque("diego.torres", "10.10.100.68", "2026-10-15 23:52:50", 0, 1, [23], "permitido"))
    return pd.concat(filas, ignore_index=True).sample(frac=1, random_state=11).reset_index(drop=True)


def sistema_medico(n: int, semilla: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    cuentas_n = max(50, n // 500)
    cuentas = np.array([f"SIM{i:07d}" for i in range(cuentas_n)])
    # cada cuenta usa un grupo fijo de 13 nombres
    pool = np.array([f"{APELLIDOS[i % 20]} {APELLIDOS[(i // 20) % 20]} {NOMBRES[(i // 400) % 20]} {NOMBRES[(i * 7) % 20]}"
                     for i in range(4000)])
    c = rng.integers(0, cuentas_n, n)
    nombre = pool[(c * 13 + rng.integers(0, 13, n)) % len(pool)]
    ts = _ts(rng, n)
    ip = np.where(rng.random(n) < 0.99, SERVIDOR, _ips(rng, n).to_numpy())
    ip[rng.random(n) < 0.001] = "10147243249"
    df = pd.DataFrame({"USUARIO_EJECUTA_EVENTO": cuentas[c], "NOMBRE_USUARIO_EJECUTA_EVENTO": nombre,
                       "FECHA_EJECUTA_EVENTO": ts.strftime("%Y%m%d"), "HORA_EJECUTA_EVENTO": ts.strftime("%H:%M:%S"),
                       "DESCRIPCION_ACCION": np.array(ACCIONES)[rng.integers(0, 9, n)], "IP_CONEXION": ip})

    def bloque(cuenta, nombre, inicio, segundos, n, acciones):
        t = pd.Timestamp(inicio) + pd.to_timedelta(np.sort(rng.integers(0, segundos + 1, n)), unit="s")
        nombres = nombre if isinstance(nombre, str) else np.array(nombre)
        return pd.DataFrame({"USUARIO_EJECUTA_EVENTO": cuenta, "NOMBRE_USUARIO_EJECUTA_EVENTO": nombres,
                             "FECHA_EJECUTA_EVENTO": t.strftime("%Y%m%d"), "HORA_EJECUTA_EVENTO": t.strftime("%H:%M:%S"),
                             "DESCRIPCION_ACCION": np.resize(np.array(acciones), n), "IP_CONEXION": SERVIDOR})
    filas = [df]
    _, nom, _, cta = ATACANTES["fuerza_bruta"]
    filas.append(bloque(cta, nom, "2026-10-10 00:00:00", 300, 2000, ["ACCESO FALLIDO"]))
    _, nom, _, cta = ATACANTES["escaneo"]
    filas.append(bloque(cta, nom, "2026-10-19 01:49:00", 67000, 1000, ["ACCESO FALLIDO"]))
    _, nom, _, cta = ATACANTES["fuga"]
    filas.append(bloque(cta, nom, "2026-10-07 13:00:00", 45, 3000,
                        ["TRANFERENCIA INTERRUMPIDA"] * 99 + ["TRANFERENCIA EXITOSA"]))
    _, nom, _, cta = ATACANTES["fantasma"]
    filas.append(bloque(cta, nom, "2026-10-24 10:40:00", 0, 1, ["INGRESO SIST_MED_IESS"]))
    filas.append(bloque(cta, nom, "2026-10-24 10:40:15", 0, 1, ["DESCARGA EXITOSA"]))
    # cuenta administrativa compartida por 300 personas
    filas.append(bloque("ADMX09002", list(pool[:300]) * 4, "2026-10-01 08:00:00", 30 * 86400, 1200,
                        ["USUARIOS - Activar usuario"]))
    return pd.concat(filas, ignore_index=True).sample(frac=1, random_state=12).reset_index(drop=True)


def generar(carpeta: Path, n_fw: int, n_med: int) -> tuple[Path, Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    fw, med = carpeta / "fw.csv", carpeta / "med.csv"
    firewall(n_fw).to_csv(fw, index=False)
    sistema_medico(n_med).to_csv(med, index=False, encoding="cp1252")   # el original viene en cp1252
    return fw, med


if __name__ == "__main__":
    generar(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
