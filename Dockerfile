# Imagen del backend de BRASA para Cloudflare Containers (o cualquier plataforma de contenedores).
# Digest del índice multi-arquitectura de python:3.12-slim al 2026-10-21.
# Para actualizarlo: docker buildx imagetools inspect python:3.12-slim
FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BRASA_DATA_DIR=/data \
    BRASA_SCHEDULER=0

WORKDIR /app
COPY requirements.lock .
RUN pip install --require-hashes -r requirements.lock && useradd --create-home --uid 10001 brasa && mkdir -p /data && chown brasa /data
COPY backend backend
COPY web web
USER brasa

EXPOSE 8000
# Solo el Worker llega a este puerto: se confía en sus cabeceras X-Forwarded-*.
# En una instalación sin proxy delante (VPS), FORWARDED_ALLOW_IPS debe restringir
# de quién se acepta X-Forwarded-For; ver docs/OPERACION.md.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS-*}\""]
