#!/usr/bin/env bash
#
# Start SchemaBridge locally: the Python API on 8000, the web app on 3000.
#
# The web app proxies /api to the API so the browser stays on one origin, which
# is what the session cookie and the same-origin check both expect.
set -euo pipefail

cd "$(dirname "$0")"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

if [[ ! -f .env.local ]]; then
  echo "No .env.local found. Copy .env.example to .env.local and fill it in."
  exit 1
fi

if [[ ! -d backend/.venv ]]; then
  echo "Setting up the Python environment (first run only)…"
  python3 -m venv backend/.venv
  ./backend/.venv/bin/pip install -q --upgrade pip
  ./backend/.venv/bin/pip install -q -e "backend[dev]"
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing web dependencies (first run only)…"
  (cd frontend && npm install --silent)
fi

# Stop both halves together, however this script exits.
cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "API  → http://127.0.0.1:${API_PORT}"
(cd backend && PORT="$API_PORT" ../backend/.venv/bin/python -m uvicorn main:app \
  --port "$API_PORT" --reload --log-level warning) &

echo "Web  → http://localhost:${WEB_PORT}"
(cd frontend && BACKEND_ORIGIN="http://127.0.0.1:${API_PORT}" \
  npx next dev --port "$WEB_PORT") &

sleep 4
echo
echo "Open http://localhost:${WEB_PORT}"
echo "Sample files are in backend/fixtures/samples/"
echo "Press Ctrl-C to stop both."
wait
