"""
scripts/site_io.py

Tiny helpers for the static-site data layout (no database):

    data/index.json              {"dates": [...desc], "months": [...desc], "audio": {...}}
    data/daily/YYYY-MM-DD.json   {"date", "compiled", "items", "created_at"}
    data/monthly/YYYY-MM.json    {"month", "compiled", "items", "created_at"}
    audio/YYYY-MM-DD.mp3         only the latest daily file is kept
    audio/monthly-YYYY-MM.mp3    only the latest monthly file is kept

`data/` is committed to main (text only). `audio/` is gitignored and only ever
reaches the published `deploy` branch (see scripts/publish_site.sh).
"""
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
DAILY_DIR = os.path.join(DATA_DIR, "daily")
MONTHLY_DIR = os.path.join(DATA_DIR, "monthly")
AUDIO_DIR = os.path.join(REPO_ROOT, "audio")

_DAILY_JSON = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
_MONTHLY_JSON = re.compile(r"^(\d{4}-\d{2})\.json$")
_DAILY_AUDIO = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(mp3|wav)$")
_MONTHLY_AUDIO = re.compile(r"^monthly-(\d{4}-\d{2})\.(mp3|wav)$")


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_daily_json(date_iso: str, compiled: str, items: List[Dict[str, Any]]) -> str:
    path = os.path.join(DAILY_DIR, f"{date_iso}.json")
    _write_json(path, {"date": date_iso, "compiled": compiled, "items": items, "created_at": _now_iso()})
    return path


def write_monthly_json(month: str, compiled: str, items: List[Dict[str, Any]]) -> str:
    path = os.path.join(MONTHLY_DIR, f"{month}.json")
    _write_json(path, {"month": month, "compiled": compiled, "items": items, "created_at": _now_iso()})
    return path


def read_daily_rows(first_day: str, last_day: str) -> List[Dict[str, Any]]:
    """Return daily digest rows with first_day <= date <= last_day, ascending."""
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(DAILY_DIR):
        return rows
    for name in sorted(os.listdir(DAILY_DIR)):
        m = _DAILY_JSON.match(name)
        if not m or not (first_day <= m.group(1) <= last_day):
            continue
        try:
            with open(os.path.join(DAILY_DIR, name), "r", encoding="utf-8") as f:
                rows.append(json.load(f))
        except (OSError, ValueError) as e:
            print(f"[Data] Skipping unreadable {name}: {e}")
    return rows


def write_audio(name: str, data: bytes) -> str:
    """Write audio/<name> and delete every other audio file of the same kind
    (daily vs monthly), so only the latest narration is ever kept."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    kind = _MONTHLY_AUDIO if name.startswith("monthly-") else _DAILY_AUDIO
    path = os.path.join(AUDIO_DIR, name)
    with open(path, "wb") as f:
        f.write(data)
    for other in os.listdir(AUDIO_DIR):
        if other != name and kind.match(other):
            os.remove(os.path.join(AUDIO_DIR, other))
    return path


def _latest_audio(pattern: "re.Pattern[str]") -> Optional[Dict[str, str]]:
    if not os.path.isdir(AUDIO_DIR):
        return None
    hits = sorted(((m.group(1), n) for n in os.listdir(AUDIO_DIR) if (m := pattern.match(n))), reverse=True)
    return {"key": hits[0][0], "file": f"audio/{hits[0][1]}"} if hits else None


def update_index() -> str:
    """Rebuild data/index.json from what is on disk."""
    def keys(directory: str, pattern: "re.Pattern[str]") -> List[str]:
        if not os.path.isdir(directory):
            return []
        return sorted((m.group(1) for n in os.listdir(directory) if (m := pattern.match(n))), reverse=True)

    index = {
        "dates": keys(DAILY_DIR, _DAILY_JSON),
        "months": keys(MONTHLY_DIR, _MONTHLY_JSON),
        "audio": {
            "daily": _latest_audio(_DAILY_AUDIO),      # {"key": "2026-11-05", "file": "audio/2026-11-05.mp3"}
            "monthly": _latest_audio(_MONTHLY_AUDIO),  # {"key": "2026-10", "file": "audio/monthly-2026-10.mp3"}
        },
    }
    path = os.path.join(DATA_DIR, "index.json")
    _write_json(path, index)
    return path
