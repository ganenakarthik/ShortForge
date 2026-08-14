"""Fresh tech news fetch for daily production.
Keyless: Hacker News Algolia API + Google News RSS. Items tagged by category
(ai / hardware / software / space / business / misc) so the producer can pick
a matching playbook. NOTE: limiters below keep titles safely under ~50 chars."""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.request import Request, urlopen

# No text query: Algolia's OR-syntax query reliably returns 0 hits here.
# Fetch all recent stories and tag them client-side with CATEGORY_RX.
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=60&numericFilters=created_at_i>{ts}"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q=technology+when:3d&hl=en-US&gl=US&ceid=US:en"

UA = {"User-Agent": "Mozilla/5.0 (daily-shorts-producer)"}

CATEGORY_RX = [
    ("ai", r"\b(ai|llm|gpt|openai|anthropic|gemini|artificial intelligence|deep learning|neural|chatbot|model)\b", 3),
    ("hardware", r"\b(chip|gpu|nvidia|amd|intel|tsmc|semiconductor|processor|core|quantum|samsung|circuit)\b", 2),
    ("space", r"\b(space|nasa|spacex|rocket|satellite|orbit|telescope|lunar|mars|starship)\b", 2),
    ("software", r"\b(software|security|bug|vulnerability|cve|open source|open-source|android|ios|linux|windows|cloud|api|developer)\b", 2),
    ("business", r"\b($|billion|million|acquir|merge|stock|market|revenue|launch|ipo|google|microsoft|apple|meta|amazon|tesla)\b", 1),
]
MISC = "misc"

MAX_TITLE_LEN = 48


def _tags(title: str) -> str:
    low = title.lower()
    best, best_score = MISC, 0
    for cat, rx, weight in CATEGORY_RX:
        m = re.findall(rx, low)
        if m:
            score = len(m) * weight
            if score > best_score:
                best, best_score = cat, score
    return best


def _clean_gn_title(title: str) -> str:
    t = title.strip()
    t = re.sub(r"\s+-\s*\S+\s*$", "", t)          # trailing "- Publisher"
    t = re.sub(r"\s*\([^)(]{0,20}\)\s*$", "", t)   # trailing (MU) / (TipRanks) style
    t = re.sub(r"\s*\([A-Z0-9.\-]{1,6}\)\s*", " ", t)  # mid-title tickers like (MU)
    t = re.sub(r"\b(USA|NASDAQ|NYSE|TSX|LSE)\b", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def _shorten(title: str) -> str:
    t = title.strip().strip(":\u2014-")
    if len(t) <= MAX_TITLE_LEN:
        return t
    cut = t[:MAX_TITLE_LEN]
    cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip(":,\u2014-") + "\u2026"


def _fetch(url: str, timeout: int = 25) -> bytes:
    req = Request(url, headers=UA)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_hn(age_hours: int = 48) -> list[dict]:
    ts = int(time.time()) - age_hours * 3600
    try:
        raw = _fetch(HN_SEARCH.format(ts=ts))
        data = json.loads(raw)
    except Exception as exc:
        print(f"[news] HN fetch failed: {exc}")
        return []
    items = []
    for h in data.get("hits", []):
        if not h.get("title") or h.get("url") and "ycombinator.com" in h["url"]:
            continue
        title = (h.get("title") or "").strip()
        items.append({
            "source": "hackernews",
            "title": _shorten(title),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "score": h.get("points") or 0,
            "age_hours": round((time.time() - (h.get("created_at_i") or time.time())) / 3600, 1),
            "category": _tags(title),
        })
    return items


def fetch_google_news() -> list[dict]:
    try:
        raw = _fetch(GOOGLE_NEWS_RSS)
    except Exception as exc:
        print(f"[news] Google News fetch failed: {exc}")
        return []
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"[news] RSS parse failed: {exc}")
        return []
    for item in root.iter("item"):
        title = strip_html(item.findtext("title", "")) or ""
        if title.lower().startswith(("  ", "\n")):
            title = re.sub(r"^\s*-\s*", "", title)
        title = _clean_gn_title(title)
        link = item.findtext("link", "")
        source = "google-news"
        m = re.search(r"https?://[^/]+", link or "")
        if m:
            source = m.group(0).replace("https://", "").replace("http://", "")
        pub = item.findtext("pubDate", "")
        age_hours = None
        try:
            dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            age_hours = round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
        except Exception:
            pass
        items.append({"source": source, "title": _shorten(title), "url": link,
                      "score": 0, "age_hours": age_hours, "category": _tags(title)})
    return items


def pick_topics(count: int = 2, min_score: int = 20, category: str | None = None) -> list[dict]:
    hn = fetch_hn()
    gn = fetch_google_news()
    merged = hn + gn
    if category:
        merged = [i for i in merged if i["category"] == category]
    ranked = sorted(
        merged,
        key=lambda x: -(
            x["score"] if x["score"] else (100 if x["age_hours"] is not None and x["age_hours"] < 48 else 0)
        ),
    )
    picked, seen = [], set()
    for item in ranked:
        key = item["title"].lower()
        if len(key) < 12 or key in seen:
            continue
        seen.add(key)
        picked.append(item)
        if len(picked) >= count:
            break
    return picked