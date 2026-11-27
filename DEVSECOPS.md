# DevSecOps en Sentinel Salud

El ciclo de desarrollo seguro del informe (numeral 9) ya está automatizado en `.github/workflows/devsecops.yml`. Corre en cada push a `main`, `dev` o `Pruebas`, en cada pull request y a mano desde **Actions > devsecops > Run workflow**. Todo se ejecuta dentro del runner de GitHub contra `127.0.0.1`: nunca toca sistemas reales ni la red del evento.

## Fases del informe y dónde se cumplen

| Fase | Control de seguridad | Herramienta | Dónde |
|---|---|---|---|
| 1. Planificar | STRIDE, matriz de riesgos, requisitos LOPDP / HIPAA / ISO 27002 | Informe | `Informe_Propuesta_Sentinel_Salud_ESPE.docx` |
| 2. Codificar | Secretos y datos fuera del repositorio | Gitleaks, `.gitignore`, pre-commit | Job `secretos` y `.pre-commit-config.yaml` |
| 2. Codificar | Estilo y errores comunes del código | ruff (backend, motor y pruebas) y oxlint sin advertencias (frontend) | Job `lint` |
| 2. Codificar | Revisión por pares | Pull requests con revisión obligatoria | Protección de rama (ver abajo) |
| 3. Construir | Dependencias con versión fija y sin vulnerabilidades conocidas | `requirements.txt` fijado, `pip-audit`, `npm audit` | Jobs `python` y `web` |
| 4. Probar (estática) | Código Python inseguro | Bandit | Job `python` |
| 4. Probar (estática) | SAST de Python y TypeScript | CodeQL (`security-extended`) | Job `codeql` |
| 4. Probar (estática) | SAST, calidad, duplicación y cobertura de pruebas | SonarQube Cloud con puerta de calidad | Job `sonarqube` |
| 4. Probar (dinámica) | Motor y API funcionan y detectan los casos; cobertura mínima de 95 % | pytest + pytest-cov (`.coveragerc` en `motor` y `backend`) | Job `python` |
| 4. Probar | Lógica del frontend (formato, navegación, cliente de la API, sesión); cobertura mínima de 95 % | Vitest + cobertura v8 | Job `web` |
| 4. Probar (dinámica) | Flujos completos en un navegador real: ingreso, decisión con motivo, reidentificación, permisos por rol, denuncia pública y XSS | Playwright (E2E) | Job `pruebas-dinamicas` |
| 4. Probar (dinámica) | Seguridad de la API en vivo: 401/403 por rol, cierre de sesión, path traversal, subida de archivos, CORS, anti-spam y bloqueo por fuerza bruta | pytest + httpx contra `127.0.0.1` | Job `pruebas-dinamicas` |
| 4. Probar (dinámica) | Vulnerabilidades web de la consola, del portal y de la API | OWASP ZAP baseline y API scan, solo sobre `127.0.0.1` | Job `dast` |
| 5. Liberar | Puerta de calidad aprobada y hash de los entregables | Todos los jobs en verde y SHA-256 | Job `liberar` (`SHA256SUMS.txt`) |
| 6. Desplegar | Ejecución local, entorno virtual y mínimo privilegio | venv, `permissions: contents: read` | `COMO_CORRER.md` y el workflow |
| 7. Operar | Seudónimos activos y bitácora de decisiones | Backend | `backend/app/` |
| 8. Monitorear | Falsos positivos, casos detectados y ajuste de umbrales | Bitácora y vista ejecutiva | Consola |

## Qué bloquea un cambio

El job `liberar` solo genera entregables si pasan `secretos`, `python`, `web`, `codeql`, `pruebas-dinamicas` y `dast`. Fallan en estos casos:

- Gitleaks encuentra un secreto en cualquier commit.
- Falla una prueba de `pytest` del motor o del backend, o de Vitest en el frontend.
- La cobertura del motor, del backend o de la lógica del frontend baja de 95 %.
- `ruff` u `oxlint` encuentran un problema.
- Bandit encuentra un problema de severidad media o alta.
- `pip-audit` o `npm audit` (nivel alto) encuentran una vulnerabilidad conocida.
- `oxlint` o la compilación de TypeScript fallan, o la interfaz menciona a la institución.
- Falla una prueba E2E de Playwright o una prueba de seguridad de la API en vivo.
- ZAP encuentra un problema marcado como `FAIL` en `.zap/rules.tsv`: falta de CSP, clickjacking, XSS, inyección SQL o errores expuestos. Las advertencias quedan en el reporte sin bloquear.

Los reportes quedan como artefactos de cada ejecución: `reportes-python` (pytest, cobertura y Bandit), `pruebas-dinamicas` (reporte HTML de Playwright con trazas, capturas y video de lo que falle, y JUnit de la API), `zap-*` (HTML y JSON de ZAP) y `entregables` (código, web compilada y `SHA256SUMS.txt`). Los hallazgos de CodeQL quedan en el artefacto `codeql-python` / `codeql-javascript-typescript` (archivo SARIF) y en el resumen de la ejecución; el job falla si hay alguno de nivel error. Si el administrador activa *Code scanning*, se puede quitar `upload: never` para verlos en **Security > Code scanning**.

