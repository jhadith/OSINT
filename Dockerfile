# Sentinel Salud: consola (React) + backend (FastAPI) + motor de análisis en una sola imagen.
#   docker compose up -d --build      → http://127.0.0.1:8000

ARG NODE_IMAGE=node:22-slim
ARG PYTHON_IMAGE=python:3.12-slim

# ---------- 1. compila la consola web ----------
FROM ${NODE_IMAGE} AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------- 2. imagen final ----------
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SENTINEL_ESTADO=/data/estado \
    SENTINEL_DATOS=/data/datos \
    SENTINEL_DB_SCHEMA=public
WORKDIR /app

# dependencias primero: se reutilizan mientras no cambien los requirements
COPY motor/requirements.txt motor/requirements.txt
COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install -r backend/requirements.txt

COPY motor/ motor/
COPY backend/ backend/
COPY rules/ rules/
COPY config/ config/
COPY datos_ejemplo/ datos_ejemplo/
COPY web/public/ web/public/
COPY --from=web /web/dist/ web/dist/

# usuario sin privilegios; el estado y los datos viven en volúmenes
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin sentinel \
 && mkdir -p /data/estado /data/datos \
 && chown -R sentinel:sentinel /data /app/backend
USER sentinel
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/acceso/roles', timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
