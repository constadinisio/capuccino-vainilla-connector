# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# No generar .pyc y salida sin buffer (mejores logs en contenedores).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instalar dependencias primero (mejor cacheo de capas).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Usuario no-root por seguridad + directorio de logs escribible por él.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app/logs
USER appuser

# Por defecto el log va a un path escribible por appuser (sobreescribible por env).
ENV LOG_FILE=/app/logs/sync.log

EXPOSE 8000

# Por defecto levanta el servidor de webhooks.
ENTRYPOINT ["capuccino-vainilla"]
CMD ["serve"]
