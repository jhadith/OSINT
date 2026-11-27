"""Motor de mitigaciones no excluyentes de HBVF (informe 14.4, etapa 6, y 14.5).

Traduce las mitigaciones declaradas en el catálogo a texto consultivo para revisión
humana. REGLA DUURA (S10): este módulo solo produce recomendaciones de texto; no expone
ninguna función que cancele, bloquee, rechace o suspenda, no recibe identificadores de
citas o eventos, y los textos son admonitorios, no órdenes ejecutables. Las medidas son
no excluyentes: un caso puede acumular varias.
"""
from __future__ import annotations

MITIGACIONES: dict[str, str] = {
    "confirmacion": "Confirmar la reserva con el afiliado por su contacto ya verificado (no el que se dejó en el chat). "
                    "Puede confirmar, desconocer o pedir ayuda; no responder no le quita la cita.",
    "representacion": "Verificar si existe una representación autorizada (cuidador u operador) antes de actuar.",
    "educacion": "Informar a los pacientes de este punto sobre los canales oficiales y que las citas son gratuitas, "
                 "sin acusar a nadie.",
    "revision": "Revisión conjunta del SOC y el área de agendamiento; las reservas se preservan mientras se investiga.",
    "desafio": "Pedir una verificación adicional (por ejemplo, un CAPTCHA accesible) a las sesiones de este origen.",
    "lista_espera": "Si un paciente desconoce su cita, ofrecerla por la lista de espera según el procedimiento.",
    "seguimiento": "Medir reincidencia corroborada y posibles perjuicios a pacientes legítimos.",
}


def recomendaciones(estado: str, patrones: dict[str, str]) -> list[str]:
    """Claves de mitigación no excluyentes para el estado validado (solo texto consultivo).

    Selección derivada del estado HBVF: la revisión prioritaria acumula más medidas,
    la observación/indeterminación solo las de contexto, y sin hallazgo no hay nada.
    """
    presentes = [k for k, v in patrones.items() if v == "presente"]
    if estado in ("Revisión prioritaria", "Requiere revisión"):
        claves = ["confirmacion", "representacion", "revision", "educacion"]
        if patrones["HG-06"] == "presente" or patrones["HG-02"] == "presente":
            claves.append("desafio")
        if "HG-05" in presentes:
            claves.append("lista_espera")
        claves.append("seguimiento")
        return claves
    if estado.startswith("Indeterminado") or estado == "Observación":
        return ["representacion", "seguimiento"]
    return []


def textos_consultivos(claves: list[str]) -> list[dict[str, str]]:
    """Texto consultivo por clave: solo ``{id, texto}``; nunca una acción ejecutable."""
    return [{"id": k, "texto": MITIGACIONES[k]} for k in claves]
