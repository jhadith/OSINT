# Cómo correr Sentinel Salud (Windows, CMD)

Necesitas Python 3.11 o superior. Node.js 20 o superior solo hace falta si vas a modificar la consola. Todo corre en tu equipo; no se conecta a ningún sistema real.

## Tres plataformas

El sistema son tres piezas complementarias con fronteras claras:

| Pieza | Dónde vive | Acceso | Qué hace |
|---|---|---|---|
| **Consola SOC** | raíz `/`, pantallas tras `/ingresar` | interno, con login por rol | analista, jefe, TI, salud y auditoría; incluye la **bandeja interna de denuncias** (gestión) |
| **Proteger — portal de denuncias** | `/denuncia` | externo, público, sin login | recibe y consulta denuncias de afiliados; alimenta al SOC, pero no es pantalla de la consola |
| **Simulador de chatbot / HBVF** | pantalla «Citas del chatbot» dentro de la consola | módulo externo al SOC que solo alimenta | aporta hipótesis de posibles tramitadores; nada automático sobre personas o citas |

## Con Docker (recomendado para la demo)

Solo necesitas **Docker Desktop**. Levanta la consola y PostgreSQL juntos.

```
cd C:\sentilel-salud\sentinel
copy .env.example .env
notepad .env                      (cambia POSTGRES_PASSWORD)
copy "C:\ruta\Registros_conexiones_FW_10_2026.csv" datos\firewall_octubre_2026.csv
copy "C:\ruta\Registros_conexiones_sist_med_....csv" datos\sistema_medico_octubre_2026.csv
docker compose up -d --build
```

Abre **http://127.0.0.1:8000**. La primera vez descarga las imágenes base y compila (unos minutos, con internet); después arranca en segundos.

| Para | Comando |
|---|---|
| Ver si está sano | `docker compose ps` (debe decir *healthy*) |
| Ver los registros | `docker compose logs -f app` |
| Apagar (conserva los datos) | `docker compose down` |
| Borrar todo, incluida la base | `docker compose down -v` |
| Pasar datos de una instalación sin Docker | `docker compose cp backend\estado\. app:/data/estado` y luego `docker compose exec app python -m app.migrar_postgres` |

Qué hace la configuración:
- La consola solo escucha en `127.0.0.1` (no queda expuesta a la red del evento) y PostgreSQL no publica ningún puerto: solo la app lo ve.
- La app corre con un usuario sin privilegios. El estado va al volumen `estado` y la base al volumen `pgdata`, así que sobreviven a reinicios.
- Los CSV de `datos\` se montan solo lectura y nunca entran a la imagen. `.env` (claves y token de Telegram) tampoco entra a la imagen ni a Git.
- Para Telegram real, llena `SENTINEL_TELEGRAM=enviar`, `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en `.env`.

## Forma rápida sin Docker

Doble clic en **ARRANCAR.bat**. La primera vez crea el entorno de Python para Windows (`.venv-win`) e instala todo; luego abre la consola en http://127.0.0.1:8000.

## 1. Instalar (una sola vez)

```
cd C:\sentilel-salud\sentinel
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

El zip ya trae la consola compilada en `web\dist`, y el backend la sirve en la misma dirección que la API: para la demo basta un solo programa y no necesitas Node.js. Solo si cambias algo de la consola, vuelve a compilarla:

```
cd web
npm install
npm run build
cd ..
```

## 2. Poner los datos

Copia los dos CSV del reto a la carpeta `datos` y **cámbiales el nombre** para que no aparezca el nombre de la institución en pantalla:

```
copy "C:\ruta\Registros_conexiones_FW_10_2026.csv" datos\firewall_octubre_2026.csv
copy "C:\ruta\Registros_conexiones_sist_med_....csv" datos\sistema_medico_octubre_2026.csv
```

La carpeta `datos_ejemplo` ya trae datos sintéticos listos (firewall, sistema médico y chatbot de citas). Sirven para una demo rápida: se procesan en unos 10 segundos. Con los datasets completos (10 millones de filas) el análisis tarda unos 3 minutos.

## 3. Arrancar

```
cd C:\sentilel-salud\sentinel
.venv\Scripts\activate
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre **http://127.0.0.1:8000** en el navegador.

- Consola del SOC: entra con un rol. Usuarios `jefe`, `analista`, `ti`, `salud`, `auditor`; contraseña `demo2026`.
- Portal público de denuncias: **http://127.0.0.1:8000/denuncia** (no pide inicio de sesión).
- Documentación de la API: http://127.0.0.1:8000/docs

La primera vez la consola está vacía: entra como `analista` o `ti`, ve a **Cargar datos**, elige los archivos y pulsa **Procesar**. Verás los diez pasos en vivo.

Para cambiar la contraseña de demostración antes de crear los usuarios: `set SENTINEL_CLAVE_DEMO=otra_clave` (los usuarios se crean la primera vez en `backend\estado\usuarios.json`; borra ese archivo para recrearlos).

## 4. Alertas por Telegram (opcional)

Sin configurar nada, las alertas críticas se generan en **modo simulación** y quedan en la bitácora. Para enviarlas de verdad, antes de `uvicorn`:

```
set SENTINEL_TELEGRAM=enviar
set TELEGRAM_BOT_TOKEN=el_token_que_te_dio_BotFather
set TELEGRAM_CHAT_ID=el_id_del_chat
python -m app.telegram
```

