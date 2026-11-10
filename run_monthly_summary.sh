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

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python "$REPO_DIR/scripts/generate_monthly_summary.py" "$@"
"$REPO_DIR/scripts/publish_site.sh"
