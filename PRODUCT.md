# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite + TypeScript (confirmed by the user). Frontend only for now: the Python backend (analysis scripts) will be connected later through an HTTP API, so every screen reads from a service layer that today returns mock data.

## Users

- **Analistas del SOC del IESS** (primary): review prioritized alerts, investigate with evidence from both datasets, and confirm or discard each case.
- **Jefe de seguridad de la información**: sees critical threats and decides which risks to treat first.
- **Personal de TI y ciberseguridad**: applies IoCs (STIX 2.1, MISP) and Sigma rules.
- **Personal de salud** (médicos, enfermería, admisión): verifies suspicious links and images before opening them.
- First real audience: the jury of Hackatón Código Confianza IESS 2026 (Reto 3, Inteligencia de amenazas), on a laptop/projector. Demo priority, but it must read as a credible daily SOC tool.

## Product Purpose

Sentinel Salud (team ESPEThreat, Universidad ESPE) tells the IESS who is attacking its health information system, what trace they left in the firewall and medical-system logs, and what to do first. Success: a traceable flow from evidence to recommendation for each detected case, decided by a human analyst.

## Positioning

Hybrid threat intelligence run locally: rules + Isolation Forest + cross-correlation of the firewall dataset with the medical-system dataset. Case 4 (cuenta fantasma) only appears when the two sources are crossed; that cross is the product's proof.

## Operating Context

- 10.023.532 synthetic records of October 2026 processed locally in 2,8 min.
- Four attacks: posible fuga de datos (7 oct, crítica), fuerza bruta (10 oct, alta), escaneo de servicios (19 oct, alta), cuenta fantasma (24 oct, crítica).
- Event flow: Ingesta → Privacidad → Detección → Priorización y alerta → Decisión y respuesta → Difusión.
- Power BI holds the reporting dashboards; this console is the local investigation and decision surface.
- Critical alerts also go to the security chief via Telegram, with no personal data.

## Capabilities and Constraints

- Everything runs locally; no cloud, no external CDNs at runtime.
- Reports show pseudonyms; only an authorized analyst can re-identify, and that action is logged.
- The platform never blocks anything by itself; the analyst decides.
- ThreatPulse is in design: its trends are hypotheses, labelled as such.
- Data are synthetic. No IESS branding in simulations.
- Open: the backend API contract (endpoints are proposed by the frontend in `src/api`).

## Brand Commitments

Name "Sentinel Salud", team "ESPEThreat". No IESS logos or marks.
The console uses the ESPE (Universidad de las Fuerzas Armadas) institutional colors, confirmed by the user on 2026-11-26: ESPE green #00713D (sampled from the official logo at espe.edu.ec) as the brand color for shell, selection and data series; shield yellow #E4D522 as a thin accent under the header. The red of the shield is not used as brand color because red means "out of range / critical" in the console.

## Evidence on Hand

`Informe_Propuesta_Sentinel_Salud_ESPE.docx`: the four cases, account and IP identifiers, risk matrix R1–R8, ISO/IEC 27002 controls, STRIDE, tests. Model output CSVs and STIX/MISP/Sigma files exist in the team's backend but are not in this folder; the frontend uses mocks derived from the report.

## Product Principles

1. Evidence before verdict: every alert shows the trace that justifies it.
2. Two sources, one picture: firewall and medical-system evidence sit side by side.
3. The human decides: confirm/discard is explicit, reasoned and logged.
4. Privacy by default: pseudonyms everywhere, re-identification is exceptional.

## Accessibility & Inclusion

Readable on a projector; severity never conveyed by color alone. Spanish UI.
