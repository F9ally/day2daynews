# day-news

A static news site that rebuilds itself every day. A server fetches news, summarizes it with local Gemma3:4b (via Ollama), writes the result as plain JSON/MP3 files, and publishes them to GitHub. Cloudflare Pages deploys from GitHub, so the site is just static files on a CDN. There is no database or API.

```
server (cron) ──> scripts/*.py writes data/ + audio/ ──> scripts/publish_site.sh
                                                              │
                 main    : source + data/ (text history)  <───┤
                 deploy  : one orphan commit with the whole site + today's audio
                                                              │
                                              Cloudflare Pages (branch: deploy)
```

## Data layout

Served from the site root (`https://day2daynews.pages.dev`):

| Path | Contents |
| --- | --- |
| `data/index.json` | `{dates, months, audio}`: every published day/month and which audio file currently exists |
| `data/daily/YYYY-MM-DD.json` | `{date, compiled, items}` |
| `data/monthly/YYYY-MM.json` | `{month, compiled, items}` |
| `audio/YYYY-MM-DD.mp3`, `audio/monthly-YYYY-MM.mp3` | **Only the latest** daily and monthly narration are kept |

`data/` is committed to `main` (a few KB per day). `audio/` is gitignored and only ever lands on the force-pushed `deploy` branch, so MP3s never accumulate in git history.

## Daily digest

`run_digest.sh` (called by `run_digest_and_poweroff.sh` / `run_digest_no_poweroff.sh`):

1. `scripts/fetch_and_publish_digest.py` fetches 1 recent article per topic (9 topics), summarizes each with Ollama, writes `data/daily/<today>.json`, generates the Kokoro TTS narration as `audio/<today>.mp3` (deleting older daily audio) and rebuilds `data/index.json`.
2. `scripts/publish_site.sh` commits `data/` to `main` and force-pushes the site to the `deploy` branch.

Config lives in `ven.env` (copy `ven.env.example`): `NEWS_API_KEY`, `NEWS_API_URL`, optional `NEWS_LANG`, `NEWS_COUNTRY`, `NEWS_MAX`, `NEWS_NULLABLE`, `NEWS_QUERY`, `NEWS_FROM`, `NEWS_TO`, `OLLAMA_MODEL` (default `gemma3:4b`), SMTP settings.

`publish_site.sh` runs on the host and uses the repo's existing git credentials for `origin` (it needs push access to `main` and `deploy`). If you run the digest via `docker compose`, `data/` and `audio/` are mounted into the container; run `scripts/publish_site.sh` on the host afterwards.

## Monthly Summary

`scripts/generate_monthly_summary.py` aggregates a calendar month of `data/daily/*.json` into one Monthly Summary: one synthesized paragraph per topic (duplicates merged, topics never mixed), written to `data/monthly/<YYYY-MM>.json` plus `audio/monthly-<YYYY-MM>.mp3` (older monthly audio is deleted).

- Run it once per month (e.g. cron shortly after midnight UTC on the 1st) with `run_monthly_summary.sh`, or manually with `python scripts/generate_monthly_summary.py [--month YYYY-MM]`. It publishes the same way as the daily run.
- The mobile app surfaces this via a calendar icon on the daily summary screen; see `day-news-mobile/README.md`.

## Cloudflare Pages setup (one time)

Connect the GitHub repo, set the **production branch to `deploy`**, leave the build command empty and the output directory as `/`.
