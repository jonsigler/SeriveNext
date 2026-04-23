FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; bcrypt 4.x ships manylinux wheels, no compiler needed.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# SQLite DB lives on a mounted volume so it survives deploys.
ENV DATABASE_URL=sqlite:////data/serivenext.db \
    PORT=8000 \
    SEED_ON_START=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:${PORT}/healthz || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