El último comando manda un mensaje de prueba. **El token nunca va en el código, en Git ni en capturas de pantalla.**

## 5. Modo desarrollo (opcional)

Si vas a cambiar la consola, deja el backend corriendo y en otra ventana:

```
cd C:\sentilel-salud\sentinel\web
npm run dev
```

y abre http://127.0.0.1:5173 (recarga sola al guardar).

## 6. Pruebas y revisiones de seguridad

```
cd C:\sentilel-salud\sentinel\motor
python -m pytest -q
cd ..\backend
python -m pytest -q
cd ..
python -m bandit -q -r backend\app motor\motor -ll
pip-audit -r backend\requirements.txt
```

## Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| "No se pudo contactar al servidor local" | El backend no está corriendo o se cerró la ventana de `uvicorn`. |
| La página muestra "Aún no hay datos para mostrar" | Falta correr un análisis en **Cargar datos**. |
| "Cuenta bloqueada" al ingresar | Cinco contraseñas equivocadas. Espera 5 minutos o reinicia `uvicorn`. |
| En **Cargar datos** no aparecen tus CSV | Revisa que estén en `sentinel\datos` y que terminen en `.csv`. |
| `uvicorn` no se reconoce | Activa el entorno: `.venv\Scripts\activate`. |

## Qué no se debe subir a Git

`datos\*.csv`, `backend\estado\` (usuarios, bitácora, análisis y la tabla de reidentificación), `.venv`, `web\node_modules` y `web\dist`. El `.gitignore` ya los excluye.

## Novedades de esta versión

- **Reporte de inteligencia en PDF** con los 8 entregables (fuentes y metodología, adversarios, inteligencia estratégica, táctica, operativa y técnica, escenarios IPE y conclusiones): botón en la Vista ejecutiva.
- **Tendencias + OSINT**: ver la versión 4 (solo fuentes oficiales).
- **Correlaciones** (antes Relaciones): coincidencias firewall ⟷ sistema médico por caso.
- **Tickets de reglas**: el analista pide crear, ajustar o desactivar una regla; TI la ve con un contador en el menú, responde y todo queda en la bitácora (aviso por Telegram si está configurado).
- Vista ejecutiva con gráficos y el escudo de ESPEThreat en el ingreso y en el menú.

## Cambios de la versión 3

- **Power BI**: un solo libro de Excel (`sentinel_powerbi.xlsx`) con una hoja y una tabla por tema. En Power BI Desktop: *Obtener datos > Libro de Excel* y marcar las tablas.
- **Maltego**: un solo grafo (`sentinel_maltego.mtgx`). En Maltego: *File > Open*.
- **Informe gerencial** en PDF.
- El menú muestra solo las secciones del rol; las demás se ocultan. Si alguien escribe la dirección a mano, el servidor la rechaza y lo registra en la bitácora.

## Cambios de la versión 4

- **Tablero de una pantalla** (menú «Tablero»): cinco pestañas sin desplazamiento (Resumen, Amenazas internas, Citas y fraude, Amenazas externas, Impacto en el negocio). Cada tarjeta se amplía con un clic (o se cierra con Esc) y tiene un botón «Ir a la sección». Probado en 1440×900 y en 1366×768 (proyector).
- **Amenazas de todas las secciones en el tablero**: casos, anomalías, citas del chatbot, denuncias, contenido reportado por el personal y amenazas externas, cada una conectada a sus riesgos (R1–R11) y a las dimensiones del negocio que golpea.
- **Impacto en el negocio** basado en la matriz de riesgos: cinco dimensiones (atención médica, datos de salud y LOPDP, acceso justo a citas, confianza y reputación, costos y sanciones). Exposición = probabilidad viva × impacto de cada riesgo en esa dimensión. El modelo está en `backend/app/fijos/impacto_negocio.json`. El **informe gerencial (PDF)** ahora explica, riesgo por riesgo, el proceso afectado, qué pasaría y la consecuencia operativa, legal, reputacional y de costos.
- **Solo fuentes oficiales** en Tendencias: CISA KEV, NVD, avisos de CISA e INCIBE-CERT y avisos PSIRT de Fortinet, Palo Alto y Ubuntu. Se quitaron Google dorks, Exploit-DB, blogs, medios y feeds comunitarios.

## PostgreSQL

Sin configurar nada, Sentinel usa SQLite (archivo en `backend\estado`). Para usar PostgreSQL:

1. Crea la base (una vez), por ejemplo con pgAdmin o:
   ```
   psql -U postgres -c "CREATE DATABASE sentinel;"
   ```
2. Antes de arrancar:
   ```
   set SENTINEL_DB_URL=postgresql://postgres:TU_CLAVE@localhost:5432/sentinel
   ```
3. Si ya tenías datos en SQLite (bitácora, decisiones, denuncias, tickets, listas), cópialos una vez:
   ```
   cd backend
   python -m app.migrar_postgres
   ```

Las tablas se crean solas. La bitácora, las decisiones y los registros son **de solo agregar** también en PostgreSQL (un disparador rechaza cualquier UPDATE o DELETE, incluso desde psql). Si PostgreSQL no responde, la consola sigue funcionando sobre SQLite y el tablero muestra «SQLite (respaldo)» en lugar de «PostgreSQL». La caché de lecturas OSINT sigue en un archivo local porque es solo caché.
