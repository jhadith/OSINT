"""Pruebas del adaptador de los CSVs REALES del reto (T5, S6a — contrato v2).

Los dos logs reales del IESS (``Registros_conexiones_FW_10_2026.csv`` y
``Registros_conexiones_sist_med_iess.csv``, ~5M de filas cada uno) son el
contrato primario (Hackaton ``docs/data-contracts.md``, sección "Contrato
real (v2)"). ``leer_fw_real``/``leer_med_real`` los leen como camino paralelo
de ``leer_fw``/``leer_med``, sin cambiar el comportamiento de los CSVs de
ejemplo que ya funcionan.

Ningún test abre los CSV reales: los fixtures reproducen los encabezados
reales (con el BOM UTF-8) con unas pocas filas, como el test homólogo de
Hackaton (``tests/test_ingesta_reales.py``).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from motor import ingesta
from motor.ingesta import leer_fw, leer_fw_real, leer_med_real

CABECERA_FW = ("Fecha_Generacion,IP_Origen,IP_Destino,Usuario_Origen,Usuario_Destino,"
               "Aplicacion,Puerto_Destino,Protocolo,Accion")

FILAS_FW = [
    # caso base: tcp/8470 no es SSH
    "2026-10-13 05:27:48,10.42.88.20,10.10.100.30,ivan.prieto,sist_med_iess,"
    "Servicio_Central,8470,tcp,permitido",
    # fecha inválida -> descartada y contada, sin detener la lectura
    "2026-99-99 99:99:99,10.10.100.61,10.10.100.30,gala.mala,sist_med_iess,"
    "No_Aplica,8470,tcp,permitido",
    # Aplicacion contiene "SSH" -> gana sobre el puerto 8470 (contrato v2)
    "2026-10-07 13:00:00,10.10.100.50,10.10.100.30,ana.ssh,sist_med_iess,"
    "Tunneling_SSH,8470,tcp,permitido",
    # Protocolo = SSH (segunda prioridad de la deriva)
    "2026-10-07 13:00:01,10.10.100.51,10.10.100.30,bruno.ssh,sist_med_iess,"
    "No_Aplica,8470,SSH,permitido",
    # puerto 22 -> SSH
    "2026-10-07 13:00:02,10.10.100.52,10.10.100.30,diego.key,sist_med_iess,"
    "No_Aplica,22,tcp,permitido",
    # negado
    "2026-10-02 19:17:19,10.85.14.95,10.10.100.30,andrea.reyes,sist_med_iess,"
    "Servicio_Central,8470,tcp,negado",
    # IP con formato raro (sin puntos, como en los logs reales) -> ip_invalida
    "2026-10-12 10:00:00,10147243249,10.10.100.30,hugo.rara,sist_med_iess,"
    "No_Aplica,8470,tcp,permitido",
    # caso base 2
    "2026-10-11 09:15:00,10.10.100.62,10.10.100.30,elena.base,sist_med_iess,"
    "No_Aplica,8471,tcp,permitido",
]

CABECERA_SM = ("USUARIO_EJECUTA_EVENTO,NOMBRE_USUARIO_EJECUTA_EVENTO,FECHA_EJECUTA_EVENTO,"
               "HORA_EJECUTA_EVENTO,DESCRIPCION_ACCION,IP_CONEXION")

ACCIONES_SM = [
    "ACCESO FALLIDO",
    "INGRESO SIST_MED_IESS",
    "TRANFERENCIA EXITOSA",          # la errata del log real se conserva tal cual
    "TRANFERENCIA INTERRUMPIDA",
    "DESCARGA EXITOSA",
    "USUARIOS - Actualizar nivel de Usuario",
    "USUARIOS - Activar usuario",
    "Inactivacion de usuarios",
    "Reactivacion de usuarios",
]

FILAS_SM = [
    "MINAD,CRUZ ORTEGA BEATRIZ MELISSA,20261006,20:38:05,"
    "USUARIOS - Actualizar nivel de Usuario,10.10.100.30",
    "CMAP09002,REYES MEDINA VANESSA CARMEN,20261001,11:04:16,"
    "USUARIOS - Activar usuario,10.10.100.30",
    "RIMODE1,GARCIA LUIS MIGUEL,20261010,00:00:05,ACCESO FALLIDO,10.10.100.30",
    "XYZ1111331,PEREZ ANA MARIA,20261007,13:00:10,"
    "TRANFERENCIA EXITOSA,10.10.100.30",
    "XYZ1111331,PEREZ ANA MARIA,20261007,13:00:40,"
    "TRANFERENCIA INTERRUMPIDA,10.10.100.30",
    "WXY1210010,LOPEZ MARIA DEL CARMEN,20261024,10:40:15,"
    "DESCARGA EXITOSA,10.10.100.30",
    "ADMIN01,SISTEMAS ADMINISTRADOR,20261005,08:00:00,"
    "Inactivacion de usuarios,10.10.100.30",
    "ADMIN01,SISTEMAS ADMINISTRADOR,20261005,08:05:00,"
    "Reactivacion de usuarios,10.10.100.30",
    "XYZ9999002,VILLAVICENCIO AVILA XIMENA MARTHA,20261012,15:23:25,"
    "INGRESO SIST_MED_IESS,10.10.100.30",
    # IP con formato raro (como en el log real): se conserva marcada en ipmal
    "USRARA,NOMBRE RARO,20261013,09:00:00,ACCESO FALLIDO,10147243249",
    # fecha inválida -> descartada y contada
    "USRFECHA,NOMBRE FECHA,20269999,12:00:00,ACCESO FALLIDO,10.10.100.30",
]


def _escribir_real(path: Path, cabecera: str, filas: list[str]) -> Path:
    """Fixture con el BOM UTF-8 real de los CSV del IESS (utf-8-sig)."""
    contenido = cabecera + "\n" + "\n".join(filas) + "\n"
    path.write_bytes(contenido.encode("utf-8-sig"))
    return path


def _fw_real(tmp_path: Path) -> Path:
    return _escribir_real(tmp_path / "fw_real.csv", CABECERA_FW, FILAS_FW)


def _sm_real(tmp_path: Path) -> Path:
    return _escribir_real(tmp_path / "sm_real.csv", CABECERA_SM, FILAS_SM)


# ---------------------------------------------------------------- firewall


def test_fw_real_lee_con_bom_y_mapea(tmp_path):
    lectura = leer_fw_real(_fw_real(tmp_path))
    df = lectura.datos

    # el BOM no contamina la primera columna: ninguna falta
    assert lectura.faltantes == []
    # 8 filas fixture - 2 inválidas = 6 válidas
    assert lectura.filas == 8 and lectura.invalidas == 2
    assert len(df) == 6
    assert {"s", "iph", "u", "p", "neg", "srv", "seg", "ssh", "fila"} <= set(df.columns)
    por_usuario = df.set_index("u")
    assert ingesta.fecha(por_usuario.loc["ivan.prieto", "s"]) == pd.Timestamp("2026-10-13 05:27:48")
    assert int(por_usuario.loc["ivan.prieto", "p"]) == 8470
    assert not bool(por_usuario.loc["ivan.prieto", "neg"])
    assert bool(por_usuario.loc["andrea.reyes", "neg"])
    assert df["srv"].all()


def test_fw_real_deriva_el_protocolo_ssh(tmp_path):
    df = leer_fw_real(_fw_real(tmp_path)).datos
    ssh = df.set_index("u")["ssh"].to_dict()

    assert ssh["ana.ssh"]        # Aplicacion contiene SSH y gana sobre el puerto 8470
    assert ssh["bruno.ssh"]      # Protocolo == SSH
    assert ssh["diego.key"]      # puerto 22
    assert not ssh["ivan.prieto"]   # tcp/8470 sin SSH en ninguna prioridad
    assert not ssh["elena.base"]
    assert not ssh["andrea.reyes"]


def test_fw_real_descarta_fecha_e_ip_invalidas(tmp_path):
    lectura = leer_fw_real(_fw_real(tmp_path))
    df = lectura.datos

    assert lectura.invalidas == 2
    assert "gala.mala" not in set(df["u"])
    assert "hugo.rara" not in set(df["u"])
    # la posición en el archivo se conserva para la segunda pasada de evidencia
    assert sorted(df["fila"]) == [0, 2, 3, 4, 5, 7]


def test_fw_real_por_chunks_produce_lo_mismo(tmp_path):
    path = _fw_real(tmp_path)
    completo = leer_fw_real(path)
    por_chunks = leer_fw_real(path, tam=3)

    assert len(por_chunks.datos) == len(completo.datos)
    assert por_chunks.filas == completo.filas
    assert por_chunks.invalidas == completo.invalidas
    assert sorted(por_chunks.datos["fila"]) == sorted(completo.datos["fila"])


# ------------------------------------------------------------ sistema medico


def test_med_real_mapea_las_nueve_acciones_con_la_errata(tmp_path):
    lectura = leer_med_real(_sm_real(tmp_path))
    df = lectura.datos

    assert lectura.faltantes == []            # el BOM no contamina la primera columna
    # 11 filas fixture - 1 fecha inválida = 10 válidas (la IP rara se conserva)
    assert lectura.filas == 11 and lectura.invalidas == 1
    assert len(df) == 10
    assert set(df["accion"].cat.categories) == set(ACCIONES_SM)
    # la errata del log real se conserva: las reglas emparejan "TRANFER" por texto
    assert "TRANFERENCIA EXITOSA" in df["accion"].cat.categories
    assert not any(str(a).startswith("TRANSFERENCIA") for a in df["accion"].cat.categories)
    for accion in ACCIONES_SM:
        assert (df["accion"] == accion).sum() >= 1, accion
    por_cuenta = df.set_index("cuenta")
    assert ingesta.fecha(por_cuenta.loc["MINAD", "s"]) == pd.Timestamp("2026-10-06 20:38:05")
    assert por_cuenta.loc["MINAD", "persona"] == "CRUZ ORTEGA BEATRIZ MELISSA"
    assert por_cuenta.loc["MINAD", "ip"] == "10.10.100.30"


def test_med_real_conserva_la_ip_rara_y_descarta_la_fecha_mala(tmp_path):
    lectura = leer_med_real(_sm_real(tmp_path))
    df = lectura.datos

    rara = df[df["cuenta"] == "USRARA"]
    assert len(rara) == 1 and bool(rara["ipmal"].iloc[0])
    assert int(df["ipmal"].sum()) == 1
    assert "USRFECHA" not in set(df["cuenta"])
    assert lectura.invalidas == 1


def test_med_real_por_chunks_produce_lo_mismo(tmp_path):
    path = _sm_real(tmp_path)
    completo = leer_med_real(path)
    por_chunks = leer_med_real(path, tam=4)

    assert len(por_chunks.datos) == len(completo.datos)
    assert por_chunks.filas == completo.filas
    assert por_chunks.invalidas == completo.invalidas
    assert int(por_chunks.datos["ipmal"].sum()) == int(completo.datos["ipmal"].sum())
    assert set(por_chunks.datos["accion"].cat.categories) == set(completo.datos["accion"].cat.categories)


# ------------------------------------------------- preservación del camino viejo


def test_el_camino_de_ejemplo_sigue_detectando_la_codificacion(tmp_path):
    """PRESERVE: leer_fw sigue con auto-detección (utf-8/cp1252), sin forzar utf-8-sig."""
    fila = ("2026-10-13 05:27:48,10.42.88.20,10.10.100.30,josé.maña,sist_med_iess,"
            "Servicio_Central,8470,tcp,permitido")
    ruta = tmp_path / "fw_cp1252.csv"
    ruta.write_bytes((CABECERA_FW + "\n" + fila + "\n").encode("cp1252"))

    lectura = leer_fw(ruta)
    assert lectura.faltantes == [] and lectura.invalidas == 0
    assert set(lectura.datos["u"]) == {"josé.maña"}
