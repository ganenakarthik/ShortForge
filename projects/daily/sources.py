"""Topic-relevant image/video sourcing from Wikimedia Commons (no API key).

Search is keyword-based on the beat's topic (e.g. "spine anatomy"),
license-filtered (PD / CC0 / CC BY / CC BY-SA only — no NC/ND), size-filtered
for vertical shorts, downloaded with retry/backoff, and cached per query so
re-runs are deterministic and idempotent.
"""

import hashlib
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "tmp", "assets")

ALLOWED_LICENSES = ("Public domain", "No restrictions", "CC0", "CC BY", "CC BY-SA")
REJECT_IF_CONTAINS = ("NC", "ND")
MIN_WIDTH = 1000
MIN_HEIGHT = 700
# Real-footage intent: skip obvious non-photo titles when kind == "image"
REJECT_TITLE_IF_CONTAINS = ("toy", "plush", "stuffed", "cartoon", "mascot", "logo",
                            "banner", "poster", "cover art", "icon", "illustration of",
                            "painting of", "drawing of", "model of", "replica",
                            "screenshot", "flag of")
UA = {"User-Agent": "OpenMontage-daily/0.1 (local Shorts pipeline)"}


def _get(url: str, retries: int = 3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def _license_ok(license_short: str) -> bool:
    if not license_short:
        return False
    if any(x in license_short for x in REJECT_IF_CONTAINS):
        return False
    return any(a in license_short for a in ALLOWED_LICENSES)


def search(query: str, kind: str = "image", n: int = 10) -> list[dict]:
    """Commons search -> candidates [{url,title,license,width,height,mime}],
    ranked by relevance (titles containing the query tokens come first)."""
    filetype = "bitmap" if kind == "image" else "video"
    params = {
        "action": "query", "generator": "search",
        "gsrsearch": f"filetype:{filetype} {query}",
        "gsrnamespace": 6, "gsrlimit": 30, "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime", "format": "json",    }
    data = _get("https://commons.wikimedia.org/w/api.php?"
                + urllib.parse.urlencode(params))
    tokens = {t for t in query.lower().split() if len(t) > 2}
    out = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (page.get("imageinfo") or [{}])[0]
        lic = ((ii.get("extmetadata", {}).get("LicenseShortName") or {}).get("value") or "").strip()
        if not _license_ok(lic):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            continue
        mime = ii.get("mime", "")
        if kind == "image" and not mime.startswith("image/"):
            continue
        if kind == "video" and not mime.startswith("video/"):
            continue
        title = (page.get("title") or "").lower()
        if kind == "image" and any(t in title for t in REJECT_TITLE_IF_CONTAINS):
            continue
        hits = sum(1 for t in tokens if t in title)
        out.append({"url": ii.get("url"), "title": page.get("title"),
                    "license": lic, "width": w, "height": h, "mime": mime,
                    "size": ii.get("size", 0), "relevance": hits})
    # Videos: prefer relevant clips and smaller files (short footage, fast
    # transcode) over long films. Images: relevant + biggest first.
    if kind == "video":
        out.sort(key=lambda c: (-c["relevance"], c["size"] or 1 << 40))
    else:
        out.sort(key=lambda c: (-c["relevance"], -c["width"] * c["height"]))
    return out


def _download(url: str, dest: str) -> None:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                f.write(r.read())
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def resolve(query: str, kind: str = "image") -> tuple[str, dict]:
    """Deterministic per query: first acceptable candidate, cached.

    Returns (local_path, meta). Videos are transcoded to h264 mp4 so Remotion
    can play them.
    """
    os.makedirs(ASSETS, exist_ok=True)
    key = hashlib.sha1(f"{kind}:{query}".encode()).hexdigest()[:12]
    ext = ".jpg" if kind == "image" else ".mp4"
    dest = os.path.join(ASSETS, f"src_{key}{ext}")
    meta_path = dest + ".json"
    if os.path.exists(dest) and os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            return dest, json.load(f)

    cands = search(query, kind)
    if not cands:
        raise LookupError(f"no acceptable Commons asset for query: {query!r}")

    raw = os.path.join(ASSETS, f"src_{key}_raw")
    c = cands[0]
    _download(c["url"], raw)

    # Video sources: keep only the first ~45s and re-encode h264 1080p-capped.
    # Shorts use a few seconds of footage; a long/4K webm would otherwise
    # stall the whole daily run (a 110MB webm once took ~24 min).
    if kind == "video":
        ff = subprocess.run(
            ["ffmpeg", "-y", "-t", "45", "-i", raw,
             "-vf", "scale='min(1920,iw)':-2",
             "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", "-an", dest],
            capture_output=True, text=True, timeout=900)
        if ff.returncode != 0:
            raise RuntimeError(f"video transcode failed: {ff.stderr[-200:]}")
        os.remove(raw)
    else:
        os.replace(raw, dest)

    meta = {k: c[k] for k in ("url", "title", "license", "width", "height", "mime")}
    meta["query"] = query
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return dest, meta