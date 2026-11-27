# Sentinel Salud · Motor de detección y análisis

Lee los dos CSV del reto (y, si se le da, el registro sintético del chatbot de citas), detecta, correlaciona, prioriza y deja `salidas/*.json` para el backend. Normalmente lo lanza el backend desde la pantalla "Cargar datos"; también se puede correr a mano.

## Cómo correrlo (Windows, CMD)

```
cd sentinel\motor
python -m motor --fw ..\datos\firewall_octubre_2026.csv --med ..\datos\sistema_medico_octubre_2026.csv
```

Escribe:
- `salidas/alertas.json`, `salidas/resumen_motor.json`, `salidas/ml.json`: lo que lee la API.
- `restringido/sal.txt` y `restringido/tabla_reidentificacion.csv`: solo para el analista autorizado. No van a Git ni a la API.

Opciones:
- `--sin-ml` salta el modelo, que es lo más lento.
- `--salidas carpeta` y `--restringido carpeta` cambian dónde se escribe.

- `--citas archivo.csv` activa el módulo de agendamiento; `--reportes archivo.txt` le pasa los contactos denunciados.

## Qué hace

| Paso | Módulo | Qué hace |
|---|---|---|
| 1 | `ingesta.py` | Lee por partes de 500.000 filas, detecta utf-8 o cp1252 y descarta fechas inválidas sin detenerse. Del firewall no guarda las 4,3 millones de IPs en texto: guarda un hash y después recupera solo las filas de las alertas |
| 2 | `reglas_fw.py` | Ráfagas por IP hacia el servidor médico. Con 3 o más puertos es escaneo; con 80 % o más negado es fuerza bruta; si son SSH permitidos, posible fuga. También cuenta los servicios sin cifrado permitidos |
| 3 | `reglas_med.py` | Accesos fallidos masivos por cuenta en 24 h, extracción masiva (transferencias o descargas en 1 min), cuenta con 5 eventos o menos en el mes que saca datos, cuentas usadas por 50 o más personas y acciones administrativas concentradas |
| 4 | `correlacion.py` | Une el firewall con el sistema médico por persona (`ivan.prieto` con `PRIETO ESTEVEZ IVAN`) y por hora, probando desfases de 0 y ±12 h |
| 5 | `ml.py` | Isolation Forest por usuario y hora (firewall) y por cuenta y día (sistema médico). Cada alerta lleva su puesto en el ranking y las 3 variables más raras |
| 6 | `priorizacion.py` | Puntaje = probabilidad × impacto (1 a 25), gravedad, riesgo R1 a R8, pilar CID, salvaguarda HIPAA, acciones sugeridas y resumen |
| 7 | `salida.py` | Aplica seudónimos a usuarios y nombres, cambia las etiquetas con el nombre de la institución por términos neutros y escribe los JSON que lee el backend |

Las reglas usan puertos y acciones, no el nombre de la aplicación. En los datos de octubre la fuerza bruta por el puerto 23 venía etiquetada como "Sesion_Incompleta" y la ráfaga SSH como "No_Aplica".

En el sistema médico, la IP registrada en los ataques es la del servidor (10.10.100.30), no la del atacante. Por eso el cruce se hace por persona y hora.

Umbrales calibrados con los datos de octubre:
- El tráfico normal llega desde IPs casi únicas, con un máximo de 7 eventos por IP en el mes.
- Cada cuenta tiene unos 500 eventos al mes, con un máximo de 83 accesos fallidos.
- Solo una cuenta tiene 5 eventos o menos en el mes y alguna descarga.

Todos los umbrales están en `config.py`.

## Resultados de las pruebas

