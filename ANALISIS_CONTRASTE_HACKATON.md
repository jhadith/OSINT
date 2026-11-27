# Análisis total — Sentinel Salud: contraste informe F-11 vs. los dos repositorios

> Fuentes: `Hackaton/Sentinel_Salud_Informe_Ampliado_HBVF-FF.docx` (160 párrafos + 22 tablas),
> `Hackaton/odd/tasks/sentinel-salud-mvp.md` (specs S1–S15, tareas T1–T22, Log L1–L18),
> y el código real de ambos repositorios (exploración directa + suites ejecutadas).
> Estado verificado hoy: **Hackaton 117 tests GREEN / 14 rojas** (solo `test_simulador`),
> **sentinel 25 tests GREEN** (backend 10 + motor 15, 1 skip).

---

## 1. Resumen ejecutivo

Hay **dos implementaciones paralelas del mismo producto**, en repositorios distintos,
con arquitecturas divergentes y **complementarias**:

| | `Hackaton/` | `sentinel/` (este directorio) |
|---|---|---|
| Qué es | Núcleo de detección spec-fiel, con tracking ODD formal | Plataforma completa consola+API, demo lista |
| Estado | Pipeline completo y testeado; **sin consola ni API** | Consola + API + portal funcionando; **divergencias con la spec** |
| Tests | **117 GREEN** + 14 rojas (simulador incompleto) | **25 GREEN** (10 backend + 15 motor) |
| Git | ✅ repo, rama `feature/sentinel-salud-mvp`, 13 commits, CI | ❌ **no es repo git** (riesgo: cambios sin red de seguridad) |
| Datos reales | ✅ los dos CSV del reto en la raíz (5.008.538 + 5.013.714 filas) y smoke E2E hecho (17m27s) | ❌ solo `datos_ejemplo` (~280k filas); formato compatible, volumen no probado |
| Consola web | ❌ `web/` vacío, `api/` vacío (T9–T11 pendientes) | ✅ 15 pantallas, login, 5 roles, ~35 endpoints |
| Fortaleza | Cumple S12 (generalidad), S10 (HBVF con sus 4 componentes), reglas en YAML, SQLite | Cumple S3 (consola), S14 (denuncias), verificación de contenido, exportes CTI |

**Ninguno de los dos cumple el informe por sí solo.** El informe pide un sistema con
consola operativa *y* las tres capas de detección *y* HBVF *y* Proteger *y* exportes:
cada repo tiene la mitad que al otro le falta. El trabajo real es **reconciliarlos sin
romper lo que ya funciona en ninguno de los dos**.

---

## 2. Matriz de contraste por requerimiento

Leyenda: ✅ cumplido · ⚠️ parcial/divergente · ❌ falta

