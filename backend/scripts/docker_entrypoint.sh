#!/usr/bin/env sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
WORKERS="${GUNICORN_WORKERS:-2}"
THREADS="${GUNICORN_THREADS:-4}"
AUTO_INIT_ON_EMPTY="${AUTO_INIT_ON_EMPTY:-1}"

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

if [ "${AUTO_INIT_ON_EMPTY}" = "1" ]; then
  echo "[entrypoint] checking whether database is empty..."
  rc=0
  python - <<'PY' || rc=$?
import os
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
engine = create_engine(url, pool_pre_ping=True, future=True)

with engine.connect() as c:
    students = int(c.execute(text("SELECT COUNT(*) FROM students")).scalar() or 0)

if students == 0:
    print("[entrypoint] students table is empty, generating mock data...")
    raise SystemExit(10)
print("[entrypoint] init data check passed.")
raise SystemExit(0)
PY
  if [ "$rc" = "10" ]; then
    python -m scripts.generate_mock_data || true
  elif [ "$rc" != "0" ]; then
    echo "[entrypoint] init-data check failed with code ${rc}" >&2
    exit "$rc"
  fi
  rc2=0
  python - <<'PY' || rc2=$?
import os
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
engine = create_engine(url, pool_pre_ping=True, future=True)
with engine.connect() as c:
    topics = int(c.execute(text("SELECT COUNT(*) FROM social_hot_topics")).scalar() or 0)
if topics == 0:
    print("[entrypoint] social_hot_topics table is empty, seeding demo hot topics...")
    raise SystemExit(11)
print("[entrypoint] hot topics seed check passed.")
raise SystemExit(0)
PY
  if [ "$rc2" = "11" ]; then
    python -m scripts.seed_social_hot_topics || true
  elif [ "$rc2" != "0" ]; then
    echo "[entrypoint] hot-topics check failed with code ${rc2}" >&2
    exit "$rc2"
  fi
fi

echo "[entrypoint] runtime package versions..."
python - <<'PY'
import importlib

mods = ["numpy", "torch", "transformers", "sentence_transformers", "bertopic"]
for m in mods:
    try:
        mod = importlib.import_module(m)
        print(f"[entrypoint] {m}={getattr(mod, '__version__', 'unknown')}")
    except Exception as e:  # noqa: BLE001
        print(f"[entrypoint] {m}=<import failed: {e}>")
PY

echo "[entrypoint] starting api server..."
exec gunicorn "api_server.app:create_app()" \
  --bind "${HOST}:${PORT}" \
  --workers "${WORKERS}" \
  --threads "${THREADS}" \
  --timeout 180 \
  --log-level "${LOG_LEVEL}"
