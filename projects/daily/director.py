"""Director: storyboard-first production engine.

Turns a playbook (facts + beats + visual material) into a v2 job whose heart
is a shot list with PURPOSE. Every shot answers: what does the viewer see,
when, why (show / contrast / reveal / signal / punctuate), with what motion
and transition, and what audio moment (sfx) supports it.

Editing philosophy (priority #1):
- The story comes first: hook -> beats -> reveals -> payoff.
- A sentence can contain multiple shots (mid_narration anchors).
- A shot can span multiple sentences (spanning anchors).
- No filler: every shot has a purpose; shots without one are dropped.
- Shot density 3-6 meaningful visual changes per 10s where the story calls
  for it (montage-y sections), slower for hold shots.
- Narration is written for spoken delivery and the visuals are timed to the
  storyboard, not the other way around.

All decisions are deterministic per (seed, index) so re-runs are stable.
"""

import copy
import json
import os
import re

import v21

ROOT = os.path.dirname(os.path.abspath(__file__))
PLAYBOOKS = os.path.join(ROOT, "playbooks")

THEMES = ["flat-motion-graphics", "clean-professional", "minimalist-diagram"]

PURPOSES = ["hook", "setup", "show", "contrast", "reveal", "signal", "punctuate"]

# Scenes that animate internally (bars draw, milestones pop), so a 'static'
# wrapper motion still yields a moving frame.
SELF_ANIMATED_TYPES = {"timeline", "bar_chart", "line_chart", "pie_chart", "kpi_grid",
                       "progress_bar", "terminal_scene"}

MOTIONS = {
    "hook": ["punch_in", "zoom_in", "slide_right"],
    "setup": ["zoom_in", "pan_up", "static"],
    "show": ["zoom_in", "pan_up", "pan_down", "static"],
    "contrast": ["slide_left", "slide_right", "punch_in"],
    "reveal": ["punch_in", "zoom_in", "pop_up"],
    "signal": ["pan_down", "zoom_out", "static"],
    "punctuate": ["zoom_out", "static"],
}

# Per-visual-type motion bias: text pops, footage glides. Applied on top of
# the purpose pool so text cards punch instead of sitting still.
TEXT_MOTION_POOL = ["punch_in", "pop_up", "zoom_in", "punch_in"]
FOOTAGE_MOTION_POOL = ["zoom_in", "pan_up", "punch_in", "pan_down"]

TRANSITIONS = {
    "hook": ["punch", "cut"],
    "setup": ["fade", "cut", "punch"],
    "show": ["cut", "punch", "fade"],
    "contrast": ["slide_left", "slide_right", "cut"],
    "reveal": ["punch", "cut"],
    "signal": ["fade", "slide_right"],
    "punctuate": ["fade", "cut"],
}

SFX_BY_PURPOSE = {
    "hook": ["whoosh"],
    "reveal": ["impact", "pop"],
    "contrast": ["whoosh", "ding"],
    "signal": ["rise", "ding"],
    "punctuate": ["rise", "impact"],
}

DEFAULT_STYLE = {
    "music": "upbeat_pulse",
    "energy": 0.5,
    "theme": "flat-motion-graphics",
}


