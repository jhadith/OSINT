# Política de seguridad

Sentinel Salud es un prototipo del equipo ESPEThreat para el Hackatón Código Confianza 2026. Trabaja solo con datos sintéticos o con los datasets entregados por el reto, y corre en local.

## Reportar una vulnerabilidad

No abras un issue público. Usa **Security > Report a vulnerability** en este repositorio (aviso privado de GitHub) o escribe directamente al equipo. Incluye:

- qué componente está afectado (motor, backend o web),
- pasos para reproducirlo,
- el impacto que esperas.

Respondemos en un máximo de 3 días hábiles durante el hackatón.

## Lo que nunca debe llegar al repositorio

- Datasets reales: `datos/*.csv`.
- El estado del backend: `backend/estado/`, que incluye usuarios, bitácora y la tabla de reidentificación.
- Tokens o claves, como `TELEGRAM_BOT_TOKEN`, `SONAR_TOKEN` o un `.env`.

El pipeline (`.github/workflows/devsecops.yml`) bloquea los cambios si Gitleaks encuentra un secreto. Si subes uno por error, **rótalo de inmediato**: borrarlo del historial no basta.

## Controles automáticos

Ver [DEVSECOPS.md](DEVSECOPS.md).
