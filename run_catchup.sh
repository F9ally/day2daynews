#!/usr/bin/env bash
# Safety net for a missed daily run (server was off at the scheduled time, no
# network, digest crashed, publish failed...). Run it from cron every 15 minutes:
#
#   */15 * * * * /home/ll/day-news/run_catchup.sh >> /home/ll/day-news/logs/catchup.log 2>&1
#
# Every run it:
#   - does nothing if another digest run is in progress
#   - if today's (UTC) digest exists: just re-tries publishing (silent no-op if already published)
#   - if it is missing and it's past NOT_BEFORE_UTC_HOUR (default 8, i.e. after the
#     normal scheduled run had its chance): waits for the network, then runs the
#     full digest + publish. It never powers the server off.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"
mkdir -p "$REPO_DIR/logs"

NOT_BEFORE_UTC_HOUR="${NOT_BEFORE_UTC_HOUR:-8}"

# One digest at a time; run_digest.sh takes the same lock for the scheduled run.
exec 9>"$REPO_DIR/.digest.lock"
flock -n 9 || exit 0
export DIGEST_LOCK_HELD=1

today="$(date -u +%F)"
hour=$((10#$(date -u +%H)))

if [ -f "data/daily/$today.json" ]; then
  exec "$REPO_DIR/scripts/publish_site.sh"
fi

[ "$hour" -ge "$NOT_BEFORE_UTC_HOUR" ] || exit 0

# Just after boot the network may not be up yet: wait up to ~5 minutes.
online=0
for _ in $(seq 1 20); do
  if curl -fsS -m 5 -o /dev/null https://gnews.io; then online=1; break; fi
  sleep 15
done
if [ "$online" -ne 1 ]; then
  echo "$(date -Is) [catchup] No network; will retry next run"
  exit 1
fi

echo "$(date -Is) [catchup] Digest for $today is missing; running it now"
"$REPO_DIR/run_digest.sh"
echo "$(date -Is) [catchup] Done"