| # | Requerimiento (informe / spec) | Hackaton | sentinel | Brecha |
|---|---|:---:|:---:|---|
| 1 | Ingesta tolerante por partes, CSVs reales (T3, contrato v2) | ✅ | ⚠️ | sentinel: por partes sí, pero **sin probar con los 5M de filas reales** |
| 2 | Privacidad: seudónimos + vault restringido (S6, T4) | ✅ pepper `.env` | ✅ sal `restringido/sal.txt` | Mecanismos distintos; ambos evitan fugas (test de fugas en ambos) |
| 3 | **Reglas con umbrales en `rules/*.yml`** (S12) | ✅ 5 YAML | ❌ | sentinel tiene los umbrales **hardcodeados en `motor/config.py`** → incumple S12 |
| 4 | Isolation Forest M1–M3 explicado, semilla 42 (S5) | ✅ | ✅ | Equivalentes |
| 5 | Correlación caso 4 por ventana temporal (S5) | ✅ | ✅ | sentinel además **corrige desfase de reloj de 12h** (informe); Hackaton no lo menciona |
| 6 | Matriz P×I 1–25 y cortes de gravedad (informe §matriz) | ✅ estática | ✅ **dinámica R1–R11** (baja al descartar casos) | sentinel cumple mejor el informe (incluye R9–R11 del apartado 14) |
| 7 | Los 4 casos detectados con tests (S5) | ✅ | ✅ | Ambos |
| 8 | Ciclo de vida de alertas + bitácora (S7, T7) | ✅ **SQLite** con triggers | ⚠️ JSONL append-only | Divergencia de tecnología; la spec T7 pide SQLite |
| 9 | Pipeline CLI end-to-end (T8) | ❌ sin entry-point | ✅ `pipeline.py:228` | Hackaton no puede correr "de CSV a alerta" en un comando |
| 10 | Telegram crítico simulado, mínimo, sin datos (S8, T12) | ✅ | ✅ | Ambos |
| 11 | **Consola web con login y roles** (S3, T9–T11) | ❌ | ✅ 15 pantallas, 5 roles, PBKDF2, bloqueo 5 intentos | **La mayor brecha de Hackaton** |
| 12 | Tableros estratégico/táctico/operativo/táctico + IoC (T11) | ❌ | ✅ | Hackaton |
| 13 | **HBVF: los 4 componentes mínimos** `pattern_catalog.json`, `behavior_validation.py`, `mitigation_engine.py`, `model_evaluation.py` + **SQLite** (S10, informe 14.4) | ✅ los 4 archivos + SQLite | ⚠️ todo en `agendamiento.py`, **sin SQLite, sin catálogo JSON, sin métricas de modelo** | sentinel no cumple el contrato literal del informe 14.4 |
| 14 | Simulador de chatbot + fingerprint de dispositivo (S15, T21) | ⚠️ `fingerprint.py` + tests **ROJOS** (faltan `backend.py`, script CLI y muestra) | ⚠️ huella JA4+UA en `agendamiento.py:159`, sin simulador propio | Ambos incompletos |
| 15 | **Sanción progresiva de dispositivo 1h→4h→24h→72h** (S15, T22) | ❌ | ❌ | **Ninguno la tiene**; solo mitigaciones consultivas |
| 16 | ThreatPulse con scoring de tendencias (S11, T15) | ✅ scoring recencia×relevancia×exposición | ⚠️ `fijos/tendencias.json` **estático** | sentinel no "evalúa" tendencias, solo las muestra |
| 17 | **Proteger: portal de denuncias externo** con seguimiento (S14, T19) | ❌ | ✅ completo (público, rate-limit, código `DN-…`, bandeja SOC, cruce HG-07) | Hackaton |
| 18 | **Proteger: verificación de enlaces/imagen** para personal de salud (informe §valor) | ❌ | ✅ `verificar.py` + listas + reportar→denuncia | Hackaton |
| 19 | Exportes Sigma / STIX 2.1 / MISP (informe §valor, §viabilidad) | ❌ `stix2` instalado sin usar | ✅ `consola.py:302-378` + `/api/exportes` | Hackaton |
| 20 | Grafo de relaciones / Maltego (T20) | ❌ | ⚠️ pantalla Relaciones + endpoint grafo; export CE no verificado | Falta export a Maltego en ambos |
| 21 | **Realimentación: decisiones→umbrales, reentrenamiento, F1** (S13, T18) | ❌ | ❌ (solo la matriz de riesgo reacciona a decisiones) | **Ninguno**: no hay recalibración ni métricas F1 visibles |
| 22 | Generalidad: cero literales de datos, test con dataset variado (S12, T17) | ✅ 11 tests de genericidad | ⚠️ **sin test equivalente** | sentinel no prueba que otro CSV produzca los mismos hallazgos |
| 23 | CI: pytest + bandit + pip-audit + gitleaks (T13) | ✅ | ⚠️ `ci.yml` existe, contenido no auditado en detalle | Verificar paridad |
| 24 | Docs: contratos, runbook (T16) | ⚠️ `data-contracts.md` + README breve; falta runbook | ✅ COMO_CORRER + README + guion | Complementarios |
| 25 | E2E con volumen real 10M filas (informe §conclusiones) | ✅ smoke L18 verificado | ❌ | sentinel debe validar rendimiento antes de prometer |
| 26 | Tablas CSV/JSON para Power BI (T10, informe) | ❌ | ⚠️ exportes CTI sí, tablas de tablero no verificadas | Revisar en ambos |
| 27 | Gileaks/Bandit/pip-audit sin hallazgos (informe §pruebas) | ✅ (L10) | ⚠️ bandit/pip-audit en requirements, ejecución local pendiente de confirmar | — |

**Totales: Hackaton ✅12 / ⚠️6 / ❌9 · sentinel ✅13 / ⚠️10 / ❌4.**

