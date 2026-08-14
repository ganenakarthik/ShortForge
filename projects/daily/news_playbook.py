"""Fresh news -> sourced playbook.

Fetches fresh tech news (news.py), builds a playbook per item with claims
taken from the article text itself (webfetched). Hard rules:
- NEVER fabricate: every claim is a sentence from the article or the headline;
  the source URL is recorded in facts[] (tier 2: reputable news publication).
- If the article cannot be fetched, the playbook carries only the headline
  claim (still sourced to the URL) — never invented detail.
- Titles are shortened, numbers kept, claims capped at 3 per playbook.

Playbooks are saved as playbooks/news-<date>-<n>.json and consumed by
director.direct() like any other playbook.
"""

import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import news  # noqa: E402

PLAYBOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playbooks")


def _clean_claim(sentence: str) -> str:
    s = re.sub(r"\s+", " ", sentence).strip()
    s = s.strip("[]\"'")
    if not s or len(s) < 20:
        return ""
    if len(s) > 140:
        cut = s[:140].rsplit(" ", 1)[0]
        s = cut.rstrip(":,\u2014-") + "\u2026"
    return s


def _extract_claims(title: str, text: str, max_claims: int = 3) -> list[str]:
    """Sentences (with numbers or strong verbs) from the article body.
    Rejects script/JSON junk (interstitial pages, paywall embeds)."""
    claims = []
    for m in re.finditer(r"[^.!?\n]+[.!?]", text):
        s = _clean_claim(m.group(0))
        if not s:
            continue
        if any(x in s for x in ("{", "}", "://", "WIZ_global_data", "window.",
                                "var ", '"', ".php", ".html", ".com/", "headline",
                                "articleSection", "\\u", "rawImage")):
            continue
        if s.count(" ") < 3:
            continue  # URL fragments / captions are not sentences
        if re.search(r"\d", s) or re.search(r"\b(could|will|is|are|has|shows|found|claims|reaches|beats|suing|trains)\b", s.lower()):
            if s not in claims:
                claims.append(s)
        if len(claims) >= max_claims:
            break
    return claims


STOPWORDS = {"a", "an", "the", "is", "are", "was", "were", "its", "own", "over",
             "for", "on", "in", "of", "and", "to", "from", "with", "at", "by",
             "about", "into", "after", "before", "as", "it", "not"}


def _video_query(title: str) -> str:
    """Short Commons-friendly video search query from the headline:
    capitalized words (proper nouns) + numbers, max 3, lowercased."""
    words = re.findall(r"\b[A-Z][A-Za-z0-9]+|\\b\d+", title)
    words = [w.lower() for w in words if w.lower() not in STOPWORDS and len(w) > 2]
    return " ".join(words[:3]) or title.split()[0].lower()


def build_playbook(item: dict, article_text: str = "", slot: int = 1) -> dict:
    title = news._shorten(item["title"])
    source = item.get("url") or item.get("link", "")
    source_name = item.get("source", "news")
    claims = _extract_claims(title, article_text)
    if not claims:
        claims = [title]

    pid = f"news-{date.today().isoformat()}-{slot}"
    return {
        "id": pid,
        "name": title,
        "target_seconds": 30,
        "hook_variants": [
            {"format": "news", "template": title, "news_slot": False},
        ],
        "body_variants": [
            {
                "name": "news-body",
                "sections": [
                    {"visual": {"type": "video", "query": _video_query(item["title"])},
                     "text": claims[0]},
                    *[
                        {"visual": "text_card", "text": c}
                        for c in claims[1:]
                    ],
                    {"visual": "CTA", "text": "Follow for daily tech you didn't know."},
                ],
            }
        ],
        "facts": [
            {"claim": c, "source_url": source, "source_name": source_name,
             "tier": 2}
            for c in claims
        ],
        "titles": [title],
        "hashtags": ["#tech", "#news", "#shorts", "#techshorts"],
        "news_source_url": source,
    }


def fetch_article(url: str, timeout: int = 20) -> str:
    """Best-effort article text; returns '' when the site blocks us or the
    URL is a redirect wrapper (Google News interstitial) with no article."""
    try:
        from urllib.request import Request, urlopen
        req = Request(url, headers={"User-Agent": news.UA["User-Agent"]})
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
        text = news.strip_html(text)
        text = re.sub(r"\s{2,}", " ", text)
        if "WIZ_global_data" in text or "news.google.com/rss/articles" in url:
            return ""
        return text[:40000]
    except Exception:
        return ""


# News categories we prefer for shorts (tech-forward, visual, shareable).
# Business/misc recalls and market chatter rank last.
PREFERRED_CATEGORIES = ("ai", "hardware", "space", "software")


def produce(count: int = 2) -> list[dict]:
    """Pick fresh news topics, fetch articles, write playbooks, return paths."""
    os.makedirs(PLAYBOOKS, exist_ok=True)
    # Fetch both feeds directly: pick_topics ranks Google News by age above
    # every HN score, which hides real article links. Sort here instead.
    items = news.fetch_hn() + news.fetch_google_news()
    items.sort(key=lambda it: (
        it.get("category") not in PREFERRED_CATEGORIES,
        it.get("source") == "google-news",
        -(it.get("score") or 0),
        it.get("age_hours") is None or it.get("age_hours", 999) >= 48,
    ))
    picked, seen = [], set()
    for it in items:
        key = it["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        picked.append(it)
        if len(picked) >= count:
            break
    if not picked:
        print("[news-playbook] no fresh news items available")
        return []

    paths = []
    for slot, it in enumerate(picked, start=1):
        text = fetch_article(it["url"])
        if text:
            print(f"[news-playbook] fetched article ({len(text)} chars) for: {it['title']}")
        else:
            print(f"[news-playbook] no article body (blocked); headline-only playbook: {it['title']}")
        pb = build_playbook(it, text, slot)
        path = os.path.join(PLAYBOOKS, f"{pb['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pb, f, indent=2)
        paths.append(path)
        print(f"[news-playbook] wrote {path}")
    return paths


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    for p in produce(n):
        print(p)