def load_playbook(playbook_id: str) -> dict:
    path = os.path.join(PLAYBOOKS, f"{playbook_id}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Hook selection (priority #4): score angles, pick strongest
# ---------------------------------------------------------------------------

def _score_hook(variant: dict) -> float:
    t = variant.get("template", "")
    score = 10.0
    score -= min(24.0, len(t) * 1.1)          # short = strong
    if re.search(r"\d", t):
        score += 4.0                          # numbers spark curiosity
    if any(w in t.lower() for w in ["lie", "myth", "wrong", "actually", "never", "no way", "but"]):
        score += 3.0                          # contradiction words
    if re.search(r"[?.]$", t):
        score -= 1.5                          # questions are weaker hooks here
    if variant.get("news_slot"):
        score -= 100
    return score


def pick_hook(playbook: dict, seed: int) -> dict:
    variants = playbook["hook_variants"]
    scored = sorted(enumerate(variants), key=lambda iv: _score_hook(iv[1]), reverse=True)
    top = scored[: min(3, len(scored))]
    pick = top[seed % len(top)]
    return {
        "variant": pick[1],
        "reason": ("shortest + numeric + contradiction" if pick[0] == 0
                   else f"angle {pick[0] + 1} chosen by seed {seed}"),
        "text": pick[1]["template"],
    }


# ---------------------------------------------------------------------------
# Beat -> narration segmentation (spoken delivery)
# ---------------------------------------------------------------------------

MAX_BEAT_WORDS = 22


def _split_beat_text(text: str) -> list[str]:
    """Split long spoken text into <=MAX_BEAT_WORDS chunks at sentence ends."""
    words = text.split()
    if len(words) <= MAX_BEAT_WORDS:
        return [text]
    parts, cur, cur_len = [], [], 0
    for w in words:
        if cur_len >= MAX_BEAT_WORDS:
            parts.append(" ".join(cur)); cur, cur_len = [], 0
        cur.append(w); cur_len += 1
    if cur:
        parts.append(" ".join(cur))
    return parts


def _beat_purpose(beat_index: int, total: int, visual_type: str) -> str:
    """Map beat position + visual type to a story purpose."""
    if beat_index == 0:
        return "hook"
    if beat_index == total - 1:
        return "punctuate"
    if visual_type in ("stat_card", "stat_reveal", "kpi_grid"):
        return "reveal"
    if visual_type in ("comparison", "timeline"):
        return "contrast" if visual_type == "comparison" else "show"
    if visual_type in ("callout", "progress_bar"):
        return "signal"
    if visual_type == "bar_chart":
        return "reveal"
    return "show"


# ---------------------------------------------------------------------------
# Shot plan: turns a beat into 1..n shots with anchors
# ---------------------------------------------------------------------------

def _shot_anchors_for_beat(beat, seed: int, n_shots: int, shot_index: int, beat_index: int,
                           narration_segs: list[dict]) -> dict:
    """Anchors are relative markers resolved against the narration timeline.

    'start' -> at beat start; 'mid' -> midpoint of the beat's narration;
    'end' -> at beat end (i.e. where the next beat starts). Mid shots split a
    sentence in half, which is the core "cut inside the sentence" move.
    """
    sid = narration_segs[beat_index]["id"]
    if n_shots == 1:
        return {"at": "start", "narration": sid}
    if shot_index == 0:
        return {"at": "start", "narration": sid}
    # V2.2: every split lands MID-sentence (the viral cut move). Two-shot
    # beats cut at 45% of the narration; three-shot at 33/66%. Never "end" —
    # an end-anchor delays the cut to the full sentence length.
    if n_shots == 2:
        # hook beat cuts at 30% (first cut must land before 1.1s);
        # body beats at 45%
        return {"at": "fraction", "narration": sid,
                "fraction": 0.30 if beat_index == 0 else 0.45}
    if shot_index == n_shots - 1:
        return {"at": "fraction", "narration": sid, "fraction": 0.66}
    # interior cut points split the sentence
    frac = shot_index / n_shots
    return {"at": "fraction", "narration": sid, "fraction": frac}


def _build_shots(beats: list[dict], seed: int, topic: str) -> list[dict]:
    shots = []
    total = len(beats)
    for bi, beat in enumerate(beats):
        vtype = beat["visual"]["type"]
        text_len = len(beat["narration"].split())
        purpose = _beat_purpose(bi, total, vtype)

        # how many shots does this beat deserve? (editing density, not filler)
        # V2.2 pacing (winning-format spec): start TIGHT (1.4-1.8s shots),
        # ease out to 2.6-3.2s. Early beats get more splits; later beats less.
        n_shots = 1
        if bi == 0:
            n_shots = 2                                   # hook: promise + proof cut
        elif vtype == "comparison":
            n_shots = 2                                   # left vs right reveal
        elif vtype in ("stat_card", "kpi_grid", "bar_chart"):
            n_shots = 2 if text_len > 8 else 1            # setup + number reveal
        elif purpose == "reveal":
            n_shots = 2
        elif vtype == "timeline":
            n_shots = 1                                   # internal animation
        elif vtype == "hero_title":
            n_shots = 2 if text_len > 9 else 1            # long hook = double hit
        # duration-aware, ANY purpose: speech runs ~0.35-0.5s/word, so long
        # segments MUST split or the 3.5s shot ceiling leaves dead gaps
        elif text_len > 16:
            n_shots = 3                                   # montage rhythm
        elif text_len > 8:
            n_shots = 2                                   # mid-sentence cut
        elif bi == total - 1:
            n_shots = 1

        narration = beat["narration"]
        for si in range(n_shots):
            anchor = _shot_anchors_for_beat(beat, seed, n_shots, si, bi,
                                            [{"id": f"n{bi + 1}"}] * total)
            shot_id = f"sh{len(shots) + 1}"
            is_last_of_beat = si == n_shots - 1
            is_first_of_beat = si == 0

            motion_pool = MOTIONS.get(purpose, ["zoom_in", "static"])
            # vary motion deterministically, avoid repeats
            prev_motion = shots[-1]["motion"] if shots else None
            pool = [m for m in motion_pool if m != prev_motion] or motion_pool
            motion = pool[(seed + len(shots)) % len(pool)]
            # visual-type bias: text pops, footage glides — then still force a
            # living frame (a held text card with no motion is a dead frame)
            if vtype in ("image", "video"):
                fpool = [m for m in FOOTAGE_MOTION_POOL if m != prev_motion] or FOOTAGE_MOTION_POOL
                motion = fpool[(seed + len(shots)) % len(fpool)]
            elif vtype in ("text_card", "hero_title", "callout", "comparison", "stat_card"):
                tpool = [m for m in TEXT_MOTION_POOL if m != prev_motion] or TEXT_MOTION_POOL
                motion = tpool[(seed + len(shots)) % len(tpool)]
            elif motion == "static" and vtype not in SELF_ANIMATED_TYPES:
                alive = [m for m in pool if m != "static"] or ["zoom_in"]
                motion = alive[(seed + len(shots)) % len(alive)]

            trans_pool = TRANSITIONS.get(purpose, ["cut", "fade"])
            if is_first_of_beat and shots:
                transition = trans_pool[(seed + len(shots)) % len(trans_pool)]
            elif is_last_of_beat and shots and shots[-1].get("beat_break", False):
                transition = "cut"
            else:
                transition = "cut"

            sfx = []
            if is_first_of_beat and bi == 0:
                sfx.append({"type": "whoosh", "at": "start"})
            if purpose in ("reveal", "punctuate") and is_last_of_beat:
                sfx_kind = SFX_BY_PURPOSE.get(purpose, ["impact"])[0]
                sfx.append({"type": sfx_kind, "at": "end"})
            if bi == total - 1 and is_last_of_beat:
                sfx.append({"type": "rise", "at": "start"})

            shots.append({
                "id": shot_id,
                "purpose": purpose,
                "beat": bi,
                # V2.3: the video IS the footage — every shot renders a real
                # clip (Wikimedia), captions overlay at the bottom. The chart
                # types are retired for daily; pacing rules above still use
                # the beat's original visual type for density.
                "visual": {
                    "type": "video",
                    "queries": _footage_queries(beat, topic),
                },
                "anchor": anchor,
                "duration_s": None,
                "motion": motion,
                "transition": transition,
                "sfx": sfx,
                "narration": narration,
                "beat_break": is_last_of_beat,
            })

    # V2.1: per-shot fields (visual_need, representation, labels, claims)
    for s in shots:
        s.update(v21.default_v21_fields(s, {}))

    # V2.1: sparse SFX budget (<=3, purposeful only: hook whoosh, first
    # reveal impact, final rise). Everything beyond the budget is dropped.
    budget = v21.SFX_BUDGET
    kept = []
    for s in shots:
        for fx in s.get("sfx", []):
            if len(kept) >= budget:
                break
            kept.append(fx)
        if len(kept) >= budget:
            break
    for s in shots:
        s["sfx"] = [fx for fx in s.get("sfx", []) if fx in kept]
    return shots


# ---------------------------------------------------------------------------
# Footage query builder (V2.3): search terms from the beat narration
# ---------------------------------------------------------------------------

_FOOTAGE_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "is", "are", "was", "were", "be", "been", "it", "its", "this",
    "that", "than", "as", "by", "from", "about", "around", "into", "over",
    "under", "how", "what", "why", "when", "which", "who", "so", "you", "your",
    "yourself", "they", "their", "them", "we", "our", "us", "i", "me", "my",
    "he", "she", "him", "her", "his", "not", "no", "yes", "just", "also",
    "very", "really", "actually", "here", "there", "every", "one", "two",
    "three", "first", "would", "could", "should", "have", "has", "had", "do",
    "does", "did", "can", "will", "may", "might", "if", "because", "while",
    "when", "where", "but", "more", "most", "much", "many", "some", "such",
    "only", "even", "still", "yet", "out", "up", "down", "off", "back",
    "called", "known", "mean", "means", "say", "says", "said", "think",
    "knows", "things", "part", "way", "parts", "stuff",
}

