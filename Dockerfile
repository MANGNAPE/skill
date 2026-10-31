# Image Docker générique : fonctionne sur Railway, Fly.io, un VPS, Google Cloud Run…
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    SKILLUP_DB=/data/skillup.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html ./
COPY static ./static

# La base SQLite vit dans /data : montez un volume persistant sur ce dossier.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT} app:app"]
