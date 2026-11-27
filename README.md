# Sentinel Salud

Consola local de inteligencia de amenazas para proteger los datos de salud de afiliados y jubilados. Prototipo del equipo ESPEThreat para el Hackatón Código Confianza 2026, reto 3. Trabaja solo con los datasets del reto y con datos sintéticos; no se conecta a sistemas reales.

Para instalar y arrancar: **[COMO_CORRER.md](COMO_CORRER.md)**. Con Docker: `copy .env.example .env`, cambia la clave y `docker compose up -d --build`.

## Qué hace

1. **Carga y procesa los registros del mes** (firewall, sistema médico y, opcionalmente, el chatbot de citas). La pantalla muestra en vivo cada paso: lectura y validación, normalización, reglas, cruce de fuentes, machine learning, agendamiento, priorización y protección de datos personales.
2. **Detecta y explica** los incidentes: reglas, correlación entre fuentes con corrección de desfase de reloj e Isolation Forest. Cada caso trae su evidencia, su rango normal y qué hacer.
3. **Matriz de riesgos dinámica**: el impacto de cada riesgo es fijo; la probabilidad sale de la evidencia del análisis activo y de las decisiones del analista. Si se descarta un caso, la matriz baja.
4. **Citas del chatbot (HBVF)**: busca orígenes que reservan citas para muchos pacientes, como un tramitador. Distingue cuidadores y operadores autorizados. Nada se cancela ni se bloquea solo.
5. **Canal de denuncias**: los afiliados denuncian sin cédula ni nombre y reciben un código de seguimiento. El contacto denunciado se cruza con las citas (patrón HG-07). El SOC responde desde su bandeja.
6. **Control de accesos por rol** con bitácora: jefatura, analista, TI, personal de salud y auditoría ven solo lo suyo. Contraseñas con PBKDF2, bloqueo tras cinco intentos y nombres reales solo con un motivo registrado.
7. **Verificar contenido** para el personal de salud: revisa enlaces e imágenes sospechosos sin abrirlos y permite avisar al SOC.
8. **Inteligencia compartible**: reglas Sigma, indicadores, STIX 2.1 y MISP. Alertas críticas por Telegram (simuladas si no hay token).

## Tres plataformas

El producto son tres piezas complementarias, con fronteras claras:

1. **Consola SOC** (interna, con login): las pantallas del analista, jefe, TI, salud y auditoría —vista ejecutiva, casos, investigación, carga, inteligencia, verificación, bitácora y la **bandeja de denuncias (interna)**. Solo accede personal con rol y cada pantalla exige su permiso.
2. **Proteger — portal de denuncias** (externo al SOC, público, sin login, `/denuncia`): el canal donde afiliados y jubilados reportan y consultan con su código. Alimenta al SOC por la ingesta, pero **no es un módulo de la consola SOC ni cuenta dentro de sus pantallas**.
3. **Simulador de chatbot / HBVF** (fuera del SOC, solo alimenta): el módulo de citas del chatbot analiza orígenes y aporta **hipótesis** a la consola (pantalla «Citas del chatbot»). No decide ni actúa: nada automático sobre personas o citas.

## Estructura

```
sentinel/
├── motor/          detección y análisis (Python, pandas, scikit-learn)
├── backend/        API local con FastAPI: acceso, análisis, denuncias, riesgos, bitácora
├── web/            consola y portal público (React + Vite)
├── datos/          aquí van los CSV del reto (no se suben a Git)
└── datos_ejemplo/  datos sintéticos para una demo rápida
```

## Panel de estado de CI

El equipo de TI tiene en **Técnico > Estado de CI** (`/ci`) el resumen de los diez checks del pipeline de GitHub Actions. Lo escribe el job `resumen-ci` en `web/public/estado-ci.json` y la consola solo lee ese archivo: no consulta GitHub ni usa tokens. Hasta la primera ejecución real se muestra un JSON de ejemplo. Ver [DEVSECOPS.md](DEVSECOPS.md).

## Reglas que respeta

- Solo datos sintéticos o los datasets entregados por el reto. Ningún logo, nombre ni texto institucional en pantalla.
- Seudónimos en todas las vistas; la tabla de reidentificación nunca sale del equipo ni va a Git.
- Ninguna acción automática sobre personas o citas: el sistema recomienda y una persona decide.
- Pruebas: `pytest` en motor y backend, Bandit, pip-audit. OWASP ZAP solo contra `localhost`.