# Verbs / filler that are long enough to look like nouns but search poorly
# ("follow hotter", "roughly enough") — drop them so the query stays
# topic-anchored.
_FOOTAGE_WEAK_VERBS = {
    "follow", "roughly", "enough", "toward", "towards", "separating",
    "building", "comes", "make", "makes", "gives", "give", "gets", "get",
    "go", "goes", "turn", "turns", "stay", "stays", "last", "lasts", "hold",
    "holds", "sit", "sits", "run", "runs", "move", "moves", "travel",
    "travels", "happen", "happens", "seem", "seems", "appear", "appears",
    "become", "becomes", "mean", "means", "means", "part", "way", "stuff",
    "along", "alongside", "between", "among", "through", "throughout",
    "within", "without", "again", "still", "already", "almost", "nearly",
    "about", "around", "perhaps", "maybe", "often", "usually", "typically",
    "generally", "basically", "actually", "really", "quite", "rather",
    "simply", "just", "only", "even", "still", "also", "too", "well",
}


def _footage_queries(beat: dict, topic: str) -> list[str]:
    """Candidate search queries, most general first. Commons full-text
    search is picky about token count, so we try the topic alone, then
    topic + first content token, then topic + two — first hit wins."""
    toks = []
    for t in re.split(r"[\s,.;:!?'\"()\u2019]+", beat["narration"].lower()):
        if t and t not in _FOOTAGE_STOP and t not in _FOOTAGE_WEAK_VERBS \
                and len(t) > 2 and not t.isdigit():
            toks.append(t)
    out = [topic] if topic else []
    for t in toks[:2]:
        out.append(t)
    return out


