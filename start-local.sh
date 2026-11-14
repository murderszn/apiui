#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export FRONTEND_PORT="${FRONTEND_PORT:-8080}"
export FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"

# Find a Python 3 interpreter that has Flask installed
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in \
    "$SCRIPT_DIR/.venv/bin/python3" \
    "$SCRIPT_DIR/venv/bin/python3" \
    "$(command -v python3 || true)" \
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3"; do
    if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c "import flask, flask_cors, pydantic_settings" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ Could not find a Python 3 interpreter with backend dependencies installed."
  echo "   Run: python3 -m pip install -r backend/requirements.txt"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js is required to serve the frontend (node server.js)."
  exit 1
fi

mkdir -p "$SCRIPT_DIR/uploads" "$SCRIPT_DIR/generated_apis"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "🛑 Shutting down APIUI servers..."
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  wait >/dev/null 2>&1 || true
}

trap cleanup INT TERM EXIT

echo "🚀 Starting APIUI Self-Hosted Stack..."
echo "   Python: $PYTHON_BIN"
echo "   Backend:  http://localhost:${PORT} (listening on ${HOST}:${PORT})"
echo "   Frontend: http://localhost:${FRONTEND_PORT} (listening on ${FRONTEND_HOST}:${FRONTEND_PORT})"
echo "   MCP HTTP: http://localhost:${PORT}/mcp"
echo ""

"$PYTHON_BIN" "$SCRIPT_DIR/backend/main.py" &
BACKEND_PID=$!

node "$SCRIPT_DIR/server.js" &
FRONTEND_PID=$!

# Exit if either process stops unexpectedly
while true; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "❌ Backend process exited."
    exit 1
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "❌ Frontend process exited."
    exit 1
  fi
  sleep 1
done
