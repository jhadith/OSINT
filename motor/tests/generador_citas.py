"""Dataset sintético complementario del chatbot de citas (informe, apartado 14.2 y 14.6).

No contiene datos clínicos ni contactos en claro: pacientes y contactos van como referencias seudónimas. Las redes
usan rangos reservados para documentación (RFC 5737, 6598, 2544) y las huellas JA4 son inventadas con formato válido.

Escenarios (columna `escenario`, que el detector NO usa; sirve solo para evaluar):
  normal                    afiliados que reservan para sí y su familia
  cuidador_autorizado       cuidador registrado que agenda para varios familiares
  operador_autorizado       operador de ventanilla que agenda rápido para muchos pacientes, con autorización
  red_compartida            varias personas desde la misma IP fija (un cibercafé)
  cancelacion_justificada   personas que cancelan y vuelven a reservar su propia cita
  tramitador_bot            programa en nube y VPN que reserva al abrir la agenda
  tramitador_oficina        persona con navegador real, mismo contacto, reasigna citas canceladas
  tramitador_movil          celular que cambia de IP en cada sesión
  tramitador_whatsapp       canal sin datos técnicos: mismo contacto y reasignaciones

Uso:  python -m tests.generador_citas salida.csv
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pandas as pd

from motor.agendamiento import referencia_contacto

INICIO = pd.Timestamp("2026-10-01")
ESPECIALIDADES = ["Medicina general", "Pediatría", "Ginecología", "Odontología", "Cardiología", "Traumatología"]
JA4_NAV = ["t13d1516h2_8daaf6152771_02713d6af862", "t13d1517h2_8daaf6152771_b0da82dd1658",
           "t13d1715h2_5b57614c22b0_3d5424432f57"]
JA4_SCRIPT = "t13d091000_f91f431d341e_7cf09e3ae3cd"
MODELOS = [f"Modelo-A{n}" for n in range(100, 140)] + [f"Modelo-R{n}" for n in range(8, 14)]
UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


def _ua(m):
    return UA_PC if m == "PC" else f"Mozilla/5.0 (Linux; Android 14; {m}) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36"


class _G:
    def __init__(self, semilla):
        self.r = random.Random(semilla)
        self.filas, self.ns, self.nc, self.ne = [], 0, 0, 0

    def paciente(self, n):
        return f"PX-{n:07d}"

    def sesion(self, t, escenario, canal="web", ip="", ja4="", ua="", contacto="", rol="", autorizacion="",
               pacientes=(), resp=(2500, 15000), reasignar=None, cancelar_propia=False):
        self.ns += 1
        s = f"S{self.ns:07d}"
        r = self.r

        def ev(accion, pac="", cita="", ms=""):
            self.ne += 1
            self.filas.append({"evento_id": f"E{self.ne:08d}", "cita_id": cita, "fecha_hora": t.strftime("%Y-%m-%d %H:%M:%S"),
                               "accion": accion, "canal": canal, "sesion": s, "paciente_ref": pac,
                               "contacto_ref": referencia_contacto(contacto) if contacto else "",
                               "rol_declarado": rol, "autorizacion_ref": autorizacion,
                               "ip": ip if canal == "web" else "", "ja4": ja4 if canal == "web" else "",
                               "user_agent": ua if canal == "web" else "",
                               "respuesta_ms": "" if canal == "call_center" else str(ms),
                               "especialidad": r.choice(ESPECIALIDADES), "unidad": f"Unidad {r.randint(1, 12)}",
                               "escenario": escenario})
        ev("inicio")
        for p in pacientes:
            ms = r.randint(*resp)
            t += pd.Timedelta(milliseconds=ms)
            ev("consulta_disponibilidad", p, ms=ms)
            ms = r.randint(*resp)
            t += pd.Timedelta(milliseconds=ms)
            self.nc += 1
            cita = f"CI-{self.nc:08d}"
            ev("reserva", p, cita, ms)
            if reasignar:
                t += pd.Timedelta(seconds=r.randint(30, 240))
                ev("cancelacion", p, cita)
                t += pd.Timedelta(seconds=r.randint(2, 25))
                ev("reserva", reasignar(), cita, r.randint(*resp))
            elif cancelar_propia:
                t += pd.Timedelta(hours=r.randint(1, 30))
                ev("cancelacion", p, cita)
                t += pd.Timedelta(minutes=r.randint(1, 120))
                self.nc += 1
                ev("reserva", p, f"CI-{self.nc:08d}", r.randint(*resp))
        return t


def generar(ruta: Path, afiliados: int = 3000, semilla: int = 11) -> Path:
    g = _G(semilla)
    r = g.r
    npac = iter(range(1, 10_000_000))

    def t_dia(d, hora=None):
        h = hora if hora is not None else (7 if r.random() < 0.08 else r.randint(7, 20))
        return INICIO + pd.Timedelta(days=d, hours=h, minutes=r.randint(0, 59), seconds=r.randint(0, 59))

    for a in range(afiliados):
        familia = [g.paciente(next(npac)) for _ in range(r.choice([1, 1, 1, 2, 3]))]
        movil = r.random() < 0.6
        modelo = r.choice(MODELOS) if movil or r.random() < 0.3 else "PC"
        canal = r.choices(["web", "whatsapp", "call_center"], [0.65, 0.25, 0.10])[0]
        contacto = f"SIM-AF-{a:05d}"
        justificada = r.random() < 0.03
        for _ in range(r.choice([1, 1, 2, 3])):
            ip = f"{r.choice(['100.64', '100.65'] if movil else ['198.18', '198.19'])}.{r.randint(0, 255)}.{r.randint(1, 254)}"
            ja4 = JA4_NAV[2] if modelo == "PC" else JA4_NAV[MODELOS.index(modelo) % 2]
            g.sesion(t_dia(r.randint(0, 29)), "cancelacion_justificada" if justificada else "normal", canal, ip, ja4,
                     _ua(modelo), contacto, pacientes=r.sample(familia, k=r.randint(1, len(familia))),
                     cancelar_propia=justificada)
    # cuidadores autorizados: agendan para 8 a 14 familiares en el mes
    for k in range(5):
        pacientes = [g.paciente(next(npac)) for _ in range(r.randint(8, 14))]
        for p in pacientes:
            g.sesion(t_dia(r.randint(0, 29)), "cuidador_autorizado", "web", f"198.18.40.{10 + k}", JA4_NAV[2], UA_PC,
                     f"SIM-CUIDADOR-{k}", "cuidador", f"AUT-C{k:03d}", [p], (2000, 9000))
    # operadores de ventanilla autorizados: muchos pacientes, rápidos (capacitados)
    for k in range(3):
        for d in range(0, 30):
            for _ in range(r.randint(2, 4)):
                g.sesion(t_dia(d, r.randint(8, 16)), "operador_autorizado", "web", f"192.0.2.{20 + k}", JA4_NAV[2],
                         UA_PC, f"SIM-VENTANILLA-{k}", "operador_autorizado", f"AUT-O{k:03d}",
                         [g.paciente(next(npac))], (700, 1400))
    # red compartida (cibercafé): personas distintas desde la misma IP fija en la misma hora
    for d in range(0, 30, 3):
        t = t_dia(d, 10)
        for j in range(r.randint(3, 5)):
            g.sesion(t + pd.Timedelta(minutes=8 * j), "red_compartida", "web", "198.19.77.7", JA4_NAV[2], UA_PC,
                     f"SIM-CAFE-{d}-{j}", pacientes=[g.paciente(next(npac))])

    pac_vendidos = lambda: g.paciente(next(npac))  # noqa: E731
    # tramitador_bot: script desde nube y VPN, al abrir la agenda, muy rápido
    for d in range(0, 28):
        for _ in range(3):
            red = r.choice(["203.0.113", "198.51.100"])
            g.sesion(INICIO + pd.Timedelta(days=d, hours=7, seconds=r.randint(0, 50)), "tramitador_bot", "web",
                     f"{red}.{r.randint(1, 254)}", JA4_SCRIPT, _ua("Modelo-A125"), "", pacientes=[pac_vendidos()],
                     resp=(150, 600))
    # tramitador_oficina: navegador real, IP fija nueva cada día, mismo contacto, reasignaciones
    ip_dia = {}
    for k in range(45):
        d = r.randint(0, 29)
        ip_dia.setdefault(d, f"198.18.{r.randint(0, 255)}.{r.randint(1, 254)}")
        g.sesion(t_dia(d, r.randint(8, 18)), "tramitador_oficina", "web", ip_dia[d], JA4_NAV[2], UA_PC,
                 "SIM-TRAMITE-01", pacientes=[pac_vendidos()], resp=(2000, 6000),
                 reasignar=pac_vendidos if k % 4 == 0 else None)
    # tramitador_movil: celular real que cambia de IP en cada sesión, sesiones seguidas al abrir la agenda
    for d in (2, 9, 16, 23):
        t = INICIO + pd.Timedelta(days=d, hours=7, minutes=1)
        for _ in range(8):
            t = g.sesion(t, "tramitador_movil", "web", f"100.64.{r.randint(0, 255)}.{r.randint(1, 254)}", JA4_NAV[1],
                         _ua("Modelo-R13-X"), "", pacientes=[pac_vendidos()], resp=(1800, 3500)) \
                + pd.Timedelta(seconds=r.randint(40, 120))
    # tramitador_whatsapp: sin datos técnicos; mismo contacto, muchos pacientes y reasignaciones
    for k in range(30):
        g.sesion(t_dia(r.randint(0, 29), r.randint(8, 19)), "tramitador_whatsapp", "whatsapp",
                 contacto="SIM-TRAMITE-02", pacientes=[pac_vendidos()], resp=(2500, 7000),
                 reasignar=pac_vendidos if k % 3 == 0 else None)
    df = pd.DataFrame(g.filas).sort_values("fecha_hora", kind="stable")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
    return ruta


if __name__ == "__main__":
    generar(Path(sys.argv[1] if len(sys.argv) > 1 else "agendamiento_sintetico.csv"))
