#!/bin/sh
# Start the API. Optionally load the synthetic catalog when the database is empty.
set -eu

if [ "${SEED_ON_START:-false}" = "true" ]; then
  python -m seed --if-empty
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
