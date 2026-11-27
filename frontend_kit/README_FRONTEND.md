# Sentinel Salud · Frontend

Responsable: Sebastián. Motor: Ariel y Dani.

El frontend es la consola del analista del SOC y del jefe de seguridad. Muestra lo que encuentra el motor y deja registrar la decisión del analista. No analiza datos: todo lo lee de la API.

## Qué hay en este kit

| Archivo | Para qué |
|---|---|
| `api_mock/*.json` | Respuestas de ejemplo de la API, con los 4 casos reales y seudónimos. Con esto trabajas sin esperar al motor |
| `tokens.css` | Colores, fuentes y bordes. Úsalos como variables, no escribas colores sueltos |
| `wireframe.png` | Boceto de la pantalla Resumen y del Detalle de alerta |
| `gen_mock.py` | Script que generó los JSON, por si hay que cambiar un ejemplo |

Los puntajes del modelo en `ml.json` son valores de ejemplo; los reales los entrega el motor.

## Reglas que no se rompen

1. Ningún logo, nombre, color ni texto del IESS en pantalla. En la interfaz se habla de "sistema médico" y "servidor médico". El nombre del producto es Sentinel Salud y abajo del menú va "Equipo ESPEThreat".
2. Colores de la ESPE (verde y amarillo de `tokens.css`). Los colores de gravedad son solo para alertas.
3. La gravedad siempre se muestra con texto e icono, no solo con color (● Crítica, ▲ Alta, ■ Media, ○ Baja).
4. Nunca mostrar nombres de personas. Solo seudónimos (`P-xxxxxx`, `U-xxxxxx`), IPs y cuentas del sistema.
5. Nada desde internet en tiempo de ejecución: sin CDN, sin Google Fonts, sin analítica. Todo se instala con npm y corre en local.
6. En el encabezado debe verse "Datos sintéticos".

## Tecnología sugerida

React + Vite + react-router, y Recharts para los gráficos. Si prefieres HTML, CSS y JavaScript sin framework, también sirve: lo que importa es respetar el contrato de la API.

```
npm create vite@latest sentinel-web -- --template react
cd sentinel-web
npm install react-router-dom recharts
```

Copia `api_mock/` dentro de `public/` y `tokens.css` dentro de `src/`.

Toda la comunicación con el motor va en un solo archivo, `src/api.js`, para que cambiar de los JSON de ejemplo a la API real sea una línea:

```js
const MOCK = true;  // false cuando el motor esté listo
const BASE = MOCK ? "/api_mock" : "http://127.0.0.1:8000/api";

export const get = (ruta) =>
  fetch(MOCK ? `${BASE}/${ruta}.json` : `${BASE}/${ruta}`).then((r) => r.json());

export const resumen = () => get("resumen");
export const alertas = () => get("alertas");
export const alerta = (id) => get(`alertas/${id}`);
export const mitre = () => get("mitre");
export const riesgos = () => get("riesgos");
export const controles = () => get("controles");
export const ml = () => get("ml");
export const iocs = () => get("iocs");
export const bitacora = () => get("bitacora");

export async function decidir(id, decision, motivo) {
  if (MOCK) return { ok: true, id, decision, motivo };  // en modo de ejemplo solo se guarda en memoria
  const r = await fetch(`${BASE}/alertas/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, motivo }),
  });
  return r.json();
}
```

## Contrato de la API

El motor expone esto en `http://127.0.0.1:8000/api`. Los JSON de `api_mock/` tienen exactamente la misma forma. Si alguien necesita cambiar un campo, se avisa en el grupo antes.

