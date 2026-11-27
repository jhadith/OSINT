#!/usr/bin/env python3
"""CLI del simulador de chatbot de citas (T21/T22, S8) — SIMULACIÓN, no IzyBot.

Uso:
    python scripts/simulador_chatbot.py --generar [--out RUTA]
        Escribe la muestra determinista de agendamiento con device_id por
        fingerprint (400 dispositivos legítimos + 3 tramitadores 60/40/25 en
        un mismo día). Por defecto en motor/datos_ejemplo/: nunca en datos/
        (CSVs del reto) ni sobre las muestras existentes.

    python scripts/simulador_chatbot.py --servir [--host H] [--puerto P]
        Sirve la página web/simulador/ con el backend POST /reservar conectado
        al verificador de sanciones (SQLite propio; bloqueado → HTTP 423).

La detección de tramitadores y la sanción progresiva viven en motor.sanciones
(umbral y bandas en config/sanciones.yaml).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]          # raíz del repositorio sentinel
sys.path.insert(0, str(RAIZ / "motor"))             # ejecutable sin instalar el paquete

from motor import config as motor_config  # noqa: E402
from motor.sanciones import Sancionador  # noqa: E402
from motor.simulador.backend import crear_simulador  # noqa: E402
from motor.simulador.generador import generar_muestra  # noqa: E402

DEFECTO_SALIDA = RAIZ / "motor" / "datos_ejemplo" / "chatbot_tramitadores_oct2026.csv"
DEFECTO_TELEMETRIA = motor_config.SALIDAS / "telemetria_chatbot.csv"
DEFECTO_SANCIONES = motor_config.SALIDAS / "sanciones.sqlite3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--generar", action="store_true",
                        help="genera la muestra CSV determinista y termina")
    parser.add_argument("--servir", action="store_true",
                        help="sirve el simulador en local y termina")
    parser.add_argument("--out", type=Path, default=DEFECTO_SALIDA,
                        help=f"salida de --generar (por defecto: {DEFECTO_SALIDA})")
    parser.add_argument("--host", default="127.0.0.1", help="host de --servir")
    parser.add_argument("--puerto", type=int, default=8300, help="puerto de --servir")
    parser.add_argument("--ruta-telemetria", type=Path, default=DEFECTO_TELEMETRIA,
                        help="CSV/JSONL de telemetría de --servir")
    parser.add_argument("--ruta-sanciones", type=Path, default=DEFECTO_SANCIONES,
                        help="SQLite de sanciones de --servir")
    args = parser.parse_args(argv)

    if args.generar:
        total = generar_muestra(args.out)
        print(f"{total} filas -> {args.out} (seed=42)")
        return 0

    if args.servir:
        import uvicorn

        sancionador = Sancionador(args.ruta_sanciones)
        app = crear_simulador(args.ruta_telemetria,
                              verificador_bloqueo=sancionador.verificador)
        print(f"SIMULACIÓN en http://{args.host}:{args.puerto}/simulador/ "
              f"(telemetría: {args.ruta_telemetria}; sanciones: {args.ruta_sanciones})")
        uvicorn.run(app, host=args.host, port=args.puerto, log_level="info")
        return 0

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