---

## 3. Matices de separación (decisiones ya tomadas que respetar)

Estos son los puntos donde los dos repos *deben* divergir o donde ya se decidió algo
que cualquier cambio tiene que preservar:

1. **Proteger es externo al SOC** (S14/L15): el portal de denuncias alimenta al SOC por
   la ingesta, pero no es pantalla del SOC. *Ojo*: en sentinel la bandeja de denuncias
   **sí vive dentro de la consola** (`Denuncias.tsx`) — el portal público está separado,
   pero conviene dejar explícito qué es bandeja SOC (interno) y qué es portal (externo).
2. **El chatbot del IESS no se toca** (S15/L17): solo se *simula*; la sanción progresiva
   es **sobre el dispositivo emisor**, nunca sobre citas ya reservadas de terceros.
   Ninguno de los dos la implementó aún.
3. **Nada automático sobre personas o citas** (S7/S10): ambos repos lo cumplen hoy
   (tests dedicados en cada lado). Cualquier sanción de dispositivo debe mantener ese test.
4. **Roles**: informe (tabla 1) = analistas, jefe, TI, salud; spec T9 = analista/jefe/admin;
   sentinel implementa jefe/analista/ti/salud/auditor. **El informe manda**: sentinel ya se
   alinea; la spec T9 debería corregirse, no al revés.
5. **Persistencia**: informe 14.4 exige SQLite (al menos para HBVF); spec T7 pide SQLite
   para alertas/bitácora. sentinel usa JSONL. Decisión a tomar (ver §5).
6. **Huella de dispositivo**: informe 14.3 dice que JA4 es solo señal auxiliar (no
   identidad). Ambos lo respetan: sentinel usa JA4+UA combinados; Hackaton usa hash de
   señales canónicas. Unificar semántica al merge.

---

## 4. Brechas críticas (lo que el informe exige y falta en uno o ambos)

**A. Solo en Hackaton falta:**
- A1. Consola web con login, roles, alertas+evidencia, decisión, bitácora, tableros, IoC (T9–T11) — *el bloque de trabajo más grande*.
- A2. CLI pipeline (T8), runbook (T16), ThreatPulse dinámico ya hecho pero sin UI.
- A3. Puerto de: denuncias, verificación de contenido, exportes Sigma/STIX/MISP (ya existen en sentinel).
- A4. Suite `test_simulador` roja: faltan `src/sentinel/simulador/backend.py`, `scripts/simulador_chatbot.py` y la muestra `data/samples/chatbot_tramitadores_oct2026.csv` (9 failed + 5 errors, verificado por ejecución).
- A5. `sentinel.simulador.__init__` importa un módulo inexistente → el paquete ni siquiera importa limpio.

**B. Solo en sentinel falta:**
- B1. Umbrales en YAML (S12) — hoy en `motor/config.py`.
- B2. HBVF con sus 4 componentes nombrados + SQLite (informe 14.4).
- B3. Test de generalidad con dataset variado (T17).
- B4. Sanción progresiva de dispositivo (T22) — ambos.
- B5. Realimentación F1/recalibración (T18) — ambos.
- B6. **No es repo git** → cualquier cambio es irreversible. Inicializar antes de tocar nada.
- B7. Validación con los CSVs reales de 5M filas (rendimiento y compatibilidad de formato).

**C. En ambos falta:**
- C1. T21/T22 completos (simulador + sanción progresiva con bitácora y apelación).
- C2. T18 realimentación (decisiones + falsos positivos → umbrales + reentrenamiento + F1 visibles).
- C3. Export a Maltego CE (T20), tablas CSV para Power BI.
- C4. SonarCloud, OWASP ZAP, Gitleaks local (informe §pruebas; ZAP y SonarCloud "planificadas" según el propio informe — aceptable reportarlas como pendientes del entregable).

---

## 5. Propuesta de cambios sin dañar nada (para tu revisión)

### Fase 0 — Protección (obligatoria antes de cualquier edición)
1. `git init` + commit baseline en `sentinel/` (hoy no hay red de seguridad).
2. Registrar el baseline de tests: Hackaton 117G/14R (rojas conocidas, T21), sentinel 25G.
3. Nada de borrar ni reescribir: ambos repos son *aditivos* desde aquí.

### Fase 1 — Decisión de arquitectura (la única decisión humana real)

