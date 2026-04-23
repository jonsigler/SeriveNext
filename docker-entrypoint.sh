#!/usr/bin/env bash
set -euo pipefail

# Make sure the data dir exists (Fly volume, docker-compose volume, or local bind mount).
mkdir -p /data

# Refuse to start with the default dev secret in production-looking environments.
if [ "${SECRET_KEY:-dev-secret-change-me}" = "dev-secret-change-me" ] || [ -z "${SECRET_KEY:-}" ]; then
  echo "WARNING: SECRET_KEY is unset or default. Set it via env / Fly secrets before exposing the app publicly." >&2
fi

# Seed demo data the very first time the container boots against an empty volume.
# Set SEED_ON_START=0 to skip (e.g. for a clean production deployment where you
# want to register users manually).
if [ "${SEED_ON_START:-1}" = "1" ] && [ ! -f /data/serivenext.db ]; then
  echo "Seeding demo data..."
  python -m scripts.seed
fi

exec "$@"
