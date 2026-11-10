#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "[Error] Virtual environment not found at $VENV_DIR" >&2
  exit 1
fi

# One digest at a time (the scheduled run and run_catchup.sh can overlap).
# run_catchup.sh already holds this lock and sets DIGEST_LOCK_HELD.
if [ -z "${DIGEST_LOCK_HELD:-}" ]; then
  exec 9>"$REPO_DIR/.digest.lock"
  flock 9
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python "$REPO_DIR/scripts/fetch_and_publish_digest.py" "$@"
bash "$REPO_DIR/scripts/publish_site.sh"