| Opción | Qué implica | Riesgo |
|---|---|---|
| **A. Hackaton como núcleo + portar la consola de sentinel** | Cumple specs/tests/datos reales; se adapta la API de sentinel al storage y rules de Hackaton | Reescribir ~35 endpoints contra SQLite/YAML; la UI no cambia casi |
| **B. sentinel como base + backportear las fortalezas de Hackaton** | La demo sigue funcionando desde el día 1; se migran reglas→YAML, estado→SQLite, se copian los 4 componentes HBVF y los tests de genericidad | Hay que rehacer el HBVF de sentinel con el contrato 14.4 y migrar datos de JSONL |
| **C. Mantener ambos con contrato compartido** (`docs/data-contracts.md` como frontera) | Cero riesgo inmediato | Doble mantenimiento; las brechas de cada lado siguen abiertas |

**Recomendación (evidencia): opción B**, porque:
- el bloque más caro (consola+API+RBAC+denuncias+verificación+exportes, 15 pantallas) ya está construido y testeado en sentinel;
- lo que hay que traer de Hackaton es *específico y acotado*: YAML de reglas, storage SQLite, los 4 archivos HBVF + tests, adaptador de CSVs reales + test de genericidad, CLI;
- lo contrario (A) significa reescribir toda la capa API contra un storage nuevo — más líneas cambiadas y más riesgo de romper lo que hoy funciona.
- Contra B: hay que hacer el smoke E2E con los 5M reales en sentinel antes de afirmar que cumple el informe (§4 B7).

### Fase 2 — Secuencia de cambios (por orden, cada uno con su test)

1. Git init + baseline (Fase 0).
2. **Migrar umbrales a `rules/*.yml`** en sentinel (lee YAML, elimina literales de `config.py`) — test: mismo resultado con YAML.
3. **Migrar estado a SQLite** en sentinel (alertas/ciclo de vida/bitácora, conservando el formato de bitácora append-only) — test: transiciones idénticas.
4. **HBVF contrato 14.4**: extraer de `agendamiento.py` los 4 archivos (`pattern_catalog.json`, `behavior_validation.py`, `mitigation_engine.py`, `model_evaluation.py`) + SQLite — test: mover los 5 tests de `test_agendamiento.py` sin perder cobertura.
5. **Puerto desde Hackaton**: adaptador CSV reales (contrato v2), test de genericidad (T17), ThreatPulse con scoring, CLI pipeline.
6. **Arreglar el simulador en Hackaton** (crear `backend.py`, script y muestra) para dejar la suite en 131 GREEN, o portarlo a sentinel con la sanción progresiva (T21+T22 juntos — misma unidad de comportamiento).
7. **T18 realimentación** (uno solo para ambos lados): decisiones → recalibración de umbrales + reentrenamiento acumulado + F1 en consola.
8. Exportes faltantes: tablas Power BI, Maltego CE.
9. Verificación final: ambas suites, E2E con CSVs reales en sentinel, bandit + pip-audit + barrido anti-hardcode (IPs/fechas/cuentas en `src/` y `motor/`), y revisión de que los tests previos siguen GREEN.

### Fase 3 — Qué NO tocar
- Los 117 tests de Hackaton y sus contratos (son la especificación ejecutable).
- La demo de sentinel end-to-end (login → cargar → procesar → caso → decisión).
- Las decisiones de matices §3 (Proteger externo, nada automático, sanción solo de dispositivo).
- Los CSVs reales de 5M (gitignorados, no commitear).

---

## 6. Riesgos del cambio (según la lista de riesgos del orquestador)

- **Riesgo alto — item 1 (datos/estado)**: migrar JSONL → SQLite puede perder bitácora existente. Mitigación: script de migración con test de idempotencia + copia del `backend/estado/` antes.
- **Riesgo alto — item 3 (contratos compartidos)**: cambiar `config.py` a YAML toca reglas que el resto del motor consume. Mitigación: test differential (misma entrada, misma salida antes/después).
- **Riesgo medio — item 4 (concurrency)**: no aplica hoy (local, single-user).
- **Riesgo de entrega**: el hackatón corre 26–30 nov; estimar esfuerzo de Fase 2 antes de comprometer alcance.

---

*Documento generado para revisión humana. No se modificó ningún código en este análisis.*
