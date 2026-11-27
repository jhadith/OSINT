"""S10/T4: el motor de mitigaciones es no excluyente y solo consultivo — cero acciones automáticas."""
import inspect

from motor.hbvf import mitigation_engine as me

PROHIBIDOS = ("cancel", "bloque", "rechaz", "deneg", "elimin", "borrar", "suspens", "vetar",
              "reject", "block", "deny", "delete")
PARAMETROS_ACCION = {"cita_id", "id_cita", "id_evento", "paciente_ref"}
CLAVES_ESPERADAS = {"confirmacion", "representacion", "educacion", "revision", "desafio",
                    "lista_espera", "seguimiento"}


def _funciones_propias():
    return {n: f for n, f in inspect.getmembers(me, inspect.isfunction) if f.__module__ == me.__name__}


def test_no_expone_funciones_que_cancelen_o_bloqueen():
    propias = _funciones_propias()
    assert propias, "el motor debe exponer su selección de recomendaciones"
    for nombre in propias:
        assert not any(p in nombre.lower() for p in PROHIBIDOS), f"función con acción automática: {nombre}"


def test_ninguna_funcion_actua_sobre_una_cita_o_evento():
    for nombre, fn in _funciones_propias().items():
        params = set(inspect.signature(fn).parameters)
        assert not params & PARAMETROS_ACCION, f"{nombre} opera sobre entidades del chatbot"


def test_solo_texto_consultivo_sin_campos_ejecutables():
    assert CLAVES_ESPERADAS <= set(me.MITIGACIONES)
    assert all(isinstance(t, str) and t for t in me.MITIGACIONES.values())
    patrones = {f"HG-0{i}": "ausente" for i in range(1, 8)}
    patrones["HG-01"] = patrones["HG-06"] = "presente"
    claves = me.recomendaciones("Revisión prioritaria", patrones)
    assert claves
    for item in me.textos_consultivos(claves):
        assert set(item) == {"id", "texto"}
        assert item["texto"] == me.MITIGACIONES[item["id"]]
