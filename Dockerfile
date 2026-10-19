FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir yt-dlp

COPY serve.py .
COPY web/ web/

# encarta.db (se construye en el portátil y se sube con deploy_pepecono.sh) y
# cache.db (fotos de Deezer y vídeos de YouTube ya resueltos) viven en /data,
# un bind mount: sobreviven a los rebuilds y la base se puede cambiar en caliente.
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8765 \
    ENCARTA_DB=/data/encarta.db ENCARTA_CACHE=/data/cache.db

EXPOSE 8765

HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

CMD ["python3", "-I", "serve.py"]
