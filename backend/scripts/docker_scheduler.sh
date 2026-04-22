#!/usr/bin/env sh
set -eu

SCHEDULE_HOUR="${SCHEDULE_HOUR:-0}"
SCHEDULE_MINUTE="${SCHEDULE_MINUTE:-10}"
RUN_ON_STARTUP="${RUN_ON_STARTUP:-1}"
GENERATE_PLOT="${GENERATE_PLOT:-0}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[scheduler] DATABASE_URL is required" >&2
  exit 1
fi

echo "[scheduler] waiting for database..."
python - <<'PY'
import os, time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
engine = create_engine(url, pool_pre_ping=True, future=True)
deadline = time.time() + 120
last_err = None
while time.time() < deadline:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print("[scheduler] database ready")
        raise SystemExit(0)
    except Exception as e:  # noqa: BLE001
        last_err = e
        time.sleep(2)
print(f"[scheduler] database not ready: {last_err}")
raise SystemExit(1)
PY

run_jobs() {
  now="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[scheduler] ${now} start: crawl hot topics"
  python -m scripts.crawler_hot_rank || true
  echo "[scheduler] ${now} start: clustering + warning refresh"
  if [ "${GENERATE_PLOT}" = "1" ]; then
    python -m scripts.run_profile_warning_refresh --generate-plot || true
  else
    python -m scripts.run_profile_warning_refresh --no-generate-plot || true
  fi
  echo "[scheduler] $(date '+%Y-%m-%d %H:%M:%S') all jobs done"
}

if [ "${RUN_ON_STARTUP}" = "1" ]; then
  run_jobs
fi

echo "[scheduler] daily schedule at ${SCHEDULE_HOUR}:${SCHEDULE_MINUTE}"
while true; do
  sleep_seconds="$(python - <<'PY'
from datetime import datetime, timedelta
import os

hour = int(os.environ.get("SCHEDULE_HOUR", "0"))
minute = int(os.environ.get("SCHEDULE_MINUTE", "10"))
now = datetime.now()
target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
if target <= now:
    target += timedelta(days=1)
print(max(1, int((target - now).total_seconds())))
PY
)"
  echo "[scheduler] next run in ${sleep_seconds}s"
  sleep "${sleep_seconds}"
  run_jobs
done
