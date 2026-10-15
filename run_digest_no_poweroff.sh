#!/usr/bin/env bash
set -euo pipefail

# Same as run_digest_and_poweroff.sh, but leaves the server running afterwards.
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

/usr/bin/logger -t day-news "Starting digest (no poweroff) as $RUN_USER from $REPO_DIR"
printf '%s Starting digest (no poweroff) as %s from %s\n' "$(date -Is)" "$RUN_USER" "$REPO_DIR" >> "$LOG_FILE"

# Execute the digest script as the repo owner/user.
# Capture the real exit status: under set -e a failing command would exit before we could log it.
set +e
runuser -l "$RUN_USER" -c "\"$REPO_DIR/run_digest.sh\"" >> "$LOG_FILE" 2>&1
status=$?
set -e

/usr/bin/logger -t day-news "Digest run exit status: $status"
printf '%s Digest exit status: %s\n' "$(date -Is)" "$status" >> "$LOG_FILE"

if [ "$status" -eq 0 ]; then
  msg="Digest completed successfully. Server left running."
else
  msg="Digest failed (exit $status). Server left running."
fi

/usr/bin/logger -t day-news "$msg"
printf '%s %s\n' "$(date -Is)" "$msg" >> "$LOG_FILE"

exit "$status"
