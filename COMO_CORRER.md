# Cómo correr Sentinel Salud (Windows, CMD)

Necesitas Python 3.11 o superior. Node.js 20 o superior solo hace falta si vas a modificar la consola. Todo corre en tu equipo; no se conecta a ningún sistema real.

## 1. Instalar (una sola vez)

```
cd C:\sentinel-salud\sentinel
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
cd C:\sentinel-salud\sentinel
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
cd C:\sentinel-salud\sentinel\web
npm run dev
```

y abre http://127.0.0.1:5173 (recarga sola al guardar).

## 6. Pruebas y revisiones de seguridad

```
cd C:\sentinel-salud\sentinel\motor
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