| Prueba | Resultado |
|---|---|
| Extractos reales (las filas de los 4 ataques + las muestras, 18.494 y 12.466 filas) | Los 4 ataques encontrados y correlacionados, con su IP y su cuenta |
| Volumen completo sintético (5 millones + 5 millones de filas, 2 núcleos) | 1,3 minutos y 1,4 GB de memoria, los 4 ataques encontrados y ninguna otra alerta Crítica o Alta |
| `pytest -q` (16 pruebas) | Ataques, gravedad, desfase de reloj, contrato de salida, que no salgan nombres, que no salga el nombre de la institución, datos mal formados |
| Bandit | Sin hallazgos |
| pip-audit | Sin vulnerabilidades conocidas en las versiones fijadas |

Las pruebas usan `tests/generador.py`, que arma datos sintéticos con la misma forma que los del reto y nombres inventados. Ningún dataset va al repositorio.

Para correr además la prueba con los extractos reales en tu equipo, arma una carpeta con `fw.csv` y `med.csv` y ejecuta `set SENTINEL_EXTRACTOS=esa_carpeta` antes de `pytest -q`.

## Numeración de casos

El motor numera los cuatro ataques igual que el informe:

| Caso | Ataque | Fecha |
|---|---|---|
| C1 | Fuerza bruta por Telnet | 10 oct |
| C2 | Escaneo de servicios | 19 oct |
| C3 | Posible fuga por SSH | 7 oct |
| C4 | Cuenta fantasma | 24 oct |

## Módulo de agendamiento médico (HBVF, `agendamiento.py`)

Es opcional y sigue la sección 14 del informe. Se activa con `--citas registros_chatbot.csv`:

```
python -m motor --fw ... --med ... --citas ..\datos_ejemplo\agendamiento_sintetico.csv [--reportes contactos.txt]
```

Columnas: `evento_id, cita_id, fecha_hora, accion, canal, sesion, paciente_ref, contacto_ref, rol_declarado, autorizacion_ref, ip, ja4, user_agent, respuesta_ms, especialidad, unidad`. Los pacientes y contactos llegan ya seudonimizados.

Qué hace:
- Agrupa sesiones en "orígenes" por vínculos verificables (mismo contacto, rotación de IP con la misma huella JA4, programa que no es navegador, nube o VPN el mismo día, IP fija en la misma hora). Un origen es una agrupación candidata, no una persona.
- Valida los siete patrones HG-01 a HG-07. Si falta un dato, el patrón queda "desconocido", nunca culpable. Las señales de la misma familia no cuentan como pruebas independientes y la técnica vale la mitad.
- Da a cada origen un estado: Sin hallazgo, Observación, Requiere revisión, Revisión prioritaria, Indeterminado o Explicado por contexto legítimo (cuidador u operador autorizado).
- Separa tres puntuaciones: anomalía (Isolation Forest), confianza de la evidencia y riesgo (probabilidad por impacto).
- Recomienda medidas no excluyentes (confirmar con el afiliado por su contacto verificado, revisar representación, revisión conjunta). Nada se bloquea ni se cancela solo.
- `--reportes` recibe los seudónimos de contactos denunciados por afiliados (patrón HG-07). El backend los arma con el canal de denuncias.

Prueba preliminar con `tests/generador_citas.py` (sintético): 4 tramitadores encontrados, 0 personas legítimas marcadas. Con datos sintéticos no se demuestra eficacia real (informe §14.6).

Salida: `salidas/agendamiento.json`.

## Salida para la consola web

Además de los JSON principales, el motor escribe `salidas/consola/` con las formas exactas de `frontend/src/api/types.ts`:
- `resumen.json`: indicadores con su rango de referencia y la interpretación por pilar CID.
- `casos.json`: casos C1 a C4 con evidencia de ambas fuentes, muestra de registros, recorrido y explicación.
- `serie.json`: 744 puntos por hora (puntuación del modelo, fallidos, SSH y transferencias).
- `anomalias_*.json`: ranking por usuario y por cuenta.
- `grafo.json` e `inteligencia.json`: grafo y Sigma, IoC, STIX y MISP.

Los rangos de referencia salen de los mismos datos: percentiles del comportamiento normal del mes, sin contar las IPs ni las cuentas de los casos. El backend (`../backend`) sirve estos archivos.
