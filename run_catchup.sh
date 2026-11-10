#!/usr/bin/env bash
# Safety net for a missed daily run. Runs ONCE per boot, 30 minutes after the
# server starts (systemd timer deploy/systemd/day-news-catchup.timer, or cron
# "@reboot sleep 1800 && .../run_catchup.sh"). It:
#   - waits for any digest run that is still going (shared lock)
#   - if today's (UTC) digest exists: re-tries publishing (silent no-op if
#     already published), covering "built but push failed"
#   - otherwise waits for the network, then builds + publishes it
# It never powers the server off. Days the server was off entirely are not backfilled.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"
mkdir -p "$REPO_DIR/logs"
# Manual run in a terminal: show output AND append it to the log file, so
# logs/catchup.log always has the full history. (From the systemd timer / cron
# stdout is not a terminal and is already appended to that file, so skip this.)
if [ -t 1 ]; then
  exec > >(tee -a "$REPO_DIR/logs/catchup.log") 2>&1
fi
log() { echo "$(date -Is) [catchup] $*"; }

# One digest at a time. Wait (up to 1h) for a scheduled run still in progress.
exec 9>"$REPO_DIR/.digest.lock"
if ! flock -w 3600 9; then log "Another digest run still holds the lock after 1h; giving up"; exit 1; fi
export DIGEST_LOCK_HELD=1

today="$(date -u +%F)"

if [ -f "data/daily/$today.json" ]; then
  log "Digest for $today exists; making sure it is published"
  exec bash "$REPO_DIR/scripts/publish_site.sh"
fi

online=0
for _ in $(seq 1 20); do
  if curl -fsS -m 5 -o /dev/null https://gnews.io; then online=1; break; fi
  sleep 15
done
if [ "$online" -ne 1 ]; then log "No network after 5 minutes; giving up until next boot"; exit 1; fi

log "Digest for $today is missing; running it now"
bash "$REPO_DIR/run_digest.sh"
log "Done"
