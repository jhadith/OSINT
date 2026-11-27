"""Aviso inmediato al jefe de seguridad por cada caso crítico de un análisis nuevo, y avisos al personal de salud.

Por defecto es una simulación (queda en la bitácora). Para enviar de verdad: SENTINEL_TELEGRAM=enviar,
TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en el entorno, nunca en el código. Los avisos para el personal de salud
van a otro chat: TELEGRAM_CHAT_SALUD. Ningún texto lleva datos personales ni datos técnicos.
Prueba de conexión:  python -m app.telegram
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from . import config, estado

API = "https://api.telegram.org/bot{token}/sendMessage"


def _enviar(texto: str, variable_chat: str = "TELEGRAM_CHAT_ID") -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get(variable_chat, "")
    if not (token and chat):
        raise RuntimeError(f"faltan TELEGRAM_BOT_TOKEN y {variable_chat}")
    datos = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode("utf-8")
    pedido = urllib.request.Request(API.format(token=token), data=datos, method="POST")
    # URL fija con https hacia la API oficial de Telegram
    with urllib.request.urlopen(pedido, timeout=15) as r:  # nosec B310
        if not json.loads(r.read().decode("utf-8")).get("ok"):
            raise RuntimeError("Telegram rechazó el mensaje")


def avisar_criticos(analisis_id: str, casos: list[dict]) -> None:
    hechos = estado.ultimo_por("telegram", "clave")
    for c in casos:
        clave = f"{analisis_id}:{c['id']}"
        if c.get("gravedad") != "critica" or not c.get("alerta"):
            continue
        previo = hechos.get(clave)
        if previo and (previo["enviada"] or not config.TELEGRAM_ENVIAR):
            continue
        enviada, detalle = False, "Simulación: el envío real se activa con SENTINEL_TELEGRAM=enviar"
        if config.TELEGRAM_ENVIAR:
            try:
                _enviar(c["alerta"]["texto"])
                enviada, detalle = True, "Mensaje enviado al jefe de seguridad, sin datos personales"
            except Exception as e:  # el error queda registrado y la consola sigue
                detalle = f"No se pudo enviar: {str(e)[:120]}"
        estado.agregar("telegram", {"clave": clave, "enviada": enviada, "fecha": estado.ahora(),
                                    "modo": "real" if config.TELEGRAM_ENVIAR else "simulación"})
        estado.bitacora("Sentinel Salud", "Alertas", "Alerta crítica enviada" if enviada else "Alerta crítica simulada",
                        c["id"], detalle)


def avisar_personal(texto: str) -> tuple[bool, str]:
    """Envía un aviso al chat del personal de salud. Devuelve (enviado, detalle para la bitácora)."""
    if not config.TELEGRAM_ENVIAR:
        return False, "Simulación: el envío real se activa con SENTINEL_TELEGRAM=enviar y TELEGRAM_CHAT_SALUD"
    try:
        _enviar(texto, "TELEGRAM_CHAT_SALUD")
        return True, "Aviso enviado al chat del personal de salud, sin datos personales"
    except Exception as e:  # el error queda registrado y la consola sigue
        return False, f"No se pudo enviar: {str(e)[:120]}"


if __name__ == "__main__":
    _enviar("Sentinel Salud: prueba de conexión del bot. Las alertas críticas llegarán a este chat.")
    print("Mensaje de prueba enviado.")
