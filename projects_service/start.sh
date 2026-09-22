#!/usr/bin/env bash
# projects_service launcher — idempotent + reboot-safe via @reboot cron (no sudo).
# Install once:
#   @reboot /home/mahmoud/v2/projects_service/start.sh >> /tmp/projects_reboot.log 2>&1
set -u
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=${PORT:-5004}
LOG=${LOG:-/tmp/projects_5004.log}

# clear stale listeners so we always run the CURRENT code (before the UP check)
pkill -f "$APP_DIR/app.py" 2>/dev/null || true
sleep 1

# already listening on :PORT ? -> exact match on ss address (0.0.0.0:5004 | *:5004 | [::]:5004)
if ss -tln 2>/dev/null | awk '{print $4}' | grep -Eq "(:${PORT})$"; then
  echo "[start.sh] projects_service already UP on :${PORT} — nothing to do"
  exit 0
fi

cd "$APP_DIR"
if [ ! -f app.py ]; then
  echo "[start.sh] FATAL: ${APP_DIR}/app.py missing" >&2
  exit 1
fi
mkdir -p database

nohup python3 "$APP_DIR/app.py" >> "$LOG" 2>&1 < /dev/null &
disown

sleep 5
if ss -tln 2>/dev/null | awk '{print $4}' | grep -Eq "(:${PORT})$"; then
  echo "[start.sh] projects_service UP on :${PORT} (pid $! → ${LOG})"
  exit 0
fi
echo "[start.sh] FAILED — last log:" >&2
tail -20 "$LOG" >&2
exit 1
