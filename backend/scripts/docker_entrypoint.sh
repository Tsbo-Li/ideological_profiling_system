#!/usr/bin/env sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
WORKERS="${GUNICORN_WORKERS:-2}"
THREADS="${GUNICORN_THREADS:-4}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] DATABASE_URL is required" >&2
  exit 1
fi

echo "[entrypoint] waiting for database..."
python - <<'PY'
import os, time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
engine = create_engine(url, pool_pre_ping=True, future=True)
deadline = time.time() + 60
last_err = None
while time.time() < deadline:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print("[entrypoint] database ready")
        raise SystemExit(0)
    except Exception as e:  # noqa: BLE001
        last_err = e
        time.sleep(1.5)
print(f"[entrypoint] database not ready: {last_err}")
raise SystemExit(1)
PY

echo "[entrypoint] init db (create_all)..."
python -m scripts.init_db || true

echo "[entrypoint] starting api server..."
exec gunicorn "api_server.app:create_app()" \
  --bind "${HOST}:${PORT}" \
  --workers "${WORKERS}" \
  --threads "${THREADS}" \
  --timeout 180 \
  --log-level "${LOG_LEVEL}"
