#!/usr/bin/env bash
# Convenience launcher for SeriveNext.
#   ./run.sh             - start server on http://localhost:8000
#   ./run.sh seed        - create DB and load demo data
#   ./run.sh reset       - wipe the SQLite DB (destroys all data)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install --quiet -r requirements.txt

case "${1:-serve}" in
  seed)
    python -m scripts.seed
    ;;
  reset)
    rm -f ./serivenext.db
    echo "Wiped serivenext.db"
    ;;
  serve)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
    ;;
  *)
    echo "Usage: $0 [serve|seed|reset]"
    exit 1
    ;;
esac
