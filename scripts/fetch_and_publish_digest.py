import time
start = time.time()
import json
import os
import re
import html as html_lib
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import site_io
from io import BytesIO
import threading
import subprocess
import sys
import io
from pydub import AudioSegment
import warnings

# External news API defaults
GNEWS_TOP_HEADLINES_URL = "https://gnews.io/api/v4/top-headlines"
DEFAULT_NEWS_LANG = "en"
DEFAULT_NEWS_COUNTRY = "us"
DEFAULT_NEWS_MAX = 10

# Suppress specific third-party warnings that are expected/harmless
# 1) Torch RNN dropout warning when num_layers=1 (emitted by upstream TTS stack)
warnings.filterwarnings(
    "ignore",
    message="dropout option adds dropout after all but last recurrent layer",
    category=UserWarning,
)
# 2) weight_norm deprecation warning from torch utils (emitted by upstream TTS stack)
warnings.filterwarnings(
    "ignore",
    message="torch.nn.utils.weight_norm is deprecated",
    category=FutureWarning,
)


# --- Config helpers ---------------------------------------------------------

def load_env_file(path: str) -> Dict[str, str]:
    vals: Dict[str, str] = {}
    if not os.path.exists(path):
        return vals
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return vals


def env(name: str, default: Optional[str] = None, env_map: Optional[Dict[str, str]] = None) -> Optional[str]:
    if name in os.environ:
        return os.environ[name]
    if env_map and name in env_map:
        return env_map[name]
    return default


def load_config() -> Dict[str, Any]:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(repo_root, "ven.env")
    env_map = load_env_file(env_path)

    def pick(k: str, d: Optional[str] = None) -> Optional[str]:
        return env(k, d, env_map)

    cfg: Dict[str, Any] = {}
    api_key = pick("GNEWS_API_KEY") or pick("NEWS_API_KEY") or pick("NEWSDATA_API_KEY", "")
    cfg["NEWS_API_KEY"] = api_key or ""
    cfg["NEWS_API_URL"] = (pick("NEWS_API_URL") or "").strip() or GNEWS_TOP_HEADLINES_URL
    cfg["NEWS_LANG"] = (pick("NEWS_LANG", DEFAULT_NEWS_LANG) or DEFAULT_NEWS_LANG)
    cfg["NEWS_COUNTRY"] = (pick("NEWS_COUNTRY") or "").strip()
    cfg["NEWS_MAX"] = (pick("NEWS_MAX", str(DEFAULT_NEWS_MAX)) or str(DEFAULT_NEWS_MAX)).strip()
    cfg["NEWS_NULLABLE"] = (pick("NEWS_NULLABLE") or "").strip()
    cfg["NEWS_QUERY"] = (pick("NEWS_QUERY") or "").strip()
    cfg["NEWS_FROM"] = (pick("NEWS_FROM") or "").strip()
    cfg["NEWS_TO"] = (pick("NEWS_TO") or "").strip()
    cfg["OLLAMA_MODEL"] = pick("OLLAMA_MODEL", "gemma3:4b") or "gemma3:4b"
    cfg["SMTP_HOST"] = pick("SMTP_HOST")
    cfg["SMTP_PORT"] = pick("SMTP_PORT", "465")
    cfg["SMTP_USER"] = pick("SMTP_USER")
    cfg["SMTP_PASS"] = pick("SMTP_PASS")
    cfg["SMTP_SENDER"] = pick("SMTP_SENDER")
    cfg["SMTP_TO"] = pick("SMTP_TO")
    return cfg


# --- Topics ----------------------------------------------------------------

def get_topics() -> List[Dict[str, str]]:
    return [
        {"category": "general"},
        {"category": "world"},
        {"category": "us"},
        {"category": "business"},
        {"category": "technology"},
        {"category": "entertainment"},
        {"category": "sports"},
        {"category": "science"},
        {"category": "health"},
    ]


CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "entertainment": [
        "film", "movie", "tv", "series", "celebrity", "music", "concert", "festival",
        "box office", "trailer", "actor", "actress", "netflix", "hbo"
    ],
    "science": [
        "research", "scientist", "space", "nasa", "laboratory", "physics", "biology",
        "astronomy", "experiment", "quantum", "biotech", "discovery"
    # --- Ollama bootstrap -------------------------------------------------------

    ],
    "health": [
        "health", "hospital", "medical", "vaccine", "virus", "disease", "clinic",
        "doctor", "patient", "treatment", "wellness", "public health"
    ],
}


def _is_article_relevant(category: Optional[str], article: Dict[str, Any]) -> bool:
    if not category:
        return True
    cat = category.lower()
    keywords = CATEGORY_KEYWORDS.get(cat)
    if not keywords:
        return True
    text = " ".join([
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        str(article.get("content") or ""),
    ]).lower()
    hits = sum(1 for kw in keywords if kw in text)
    return hits >= 1


# --- News API fetchers -----------------------------------------------------

