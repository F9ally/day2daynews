#!/usr/bin/env bash
# Publish the built site:
#   1. commit the (text-only) data/ folder to main
#   2. force-push a single-commit orphan `deploy` branch containing the whole
#      site plus today's audio. Cloudflare Pages deploys from `deploy`, so the
#      MP3s never pile up in git history.
#
# Idempotent: if nothing changed since the last successful publish this exits
# silently without touching git (so run_catchup.sh can call it every few
# minutes). Set FORCE=1 to publish anyway.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

STATE_FILE="$REPO_DIR/.published_state"
site_state() {
  find data audio index.html about.html site.webmanifest -type f 2>/dev/null \
    | LC_ALL=C sort | xargs sha256sum | sha256sum | cut -d' ' -f1
}

if [ "${FORCE:-0}" != "1" ] && [ -f "$STATE_FILE" ] && [ "$(site_state)" = "$(cat "$STATE_FILE")" ]; then
  exit 0
fi

REMOTE_URL="$(git remote get-url origin)"
STAMP="$(date -u +%F)"
GIT_NAME="$(git config user.name || echo day-news-bot)"
GIT_EMAIL="$(git config user.email || echo day-news-bot@users.noreply.github.com)"

# 1) data/ -> main (history of the text digests)
git pull --rebase --autostash -q origin main
git add data
if ! git diff --cached --quiet; then
  git commit -q -m "Update digest data $STAMP"
  git push -q origin HEAD:main
fi

# 2) build the deployable site in a scratch dir and force-push it as `deploy`
STAGE="$REPO_DIR/staging"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp index.html about.html site.webmanifest favicon-*.png icon-*.png "$STAGE"/
cp -r data "$STAGE/data"
[ -d audio ] && cp -r audio "$STAGE/audio"

cd "$STAGE"
git init -q -b deploy
git add -A
git -c user.name="$GIT_NAME" -c user.email="$GIT_EMAIL" commit -q -m "Site build $STAMP"
git push -q --force "$REMOTE_URL" deploy

cd "$REPO_DIR"
rm -rf "$STAGE"
site_state > "$STATE_FILE"   # only recorded after BOTH pushes succeeded
echo "[Publish] Pushed data to main and site to deploy ($STAMP)"
