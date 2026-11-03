#!/usr/bin/env bash
# One command for a local review. Uses SQLite and the fictional Northline brand.
# Does not call Shopify or ShipHero. Ctrl-C stops both processes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d backend/.venv ]]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

export USE_SQLITE=true
export SQLITE_PATH="$ROOT/backend/inventory.db"
export DEMO_MODE=true
export AUTO_SEED=true
export SCHEDULER_ENABLED=true
export WARM_FORECASTS=true
export SECRET_KEY="${SECRET_KEY:-demo-only-not-for-production}"
export CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

cd "$ROOT/backend"
.venv/bin/python -m seed
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACK_PID=$!
cd "$ROOT/frontend"
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONT_PID=$!

cleanup() {
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "Inventory Intel is starting."
echo "  Product page:  http://127.0.0.1:5173/"
echo "  Today:         http://127.0.0.1:5173/today"
echo "  Sample login:  demo@northline.example / northline-demo"
echo "  API health:    http://127.0.0.1:8000/api/health"
echo "Mountain Time (Utah). Press Ctrl-C to stop."
echo ""
wait
