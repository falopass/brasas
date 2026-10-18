# Imagen del backend de BRASA para Cloudflare Containers (o cualquier plataforma de contenedores).
FROM python:3.12-slim

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
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
