#!/usr/bin/env bash
set -euo pipefail

# Repo directory can be provided via env (REPO_DIR); defaults to $HOME/day-news
REPO_DIR="${REPO_DIR:-${HOME:-/home/$(id -un)}/day-news}"

# Determine which user to run the digest as. Prefer RUN_AS, else owner of REPO_DIR, else SUDO_USER/USER
if [ -n "${RUN_AS:-}" ]; then
  RUN_USER="$RUN_AS"
else
  # Try to detect owner of the repo directory
  if command -v stat >/dev/null 2>&1; then
    RUN_USER="$(stat -c '%U' "$REPO_DIR" 2>/dev/null || true)"
  fi
  if [ -z "${RUN_USER:-}" ] || [ "$RUN_USER" = "root" ]; then
    RUN_USER="${SUDO_USER:-${USER:-$(id -un)}}"
  fi
fi

LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/digest.log"

/usr/bin/logger -t day-news "Starting digest as $RUN_USER from $REPO_DIR"
printf '%s Starting digest as %s from %s\n' "$(date -Is)" "$RUN_USER" "$REPO_DIR" >> "$LOG_FILE"

# Execute the digest script as the repo owner/user
if ! runuser -l "$RUN_USER" -c "\"$REPO_DIR/run_digest.sh\"" >> "$LOG_FILE" 2>&1; then
  status=$?
else
  status=0
fi

/usr/bin/logger -t day-news "Digest run exit status: $status"
printf '%s Digest exit status: %s\n' "$(date -Is)" "$status" >> "$LOG_FILE"