| Método y ruta | Archivo de ejemplo | Devuelve |
|---|---|---|
| `GET /resumen` | `resumen.json` | Totales de registros, alertas por gravedad, conteo por día y por pilar CID |
| `GET /alertas` | `alertas.json` | Lista corta de alertas para la tabla |
| `GET /alertas/{id}` | `alertas/{id}.json` | Detalle: resumen, línea de tiempo, técnicas, acciones sugeridas, riesgo |
| `POST /alertas/{id}/decision` | (no hay) | Recibe `{decision: "confirmada" \| "descartada", motivo}` y devuelve `{ok, id, decision, motivo}` |
| `GET /mitre` | `mitre.json` | Técnicas MITRE ATT&CK con número de alertas |
| `GET /riesgos` | `riesgos.json` | Riesgos R1 a R8 con probabilidad, impacto y nivel |
| `GET /controles` | `controles.json` | Controles ISO 27002 / EGSI con su estado |
| `GET /ml` | `ml.json` | Ranking del modelo por usuario y por cuenta |
| `GET /iocs` | `iocs.json` | IPs, cuentas, reglas Sigma y enlaces de descarga |
| `GET /bitacora` | `bitacora.json` | Decisiones del analista y avisos enviados por Telegram |
| `GET /exportes/{stix\|misp\|sigma}` | (no hay) | Descarga del archivo |

Campos de una alerta en la lista: `id, caso, titulo, gravedad, puntaje, fuente, inicio, fin, ip_origen, cuenta, tecnicas, estado, aviso_telegram`. El detalle agrega `resumen, acciones, linea, tecnicas_detalle, riesgo, cid, usuario_firewall, persona, eventos_firewall, eventos_sistema_medico`.

Valores posibles:
- `gravedad`: Crítica, Alta, Media, Baja
- `fuente`: firewall, sistema_medico, correlacion
- `estado`: pendiente, confirmada, descartada
- fechas como texto `AAAA-MM-DD HH:MM:SS`

## Pantallas

Cada pantalla corresponde a un nivel de inteligencia del informe.

1. **Resumen (estratégica).** Para el jefe de seguridad.
   - Cuatro tarjetas: registros analizados, críticas pendientes, ataques detectados y controles con brecha.
   - Barras de alertas por gravedad.
   - Mapa de calor 5×5 de la matriz de riesgos, con los R1 a R8 ubicados en su celda.
   - Tabla con las últimas alertas críticas y altas. Al hacer clic se abre el detalle.
2. **Alertas (operativa).** Tabla con todas las alertas, con filtros de gravedad, fuente y estado en una fila arriba, y orden por gravedad e inicio.
3. **Detalle de alerta (operativa).**
   - Encabezado: gravedad, título, horas, fuente y si ya se avisó por Telegram.
   - Bloques "Qué pasó", "Técnicas MITRE" y "Línea de tiempo" (sistema médico en verde, firewall en azul).
   - Acciones sugeridas.
   - Campo de motivo y botones "Confirmar ataque" y "Descartar". No se puede decidir sin motivo; al decidir cambia el estado.
4. **Táctica.**
   - Técnicas MITRE agrupadas por táctica, con el número de alertas de cada una.
   - Tabla de adversarios: IP, cuenta, alertas y técnicas.
   - Ranking del modelo (`ml.json`).
5. **Técnica (IoC).**
   - Listas de IPs y cuentas con un botón para copiar.
   - Reglas Sigma.
   - Botones de descarga de STIX, MISP y Sigma.
6. **Riesgos y controles.** Tabla de R1 a R8 con su tratamiento y tabla de controles, con el estado como etiqueta (Brecha, Propuesto, Se implementa, Cubierto).
7. **Bitácora.** Decisiones del analista (quién, cuándo, qué y por qué) y avisos de Telegram.

Mira `wireframe.png`: barra lateral verde oscuro, ítem activo en verde con borde amarillo, tarjetas blancas sobre fondo gris claro.

## Orden de trabajo

| Bloque | Entrega |
|---|---|
| 1 | Proyecto creado, `tokens.css`, barra lateral, encabezado, rutas vacías |
| 2 | Pantalla Resumen con los datos de ejemplo |
| 3 | Lista de alertas y Detalle con la decisión, que es lo que se muestra en la demo |
| 4 | Táctica, Técnica, Riesgos y Bitácora |
| 5 | Cambiar `MOCK` a `false` y probar con el motor de Ariel y Dani |

Para la demo de 10 minutos importa sobre todo el flujo Resumen → alerta crítica → detalle → confirmar. Las demás pantallas pueden ser más simples.

## Antes de subir a Git

- `node_modules/` va en `.gitignore`.
- No hay tokens ni claves en el código.
- Busca "IESS" en todo el proyecto: no debe aparecer en la interfaz.
- Con `npm run build` el proyecto compila sin errores.
