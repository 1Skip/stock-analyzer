#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_PORT="${APP_PORT:-8501}"
APP_URL="http://localhost:${APP_PORT}"

echo "======================================"
echo "     Stock Analyzer Web Launcher"
echo "======================================"
echo

if [[ ! -f ".env" && -f ".env.example" ]]; then
  echo "[INFO] Local .env not found. Copy .env.example to .env and fill API keys if you want local LLM enabled."
  echo
fi

PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
fi

if [[ -z "${PYTHON_CMD}" ]]; then
  echo "[ERROR] Python was not found."
  echo "Please install Python 3.10 or newer:"
  echo "https://www.python.org/downloads/"
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[1/3] Creating local virtual environment: .venv"
  "${PYTHON_CMD}" -m venv .venv
fi

PY=".venv/bin/python"

echo "[2/3] Installing dependencies. First run may take a few minutes..."
"${PY}" -m pip install --upgrade pip
"${PY}" -m pip install -r requirements.txt

echo
echo "[3/3] Starting Streamlit..."
echo "Browser URL: ${APP_URL}"
echo "Press Ctrl+C to stop the server."
echo

if "${PY}" -c "import config; raise SystemExit(0 if config.SCHEDULE_ENABLED else 1)" >/dev/null 2>&1; then
  if pgrep -f "main.py --schedule" >/dev/null 2>&1; then
    echo "[INFO] Scheduler already appears to be running."
  else
    echo "[INFO] Starting scheduler in background..."
    nohup "${PY}" main.py --schedule >>scheduler.out.log 2>>scheduler.err.log &
  fi
else
  echo "[INFO] Scheduler is disabled. Set SCHEDULE_ENABLED=true in .env to enable local report/cache tasks."
fi

if command -v open >/dev/null 2>&1; then
  open "${APP_URL}" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${APP_URL}" >/dev/null 2>&1 || true
fi

"${PY}" -m streamlit run app.py --server.port "${APP_PORT}" --server.headless true --browser.gatherUsageStats false