## Publicar una versión

```bash
git tag v1.0.0
git push origin v1.0.0
```

El job `liberar` crea un release de GitHub con los paquetes y su `SHA256SUMS.txt`. Para verificar un paquete descargado: `sha256sum -c SHA256SUMS.txt`.

## Configuración que tienes que hacer en GitHub (una vez)

1. **Actions**: en *Settings > Actions > General*, permite que corran los workflows.
2. **Protección de la rama `main`**: en *Settings > Branches > Add rule*:
   - Exige pull request con al menos 1 aprobación.
   - Exige que pasen los checks `Secretos (Gitleaks)`, `Motor y backend (pytest, Bandit, pip-audit)`, `Consola web (lint, build, npm audit)`, `SAST (CodeQL)`, `Pruebas dinámicas (E2E Playwright y API en vivo)` y `DAST (OWASP ZAP sobre 127.0.0.1)`.
   - Bloquea los force push.
3. **Avisos de seguridad**: en *Settings > Code security* activa Secret scanning y Private vulnerability reporting. Las actualizaciones automáticas de Dependabot no se usan: las versiones se actualizan a mano y `pip-audit` / `npm audit` bloquean el pipeline si alguna tiene una vulnerabilidad conocida.
4. **CodeQL**: funciona sin configurar nada; guarda los resultados como artefacto. Para verlos en la pestaña Security, quien administra el repo debe activar *Settings > Code security > Code scanning* (en repos privados requiere GitHub Advanced Security) y quitar `upload: never` del workflow.
5. **SonarQube Cloud**:
   1. Entra a [sonarcloud.io](https://sonarcloud.io) con tu cuenta de GitHub.
   2. Crea el proyecto con **+ > Analyze new project**. Si `jhadith/osit` no aparece, quien administra el repo debe instalar la app de SonarQube Cloud en su cuenta. También puedes crearlo a mano dentro de tu organización.
   3. En el proyecto, *Administration > Analysis Method*: **desactiva Automatic Analysis**. El análisis lo hace el pipeline, y con los dos activos falla.
   4. Copia la **Organization Key** y la **Project Key**, que están en *Information*, y genera un token en *My Account > Security*.
   5. En GitHub, *Settings > Secrets and variables > Actions*:
      - pestaña **Secrets**: `SONAR_TOKEN` = el token;
      - pestaña **Variables**: `SONAR_ORGANIZATION` = la organization key y `SONAR_PROJECT_KEY` = la project key.
   6. Haz un push. El job `SonarQube Cloud (SAST + cobertura)` sube el análisis y la cobertura de pytest del motor y del backend, y falla si no pasa la puerta de calidad. Sin esos datos, solo deja un aviso.

6. **Clave de demo (opcional)**: el secreto `SENTINEL_CLAVE_DEMO` cambia la contraseña que usa el backend durante el escaneo DAST.

## Correr lo mismo en tu equipo

Linux o macOS:

```bash
./scripts/revision_seguridad.sh
```

Windows (CMD), desde la carpeta del proyecto con el entorno activado:

```
cd motor && python -m pytest -q && cd ..
cd backend && python -m pytest -q && cd ..
python -m bandit -q -r backend\app motor\motor -ll
pip-audit -r backend\requirements.txt
ruff check .
cd web && npm ci && npm run lint && npm run coverage && npm run build && npm audit --audit-level=high && cd ..
```

Antes de cada commit, para que los secretos ni siquiera salgan de tu equipo:

```bash
pip install pre-commit
pre-commit install
```

Pruebas dinámicas en local, con el backend corriendo en `127.0.0.1:8010` (`uvicorn app.main:app --host 127.0.0.1 --port 8010` desde `backend`):

```bash
cd pruebas_dinamicas/e2e
npm ci && npx playwright install chromium
SENTINEL_URL=http://127.0.0.1:8010 npx playwright test      # E2E
npx playwright show-report reporte                          # ver el reporte
cd ../api
SENTINEL_URL=http://127.0.0.1:8010 python -m pytest -v      # seguridad de la API
```

Corre primero las E2E y después las de la API: la última prueba bloquea a propósito la cuenta `ti` durante 5 minutos y el portal admite 5 denuncias por equipo cada 10 minutos. En Windows usa `set SENTINEL_URL=http://127.0.0.1:8010` antes de cada comando.

ZAP en local, con el backend corriendo en `127.0.0.1:8000`:

```bash
docker run --rm --network host -v "$PWD/.zap:/zap/wrk:rw" ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://127.0.0.1:8000/ -c rules.tsv -a -I -m 3 -r reporte_zap.html
```
