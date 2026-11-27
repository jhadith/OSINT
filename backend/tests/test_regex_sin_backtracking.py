"""Las expresiones que limpian texto de denuncias y avisos no se cuelgan con entradas largas (ReDoS)."""
import time

from app import avisos, denuncias

LARGO = 50_000


def _rapido(funcion, texto):
    inicio = time.perf_counter()
    resultado = funcion(texto)
    assert time.perf_counter() - inicio < 2, "la expresión tarda demasiado: posible backtracking"
    return resultado


def test_fecha_de_nacimiento_con_muchos_espacios_no_se_cuelga():
    _rapido(denuncias.proteger, "fecha de nacimiento" + " " * LARGO + "x")


def test_fecha_de_nacimiento_sigue_protegida():
    texto = _rapido(denuncias.proteger, "FECHA DE NACIMIENTO\n12 ENE 1985\nSexo M")
    assert "1985" not in texto and texto.startswith("FECHA DE NACIMIENTO\n")


def test_aviso_con_correo_gigante_no_se_cuelga():
    _rapido(avisos.limpiar, "a" * LARGO + "@" + "b" * LARGO)


def test_aviso_retira_correos_e_ip():
    texto = avisos.limpiar("Escriba a ana.perez@iess.gob.ec desde 10.10.1.5")
    assert "ana.perez" not in texto and "10.10.1.5" not in texto