def _topic_slug(playbook: dict) -> str:
    src = (playbook.get("topic") or playbook.get("name")
           or playbook.get("id") or "")
    words = re.split(r"[\s\-_:/,.!?'\u2019]+", src)
    # Capitalized words are the real subject ("Lightning is 5x hotter...";
    # "US Space Force gives Rocket Lab...") — use those first.
    capped = [w.lower() for w in words
              if w and w[0].isupper() and len(w) > 2
              and w.lower() not in _FOOTAGE_STOP]
    if not capped:
        toks = [w.lower() for w in words
                if w and len(w) > 2 and w.lower() not in _FOOTAGE_STOP]
        capped = sorted(set(toks), key=len, reverse=True)[:2]
    seen = set()
    out = []
    for t in capped:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= 3:
            break
    return " ".join(out) or "science"


# ---------------------------------------------------------------------------
# Emphasis words (priority #5/#6): what should pop in captions + text scenes
# ---------------------------------------------------------------------------

def _emphasis_words(beat: dict, seed: int) -> list[str]:
    words = []
    text = beat["narration"]
    hints = [w for w in (beat.get("emphasis") or []) if w]
    toks = [t for t in re.split(r"[\s,.;:!?]+", text) if t]
    for t in toks:
        if re.search(r"\d", t):
            words.append(t.strip(".,!?"))
    for t in toks:
        if t.lower() in ("never", "always", "wrong", "myth", "actually", "true", "impossible",
                         "closer", "older", "longer", "faster", "bigger", "not", "no",
                         "literal", "stardust", "every", "you", "real"):
            words.append(t.strip(".,!?"))
    words = hints + words
    # cap at 2 per beat to avoid caption noise
    seen, out = set(), []
    for w in words:
        key = w.lower().strip(".,!?")
        if key in seen or key not in {t.lower() for t in toks}:
            continue
        seen.add(key)
        out.append(w)
        if len(out) >= 2:
            break
    return out


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def direct(playbook: dict, date_str: str, index: int, seed: int) -> dict:
    """Produce a v2 job spec from a playbook."""
    h = pick_hook(playbook, seed)
    hook_text = h["text"]

    body = copy.deepcopy(playbook["body_variants"][(seed + index) % len(playbook["body_variants"])])

    # narration beats: the hook IS the first narration segment (spoken aloud)
    beats = [{
        "narration": hook_text,
        "visual": {"type": "hero_title", "text": hook_text},
        "emphasis": [w.strip(".,!?") for w in re.split(r"[\s,.;:!?]+", hook_text)
                     if re.search(r"\d", w)][:1],
    }]
    for i, sec in enumerate(body["sections"]):
        visual = sec["visual"]
        raw_visual = visual if isinstance(visual, dict) else {"type": visual}
        vtype = raw_visual.get("type", "text_card")
        payload = {k: v for k, v in sec.items() if k not in ("visual", "text", "emphasis")}
        if vtype == "callout" and payload.get("type"):
            raw_visual["callout_type"] = payload.pop("type")
        raw_visual = {**raw_visual, **payload}
        beat_text = sec["text"]
        hints = sec.get("emphasis") or raw_visual.get("emphasis") or []
        for chunk in _split_beat_text(beat_text):
            beats.append({
                "narration": chunk,
                "visual": {**raw_visual, "text": chunk},
                "emphasis": hints,
            })

    narration = []
    for i, b in enumerate(beats):
        narration.append({
            "id": f"n{i + 1}",
            "text": b["narration"],
            "emphasis": _emphasis_words(b, seed + i),
        })

    shots = _build_shots(beats, seed, _topic_slug(playbook))

    style = playbook.get("style", {})
    music_style = style.get("music", DEFAULT_STYLE["music"])

    theme = THEMES[(seed + index) % len(THEMES)]
    if style.get("theme"):
        theme = style["theme"]

    return {
        "date": date_str,
        "index": index,
        "seed": seed + index,
        "theme": theme,
        "playbook": playbook["id"],
        "total_estimate_s": playbook.get("target_seconds"),
        "style": {
            "music": music_style,
            "energy": style.get("energy", DEFAULT_STYLE["energy"]),
            "theme_config": style.get("theme_config"),
        },
        "story": {
            "hook": {"text": hook_text, "reason": h["reason"]},
            "beats": [{"id": f"b{i + 1}", "narration": b["narration"]} for i, b in enumerate(beats)],
            "payoff": beats[-1]["narration"] if beats else "",
        },
        "narration": narration,
        "shots": shots,
        "title": playbook["titles"][(seed + index) % len(playbook["titles"])],
        "hashtags": playbook.get("hashtags", []),
        "facts": playbook.get("facts", []),
        "description": playbook.get("description", playbook["name"]),
    }


if __name__ == "__main__":
    import sys
    pid = sys.argv[1] if len(sys.argv) > 1 else "how-llms-work"
    pb = load_playbook(pid)
    job = direct(pb, "2026-08-13", 1, 20260813)
    print(json.dumps({"playbook": job["playbook"], "n_shots": len(job["shots"]),
                      "shots": [s["id"] for s in job["shots"]],
                      "purposes": [s["purpose"] for s in job["shots"]],
                      "motions": [s["motion"] for s in job["shots"]]}, indent=2))