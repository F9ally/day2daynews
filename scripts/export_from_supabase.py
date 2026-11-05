"""
One-time migration to the static data/ layout.

    python scripts/export_from_supabase.py            # from Supabase (if still reachable)
    python scripts/export_from_supabase.py --from-out # from out/digest_<DD Month YYYY>.json

The --from-out mode rebuilds daily files from the local fallback JSON that every
digest run has always written to out/ (run it on the server, where the full
history is). Existing data/daily files are never overwritten in that mode.

Supabase mode reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from ven.env (or the
environment), writes data/daily/*.json and data/monthly/*.json, then rebuilds
data/index.json. Audio is not migrated (only the latest file is kept going
forward). Delete this script once the migration is done.
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

import requests

import site_io

PAGE = 500


def load_env() -> dict:
    vals = {}
    path = os.path.join(site_io.REPO_ROOT, "ven.env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip('"')
    return {**vals, **os.environ}


def fetch_all(base: str, key: str, table: str, order: str):
    rows, offset = [], 0
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    while True:
        r = requests.get(
            f"{base}/rest/v1/{table}",
            headers=headers,
            params={"select": "*", "order": f"{order}.asc", "limit": PAGE, "offset": offset},
            timeout=60,
        )
        if r.status_code != 200:
            raise RuntimeError(f"{table}: HTTP {r.status_code} - {r.text[:300]}")
        batch = r.json()
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def export_from_out() -> int:
    from fetch_and_publish_digest import compile_digest  # needs the project venv

    out_dir = os.path.join(site_io.REPO_ROOT, "out")
    pat = re.compile(r"^digest_(\d{2} [A-Za-z]+ \d{4})\.json$")
    written = 0
    for path in sorted(glob.glob(os.path.join(out_dir, "digest_*.json"))):
        m = pat.match(os.path.basename(path))
        if not m:
            continue
        try:
            date_iso = datetime.strptime(m.group(1), "%d %B %Y").strftime("%Y-%m-%d")
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
        except (ValueError, OSError):
            print(f"Skipping {os.path.basename(path)}")
            continue
        if not isinstance(items, list) or not items:
            continue
        if os.path.exists(os.path.join(site_io.DAILY_DIR, f"{date_iso}.json")):
            continue
        site_io.write_daily_json(date_iso, compile_digest(items), items)
        written += 1
    print(f"Rebuilt {written} daily digests from out/")
    print(f"Wrote {site_io.update_index()}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-out", action="store_true", help="rebuild from out/*.json instead of Supabase")
    if ap.parse_args().from_out:
        return export_from_out()
    env = load_env()
    base = (env.get("SUPABASE_URL") or "").rstrip("/")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base or not key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (ven.env or environment).")
        return 1

    daily = fetch_all(base, key, env.get("SUPABASE_TABLE", "daily_digests"), "date")
    for row in daily:
        site_io.write_daily_json(row["date"], row.get("compiled") or "", row.get("items") or [])
    print(f"Exported {len(daily)} daily digests")

    try:
        monthly = fetch_all(base, key, env.get("SUPABASE_MONTHLY_TABLE", "monthly_digests"), "month")
    except RuntimeError as e:
        print(f"Skipping monthly digests: {e}")
        monthly = []
    for row in monthly:
        site_io.write_monthly_json(row["month"], row.get("compiled") or "", row.get("items") or [])
    print(f"Exported {len(monthly)} monthly digests")

    print(f"Wrote {site_io.update_index()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