def _build_news_params(cfg: Dict[str, Any], category: str, page: int) -> Dict[str, Any]:
    raw_max = cfg.get("NEWS_MAX")
    try:
        max_value = max(1, min(int(raw_max), 100)) if raw_max else DEFAULT_NEWS_MAX
    except (TypeError, ValueError):
        max_value = DEFAULT_NEWS_MAX

    params: Dict[str, Any] = {
        "category": (category or "").lower() or "general",
        "lang": cfg.get("NEWS_LANG") or DEFAULT_NEWS_LANG,
        "max": max_value,
        "page": page,
        "apikey": cfg.get("NEWS_API_KEY"),
    }

    country = cfg.get("NEWS_COUNTRY") or DEFAULT_NEWS_COUNTRY
    if country and country.lower() != "any":
        params["country"] = country

    nullable = cfg.get("NEWS_NULLABLE")
    if nullable:
        params["nullable"] = nullable

    query = cfg.get("NEWS_QUERY")
    if query:
        params["q"] = query

    date_from = cfg.get("NEWS_FROM")
    if date_from:
        params["from"] = date_from

    date_to = cfg.get("NEWS_TO")
    if date_to:
        params["to"] = date_to

    return params


def try_gnews_api(cfg: Dict[str, Any], category: str, page: int = 1) -> Optional[Dict[str, Any]]:
    if not cfg.get("NEWS_API_KEY"):
        print("[News API] Missing API key; set GNEWS_API_KEY or NEWS_API_KEY in ven.env.")
        return None

    params = _build_news_params(cfg, category, page)
    url = cfg.get("NEWS_API_URL") or GNEWS_TOP_HEADLINES_URL

    try:
        response = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        print(f"[News API] Request error for {category} page {page}: {exc}")
        return None

    quota_left = response.headers.get("X-RateLimit-Remaining") or response.headers.get("x-ratelimit-remaining")
    if quota_left is not None:
        print(f"[News API] Quota left: {quota_left}")

    if response.status_code != 200:
        snippet = response.text[:200] if response.text else "<no body>"
        print(f"[News API] HTTP {response.status_code}: {snippet}")
        return None

    try:
        data = response.json()
    except ValueError:
        print("[News API] Failed to decode JSON response.")
        return None

    articles = data.get("articles") or []
    if not isinstance(articles, list):
        print("[News API] Unexpected payload format; 'articles' is not a list.")
        return None

    if not articles:
        print(f"[News API] No articles returned for {category} (page {page}).")
        return None

    # Return the first article; callers handle duplicate / relevance filtering.
    article = articles[0]
    url_field = article.get("url") or (article.get("source") or {}).get("url")
    content = article.get("content") or article.get("description") or ""

    return {
        "title": article.get("title"),
        "description": article.get("description") or "",
        "url": url_field,
        "published_at": article.get("publishedAt") or article.get("published_at"),
        "content": content,
        "quota_left": quota_left,
    }


def fetch_news_article_with_retries(
    cfg: Dict[str, Any],
    category: str,
    max_attempts: int = 1,
    global_exclude: Optional[set] = None,
) -> Optional[Dict[str, Any]]:
    seen: set = set()
    for attempt in range(1, max_attempts + 1):
        article = try_gnews_api(cfg, category, page=attempt)
        if not article:
            print(f"[{category}] No article found on attempt {attempt}; retrying...")
            continue

        url = article.get("url") or ""
        normalized = url.strip().lower() if url else ""
        title_key = (article.get("title") or "").strip().lower()
        key = normalized or title_key
        # Cross-category deduplication: avoid articles seen in other sections
        if global_exclude and key and key in global_exclude:
            print(f"[{category}] Skipping globally-duplicate result; retrying...")
            continue
        if key and key in seen:
            print(f"[{category}] Skipping duplicate result; retrying...")
            continue

        if not _is_article_relevant(category, article):
            print(f"[{category}] Skipping off-topic result; retrying...")
            if key:
                seen.add(key)
            continue

        if key:
            seen.add(key)
        return article

    print(f"[{category}] All attempts failed.")
    return None


# --- Summarization via Ollama ----------------------------------------------

def summarize_with_ollama(model: str, topic: str, title: str, content: str, url: Optional[str]) -> str:
    prompt = f"""
You are a professional news editor creating concise summaries for a daily news digest.

Category: {topic}

Instructions:
1. Create a COMPLETE, engaging headline (8-15 words) that captures the key story
2. Write a clear, factual summary well summarising each article provided, highlighting the key points and interesting details (3-5 sentences)
3. Use third-person voice only
4. Focus on facts from the article - no speculation or opinions
5. Make the headline self-contained and informative
6. Do NOT repeat the headline text in the summary

Article Title: {title}
Source URL: {url or 'N/A'}

Article Content:
{(content[:4000] + '...') if content and len(content) > 4000 else (content or '')}

Required Format (provide exactly this):
Headline: [Your complete, engaging headline here]
Summary: [Your 3-5 sentence factual summary here]
""".strip()

    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    endpoint = f"{host}/api/chat"
    payload = {
        "model": model or "gemma3:4b",
        "messages": [
            {"role": "system", "content": "You are a concise news editor."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.1, "num_predict": 256},
        "stream": False,
    }

    for attempt in range(1, 4):
        print(f"[Ollama] Summarizing (attempt {attempt}) for: {title}")
        try:
            resp = requests.post(endpoint, json=payload, timeout=90)
            if resp.status_code != 200:
                print(f"[Ollama] HTTP {resp.status_code} for {title}: {resp.text[:200]}")
            else:
                try:
                    data = resp.json()
                except ValueError as e_json:
                    print(f"[Ollama] JSON decode error: {repr(e_json)}")
                    data = None
                if data:
                    message = data.get("message", {}).get("content") if isinstance(data, dict) else None
                    if message:
                        print(f"[Ollama] Success via HTTP API for: {title}")
                        return message.strip()
                    else:
                        print(f"[Ollama] API returned no message content for: {title}")
        except requests.RequestException as e_http:
            print(f"[Ollama] HTTP request failed on attempt {attempt}: {repr(e_http)}")
        time.sleep(1)

    print(f"[Ollama] All attempts failed for: {title}")
    return f"Headline: {title}\nSummary:\n• [ERROR: Could not summarize with {model or 'gemma3:4b'} after 3 attempts]"


# --- Formatting -------------------------------------------------------------

def _strip_markdown(text: str) -> str:
    """Remove common markdown syntax and collapse whitespace."""
    if not text:
        return ""
    t = text
    # Remove fenced code blocks
    t = re.sub(r"```[\s\S]*?```", " ", t)
    # Strip headings like #, ## at start of lines
    t = re.sub(r"^\s*#{1,6}\s+", "", t, flags=re.MULTILINE)
    # Bold/italic markers
    t = t.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    # Inline code backticks
    t = t.replace("`", "")
    # Replace markdown bullets with separators
    t = re.sub(r"^[\s>*\-•]+", "• ", t, flags=re.MULTILINE)
    # Remove stray markdown links [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    # Collapse multiple newlines to a single space
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _clean_for_html(summary: str) -> str:
    """Sanitize model output for safe HTML embedding: strip markdown and escape HTML."""
    # First, strip markdown and decode any HTML entities the model may have emitted (e.g., &#x27;)
    clean = _strip_markdown(summary)
    clean = html_lib.unescape(clean)
    # Escape any HTML to avoid injecting tags
    clean = html_lib.escape(clean)
    return clean


def _is_recent(published_at: Optional[str], hours: int = 30) -> bool:
    if not published_at:
        return False
    try:
        # Attempt to parse common ISO formats
        s = published_at.strip()
        # Normalize 'Z' suffix
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        return age.total_seconds() <= hours * 3600
    except Exception:
        return False


def _is_digest_day_utc(published_at: Optional[str]) -> bool:
    if not published_at:
        return False
    try:
        s = published_at.strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
    # Treat anything published in the previous 48 hours as relevant for the digest
        age = datetime.now(timezone.utc) - dt_utc
        return age.total_seconds() <= 48 * 3600
    except Exception:
        return False


def _extract_headline_and_points(cleaned_text: str) -> Tuple[str, List[str]]:
    """Parse the model output to extract the Headline and bullet points.

    Notes:
    - Avoid capturing the "Summary:" portion in the headline even if newlines
      were collapsed during cleaning.
    - Do not alter the summary content itself; just return it as a single paragraph.
    """
    HEADLINE_MAX_LEN = 180  # allow longer headlines to avoid premature cut-offs
    headline = ""
    summary = ""
    # Capture headline up to the beginning of "Summary:" or end of string
    m = re.search(r"Headline:\s*(.+?)(?:\s+Summary:|$)", cleaned_text, re.IGNORECASE | re.DOTALL)
    if m:
        headline = m.group(1).strip()
        if len(headline) > HEADLINE_MAX_LEN:
            headline = headline[:HEADLINE_MAX_LEN].rstrip()
    # Capture summary after "Summary:"
    sm = re.search(r"Summary:\s*(.+)", cleaned_text, re.IGNORECASE | re.DOTALL)
    if sm:
        summary = sm.group(1).strip()
    return headline, [summary] if summary else []


def compile_digest(items: List[Dict[str, str]]) -> str:
    """
    Given a list of items with keys: topic (title-cased), title, summary.
    Build safe HTML with topic header, bold article headline, and per-line bullet paragraphs.
    """
    topic_emojis = {
        "general": "📰",
        "world": "🌍",
        "us": "🦅",
        "business": "💰",
        "technology": "💻",
        "entertainment": "🎭",
        "sports": "🏅",
        "science": "🔬",
        "health": "🩺",
    }
    seen = set()
    html_blocks = []
    # Helper to strip leading topic labels the model may add
    topic_label_re = re.compile(r"^(General|World|US|Business|Technology|Entertainment|Sports|Science|Health)\s*:\s*", re.IGNORECASE)
    for it in items:
        topic_title = it.get("topic", "General")
        summary = it.get("summary", "")
        art_title = it.get("title", "Untitled")
        key = topic_title.lower()
        if key in seen:
            continue
        seen.add(key)
        emoji = topic_emojis.get(key, "❓")
        # Skip error summaries entirely from the website output
        if "[ERROR:" in summary:
            continue
        # Remove a leading topic label if present
        no_label = topic_label_re.sub("", summary.strip())
        safe = _clean_for_html(no_label)
        # Extract headline + bullet points from the cleaned text (already HTML-escaped)
        headline, points = _extract_headline_and_points(safe)
        # Fallback to original article title as headline if parsing failed or headline empty
        if not headline:
            headline = html_lib.escape(art_title or "Untitled")
        # Remove points that duplicate the headline
        def _norm(x: str) -> str:
            return re.sub(r"[\s\.;:\-]+$", "", x.strip().lower())
        norm_head = _norm(headline)
        seen_pts = set()
        deduped: List[str] = []
        for p in points:
            np = _norm(p)
            if not np or np == norm_head or np in seen_pts:
                continue
            seen_pts.add(np)
            deduped.append(p)
        points = deduped
        # Build paragraphs for points
        point_ps = "".join(f"<p>{p}</p>" for p in points if p)
        safe_url = None
        if it.get("url"):
            try:
                safe_url = html_lib.escape(str(it.get("url")), quote=True)
            except Exception:
                safe_url = None
        # Headings with optional links
        # Display title special-casing: always render "US" in all caps
        display_topic = "US" if key == "us" else html_lib.escape(topic_title)
        if safe_url:
            h2_html = f'<h2><a href="{safe_url}" target="_blank" rel="noopener noreferrer">{emoji} {display_topic}</a></h2>'
            h3_html = f'<h3 class="digest-headline"><a href="{safe_url}" target="_blank" rel="noopener noreferrer">{headline}</a></h3>'
        else:
            h2_html = f'<h2>{emoji} {display_topic}</h2>'
            h3_html = f'<h3 class="digest-headline">{headline}</h3>'
        block = (
            f'<section class="digest-topic">'
            f'{h2_html}'
            f'{h3_html}'
            f'<div class="digest-points">{point_ps}</div>'
            f'</section>'
        )
        html_blocks.append(block)
    return "\n".join(html_blocks)
# --- Local fallback output --------------------------------------------------

def save_local_fallback(compiled: str, items: List[Dict[str, Any]]) -> str:
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%d %B %Y")
    html_path = os.path.join(out_dir, f"digest_{date_str}.html")
    json_path = os.path.join(out_dir, f"digest_{date_str}.json")
    # Wrap the digest in a basic HTML template
    html_template = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Day News Digest - {date_str}</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #fafafa; color: #222; margin: 2em; }}
        .digest-topic {{ margin-bottom: 2em; padding: 1em; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px #eee; }}
        h2 {{ margin-top: 0; font-size: 1.3em; }}
        .digest-error {{ color: #b00; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>Day News Digest <span style=\"font-size:0.7em;color:#888\">{date_str}</span></h1>
    {compiled}
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return html_path


# --- Audio generation (Kokoro TTS) -----------------------------------------

def build_narration_text_from_compiled(
    compiled_html: str,
    intro: str = "This is Day2Day News.",
    outro: str = "That's all for today from Day2Day News.",
    empty_message: str = "No news items are available today.",
    debug_filename: str = "narration_debug.txt",
) -> str:
    """Create narration text that exactly mirrors today's displayed summary.

    Strategy: strip HTML tags from the compiled digest, preserve natural breaks
    after headings and paragraph tags, and unescape entities so the spoken
    text matches what users read on the page. Keep a short intro, no date.
    Remove emojis from topic headings.

    The intro/outro/empty_message/debug_filename parameters allow callers
    (e.g. the monthly summary generator) to reuse this exact pipeline with
    different narration bookends.
    """
    if not compiled_html:
        return intro + " " + empty_message
    t = compiled_html
    # Normalize tag closings to line breaks for readability
    t = re.sub(r"</(h1|h2|h3|p|section)>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.IGNORECASE)
    # Remove all remaining tags
    t = re.sub(r"<[^>]+>", "", t)
    # Unescape entities (compiled already escaped article text)
    t = html_lib.unescape(t)
    # Remove emojis (common Unicode ranges for emojis)
    # Match emoji pictographs and symbols
    t = re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF]+', '', t)
    # Collapse whitespace but preserve newlines
    t = re.sub(r"\r", "", t)
    # Collapse multiple blank lines
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    # Trim lines
    lines = [ln.strip() for ln in t.split("\n")]
    text_body = "\n".join([ln for ln in lines if ln])
    full_text = intro + "\n" + text_body + "\n" + outro
    # Save narration text for debugging
    try:
        debug_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", debug_filename)
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"[Audio] Narration text saved to: {debug_path}")
    except Exception:
        pass
    return full_text


def generate_audio_with_kokoro(text: str, voice: str = "am_michael") -> bytes:
    """Generate spoken audio with Kokoro.

    Priority order based on your working setup:
    1) kokoro.KPipeline (observed in your working test)
    2) kokoro_onnx.Kokoro

    Returns WAV bytes or empty bytes on failure.
    """
    # 1) Try the user's confirmed working API: kokoro.KPipeline
    try:
        print("[Audio] Attempting to initialize Kokoro KPipeline...")
        from kokoro import KPipeline  # type: ignore
        # Pass explicit repo_id to avoid defaulting warning from upstream
        pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M')
        print("[Audio] KPipeline initialized successfully")
        
        # KPipeline yields (ps, go, audio) for chunks; collect all audio to cover full narration
        sr = 24000  # your example saved with 24kHz
        all_samples: List[float] = []
        chunk_count = 0
        
        print(f"[Audio] Generating speech for {len(text)} characters...")
        for _ps, _go, audio in pipeline(text, voice=voice):
            if audio is None:
                continue
            try:
                # Extend with chunk samples
                chunk_len = len(audio) if hasattr(audio, '__len__') else 0
                all_samples.extend(float(x) for x in audio)
                chunk_count += 1
                if chunk_count % 10 == 0:
                    print(f"[Audio] Processed {chunk_count} chunks, {len(all_samples)} samples so far...")
            except Exception as e_chunk:
                print(f"[Audio] Warning: Failed to process audio chunk: {e_chunk}")
                continue
        
        print(f"[Audio] Collected {len(all_samples)} samples from {chunk_count} chunks")
        
        if all_samples:
            import wave, struct
            with BytesIO() as bio:
                with wave.open(bio, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sr)
                    def _clip_to_i16(x: float) -> int:
                        if x > 1.0:
                            x = 1.0
                        elif x < -1.0:
                            x = -1.0
                        return int(x * 32767.0)
                    # Write all frames sequentially
                    for x in all_samples:
                        try:
                            wf.writeframes(struct.pack('<h', _clip_to_i16(float(x))))
                        except Exception:
                            continue
                data = bio.getvalue()
            print(f"[Audio] Generated {len(data)} bytes of WAV audio (kokoro.KPipeline, concatenated)")
            return data
        else:
            print("[Audio] KPipeline yielded no audio frames")
    except Exception as e:
        print(f"[Audio] KPipeline failed: {type(e).__name__}: {e}")
        # Fall back to kokoro_onnx
        pass

    # 2) Try kokoro_onnx API
    try:
        import tempfile
        from kokoro_onnx import Kokoro  # type: ignore
        # Note: kokoro-onnx requires local model and voices paths. If not provided,
        # this will raise a TypeError; we'll catch and continue to the local OS TTS fallback.
        tts = Kokoro()  # type: ignore[call-arg]
        # Try common method names returning bytes/array
        for meth_name in ("generate", "tts", "synthesize", "create", "speak"):
            meth = getattr(tts, meth_name, None)
            if not callable(meth):
                continue
            try:
                try:
                    res = meth(text, voice=voice)
                except TypeError:
                    res = meth(text, voice)
                if res is None:
                    continue
                # If result is (samples, sr)
                if isinstance(res, tuple) and len(res) == 2:
                    samples, sr = res
                    import wave, struct
                    nch = 1
                    try:
                        first = samples[0]
                        if isinstance(first, (list, tuple)):
                            nch = max(1, len(first) or 1)
                    except Exception:
                        pass
                    with BytesIO() as bio:
                        with wave.open(bio, 'wb') as wf:
                            wf.setnchannels(nch)
                            wf.setsampwidth(2)
                            wf.setframerate(int(sr))
                            def _clip_to_i16(x: float) -> int:
                                if x > 1.0:
                                    x = 1.0
                                elif x < -1.0:
                                    x = -1.0
                                return int(x * 32767.0)
                            if nch == 1:
                                for x in samples:
                                    try:
                                        wf.writeframes(struct.pack('<h', _clip_to_i16(float(x))))
                                    except Exception:
                                        continue
                            else:
                                for frame in samples:
                                    try:
                                        for ch in frame:
                                            wf.writeframes(struct.pack('<h', _clip_to_i16(float(ch))))
                                    except Exception:
                                        continue
                        data = bio.getvalue()
                    if data:
                        print(f"[Audio] Generated {len(data)} bytes of WAV audio (kokoro_onnx tuple)")
                        return data
                # If object has bytes/attribute
                for attr in ("speech", "audio", "wav", "data"):
                    if hasattr(res, attr):
                        data = getattr(res, attr)
                        try:
                            data = bytes(data)
                        except Exception:
                            pass
                        if isinstance(data, (bytes, bytearray)) and data:
                            print(f"[Audio] Generated {len(data)} bytes of WAV audio (kokoro_onnx object)")
                            return bytes(data)
                if isinstance(res, (bytes, bytearray)) and res:
                    print(f"[Audio] Generated {len(res)} bytes of WAV audio (kokoro_onnx bytes)")
                    return bytes(res)
            except Exception:
                continue
        # Try save-to-file style APIs
        for save_name in ("save_wav", "save", "to_wav", "write_wav"):
            save = getattr(tts, save_name, None)
            if not callable(save):
                continue
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                    try:
                        save(text, voice=voice, to=tmp.name)
                    except TypeError:
                        try:
                            save(text, tmp.name, voice=voice)
                        except TypeError:
                            save(text, tmp.name)
                    tmp.seek(0)
                    data = tmp.read()
                    if data:
                        print(f"[Audio] Generated {len(data)} bytes of WAV audio (kokoro_onnx saved)")
                        return data
            except Exception:
                continue
    except Exception as e:
        # Either kokoro_onnx isn't available or models are not set up; fall through.
        print(f"[Audio] kokoro_onnx path skipped: {type(e).__name__}: {e}")

    # 3) Last-resort local fallback: use system TTS via pyttsx3 (Windows: SAPI5)
    #    This is fully offline and avoids heavyweight ML deps.
    try:
        import tempfile
        import pyttsx3  # type: ignore

        print("[Audio] Falling back to local OS TTS (pyttsx3)...")
        engine = pyttsx3.init()  # On Windows uses SAPI5
        
        # Voice selection: prefer male voices for consistency with am_michael
        # Look for "David", "Mark", or any voice with "male" in the name
        try:
            voices = engine.getProperty('voices')
            selected_voice = None
            
            # First priority: look for David (common Windows male voice)
            for v in voices:
                name = (getattr(v, 'name', '') or '').lower()
                if 'david' in name:
                    selected_voice = v.id
                    print(f"[Audio] Selected voice: {getattr(v, 'name', 'David')}")
                    break
            
            # Second priority: look for Mark or other common male names
            if not selected_voice:
                for v in voices:
                    name = (getattr(v, 'name', '') or '').lower()
                    if any(male_name in name for male_name in ['mark', 'james', 'george', 'male']):
                        selected_voice = v.id
                        print(f"[Audio] Selected voice: {getattr(v, 'name', 'Male voice')}")
                        break
            
            # Third priority: if voice parameter matches Kokoro style (am_*), pick first male-sounding voice
            if not selected_voice and voice and 'am_' in str(voice).lower():
                for v in voices:
                    name = (getattr(v, 'name', '') or '').lower()
                    # Avoid female names
                    if not any(fem in name for fem in ['zira', 'hazel', 'susan', 'female']):
                        selected_voice = v.id
                        print(f"[Audio] Selected voice (male preference): {getattr(v, 'name', 'Unknown')}")
                        break
            
            if selected_voice:
                engine.setProperty('voice', selected_voice)
            else:
                print("[Audio] Using default system voice")
        except Exception as e:
            print(f"[Audio] Voice selection failed, using default: {e}")

        # Moderate speech rate for clarity
        try:
            rate = int(engine.getProperty('rate') or 200)
            engine.setProperty('rate', max(140, min(rate, 220)))
        except Exception:
            pass

        # Save to temporary WAV then return bytes
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)  # Close handle so SAPI can write to it on Windows
        try:
            engine.save_to_file(text, tmp_path)
            engine.runAndWait()
            with open(tmp_path, "rb") as f:
                data = f.read()
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        if data:
            print(f"[Audio] Generated {len(data)} bytes of WAV audio (pyttsx3)")
            return data
    except Exception as e:
        print(f"[Audio] pyttsx3 fallback failed: {type(e).__name__}: {e}")

    print("[Audio] Kokoro TTS generation failed: No compatible API path succeeded")
    return b""


# --- Ollama bootstrap -------------------------------------------------------

def _ollama_http_ok() -> bool:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    try:
        r = requests.get(f"{host}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def ensure_ollama_running_and_model(model: str, wait_seconds: int = 60, pull_timeout: int = 600) -> None:
    """Check if Ollama HTTP API is accessible and warn if not.
    
    In Docker with network_mode: host, we rely on the host's Ollama service.
    We don't try to start Ollama or pull models - just verify connectivity.
    """
    import urllib.request
    
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    print(f"[Ollama] Checking if Ollama API is accessible at {host}...")

    try:
        urllib.request.urlopen(f"{host}/api/tags", timeout=5)
        print(f"[Ollama] ✓ API is accessible. Model '{model}' should be available.")
    except Exception as e:
        print(f"[Ollama] ✗ Could not reach Ollama API: {repr(e)}")
        print(f"[Ollama] Make sure Ollama is running on the host with: ollama serve")
        print(f"[Ollama] And that model '{model}' is pulled with: ollama pull {model}")
        print(f"[Ollama] Continuing anyway - summaries will fail if Ollama is not available.")


# --- Timeout watchdog and alert --------------------------------------------

def send_timeout_email(cfg: Dict[str, Any], elapsed_seconds: float) -> None:
    subject = "Day News Digest: Script Timeout"
    ts = datetime.now(timezone.utc).isoformat()
    mins = int(elapsed_seconds // 60)
    secs = int(elapsed_seconds % 60)
    body = (
        "The daily digest script exceeded the maximum runtime and was terminated.\n\n"
        f"Timestamp (UTC): {ts}\n"
        f"Elapsed: {mins} minutes {secs} seconds\n"
        "Max allowed: 20 minutes\n\n"
        "This alert was sent automatically."
    )

    smtp_host = cfg.get("SMTP_HOST")
    smtp_port = int(cfg.get("SMTP_PORT", "465") or "465")
    smtp_user = cfg.get("SMTP_USER")
    smtp_pass = cfg.get("SMTP_PASS")
    sender = cfg.get("SMTP_SENDER")
    # Use configured recipient if present; otherwise, default to the provided address
    recipient = cfg.get("SMTP_TO") or "justwebsites.contact@gmail.com"

    if not all([smtp_host, smtp_user, smtp_pass, sender, recipient]):
        print("Timeout email skipped: SMTP credentials are not fully configured.")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = formataddr(("Day News", str(sender)))
    msg["To"] = str(recipient)

    try:
        smtp = smtplib.SMTP_SSL(str(smtp_host), smtp_port)
        smtp.login(str(smtp_user), str(smtp_pass))
        smtp.sendmail(str(sender), [str(recipient)], msg.as_string())
        smtp.quit()
        print(f"Timeout notification sent to {recipient}")
    except Exception as e:
        print(f"Failed to send timeout email: {e}")


def start_timeout_watchdog(seconds: int, cfg: Dict[str, Any]):
    """Start a background timer that will email and terminate if runtime exceeds 'seconds'."""
    def _trigger():
        elapsed = time.time() - start
        try:
            send_timeout_email(cfg, elapsed)
        except Exception as e:
            print(f"[Timeout] Failed to send notification: {e}")
        print(f"[Timeout] Exceeded {seconds} seconds; exiting.")
        os._exit(2)

    t = threading.Timer(seconds, _trigger)
    t.daemon = True
    t.start()
    return t


# --- Ollama Initialization --------------------------------------------------

def ensure_ollama_ready(model: str, max_retries: int = 30, timeout_secs: int = 3) -> bool:
    """
    Ensure Ollama is running and reachable. If not, try to start it. Exit if not available.
    """
    import time
    import urllib.request
    import subprocess
    import sys
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    print(f"[Ollama] Checking if Ollama API is accessible at {host}...")

    def http_ok():
        try:
            urllib.request.urlopen(f"{host}/api/tags", timeout=5)
            return True
        except Exception:
            return False

    # Try to connect first
    if http_ok():
        print(f"[Ollama] API is accessible. Model '{model}' should be available.")
        return True

    # Try to start Ollama if not running
    print("[Ollama] Ollama not running. Attempting to start ollama serve...")
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except Exception as e:
        print(f"[Ollama] Failed to start Ollama: {e}")
        sys.exit(1)

    # Wait for Ollama to become available
    for attempt in range(1, max_retries + 1):
        if http_ok():
            print(f"[Ollama] API is accessible (after starting) (attempt {attempt}). Model '{model}' should be available.")
            return True
        if attempt == 1 or attempt % 10 == 0:
            print(f"[Ollama] Waiting for Ollama to start (attempt {attempt})...")
        time.sleep(timeout_secs)

    print(f"[Ollama] ERROR: Could not reach Ollama API after {max_retries} attempts. Exiting.")
    sys.exit(1)


# --- Main -------------------------------------------------------------------

def main() -> int:
    cfg = load_config()
    
    # Ensure Ollama is ready before starting the digest
    ollama_model = cfg.get("OLLAMA_MODEL") or "gemma3:4b"
    ensure_ollama_ready(ollama_model, max_retries=30, timeout_secs=2)
    
    # Start a 20-minute watchdog to abort and email if the script overruns.
    watchdog = start_timeout_watchdog(20 * 60, cfg)
    missing = [k for k in ("NEWS_API_KEY",) if not cfg.get(k)]
    if missing:
        print(f"Missing config values: {', '.join(missing)}. Check ven.env.")

    topics = get_topics()

    fetched: List[Dict[str, Any]] = []
    failed_categories: List[str] = []
    last_quota_seen: Optional[str] = None
    # Track global duplicates across sections (by URL or title)
    global_seen: set = set()
    for t in topics:
        cat = t.get("category") or "general"
        article = fetch_news_article_with_retries(cfg, cat, max_attempts=5, global_exclude=global_seen)
        if not article:
            failed_categories.append(cat)
            article = {
                "title": f"No article found for category {cat}",
                "description": "",
                "url": None,
                "published_at": None,
                "content": "",
            }
        else:
            if article.get("quota_left") is not None:
                last_quota_seen = str(article["quota_left"])
            # Record globally seen key for cross-section dedupe
            url = (article.get("url") or "").strip().lower()
            title_key = (article.get("title") or "").strip().lower()
            key = url or title_key
            if key:
                global_seen.add(key)
        fetched.append({
            "topic": cat,
            **article,
        })
        time.sleep(1)  # Add a 1-second delay between requests

    # Email notification if any failures
    if failed_categories:
        send_failure_email(cfg, failed_categories)

    # Ensure Ollama server and model are ready before summarization
    try:
        ensure_ollama_running_and_model(ollama_model)
    except Exception as e:
        print(f"[Ollama] Bootstrap error (non-fatal): {e}")

    # Summarize each
    digest_items: List[Dict[str, Any]] = []
    for item in fetched:
        # Normalize topic display: keep everything Title Case except ensure "US" stays uppercase
        raw_topic = item["topic"]
        topic_title = raw_topic.replace("-", "/").title()
        if raw_topic.lower() == "us":
            topic_title = "US"
        summary = summarize_with_ollama(
            ollama_model,
            topic_title,
            item.get("title", "Untitled"),
            item.get("content", ""),
            item.get("url"),
        )
        # Only include successful summaries in persisted items
        if "[ERROR:" not in summary:
            digest_items.append({
                "topic": topic_title,
                "title": item.get("title"),
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "summary": summary,
            })

    compiled = compile_digest(digest_items)

    # Write the day's static JSON (failed summaries are already excluded from items/compiled).
    # Skip if nothing succeeded so a bad re-run never overwrites a good day.
    date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if digest_items:
        print(f"Wrote digest: {site_io.write_daily_json(date_iso, compiled, digest_items)}")
    else:
        print("No successful summaries; not writing a daily JSON file.")

    # Generate audio summary (only the latest day's file is kept)
    try:
        narration = build_narration_text_from_compiled(compiled)
        audio_bytes = generate_audio_with_kokoro(narration, voice="am_michael")
        if audio_bytes:
            # Convert WAV to MP3 for smaller file size
            try:
                print(f"[Audio] Converting WAV ({len(audio_bytes)} bytes) to MP3...")
                wav_io = io.BytesIO(audio_bytes)
                audio_segment = AudioSegment.from_wav(wav_io)
                mp3_io = io.BytesIO()
                audio_segment.export(mp3_io, format="mp3", bitrate="128k")
                audio_bytes = mp3_io.getvalue()
                file_ext = "mp3"
                print(f"[Audio] Converted to MP3 ({len(audio_bytes)} bytes, ~{len(audio_bytes)/(1024*1024):.1f}MB)")
            except Exception as conv_err:
                print(f"[Audio] MP3 conversion failed ({conv_err}), using WAV fallback")
                file_ext = "wav"
            
            if digest_items:
                print(f"[Audio] Wrote {site_io.write_audio(f'{date_iso}.{file_ext}', audio_bytes)}")
        else:
            print("[Audio] Skipping audio because generation failed or returned empty data")
    except Exception as e:
        print(f"[Audio] Unexpected error during audio pipeline: {e}")

    print(f"Updated index: {site_io.update_index()}")

    # Always save local fallback
    out_path = save_local_fallback(compiled, digest_items)
    print(f"Saved local digest to: {out_path}")

    # Show remaining daily quota if observed
    if last_quota_seen is not None:
        print(f"[API] X-RateLimit-Remaining today: {last_quota_seen}")

    print(f"Total runtime: {time.time() - start:.2f} seconds")
    # Cancel watchdog on successful completion
    try:
        watchdog.cancel()
    except Exception:
        pass
    return 0

def send_failure_email(cfg: Dict[str, Any], failed_categories: List[str]) -> None:
    subject = "Day News Digest: API Failure Notification"
    body = (
        "The following categories failed to fetch news after 3 attempts:\n\n" + ", ".join(failed_categories)
    )

    smtp_host = cfg.get("SMTP_HOST")
    smtp_port = int(cfg.get("SMTP_PORT", "465") or "465")
    smtp_user = cfg.get("SMTP_USER")
    smtp_pass = cfg.get("SMTP_PASS")
    sender = cfg.get("SMTP_SENDER")
    recipient = cfg.get("SMTP_TO")

    if not all([smtp_host, smtp_user, smtp_pass, sender, recipient]):
        print("Email notification skipped: SMTP credentials are not configured.")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = formataddr(("Day News", str(sender)))
    msg["To"] = str(recipient)

    try:
        smtp = smtplib.SMTP_SSL(str(smtp_host), smtp_port)
        smtp.login(str(smtp_user), str(smtp_pass))
        smtp.sendmail(str(sender), [str(recipient)], msg.as_string())
        smtp.quit()
        print(f"Failure notification sent to {recipient}")
    except Exception as e:
        print(f"Failed to send email notification: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
