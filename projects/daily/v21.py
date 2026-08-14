"""V2.1: video-first spec support for the daily pipeline.

1. Topic scoring gate  (before production)
2. Representation + label defaults for built visuals
3. V2.1 checks          (after render, advisory + hard rules)
4. Per-shot V2.1 field defaults (visual_need, visual_claim, factual_risk,
   why_shot_exists, source_type, source_label, on_screen_label)

qc.py is intentionally untouched; V2.1 checks live here.
"""

import json
import re

REPRESENTATIONS = ("REAL", "ILLUSTRATION", "SIMULATION", "STOCK")

# ---------------------------------------------------------------------------
# Representation defaults for built visuals (what the viewer sees is a graphic)
# ---------------------------------------------------------------------------

ILLUSTRATION_TYPES = {
    "bar_chart", "line_chart", "pie_chart", "kpi_grid", "progress_bar",
    "timeline", "comparison", "stat_card", "hero_title", "text_card", "callout",
}
SIMULATION_TYPES = {"anime_scene", "terminal_scene", "screenshot_scene"}

# Text/hero cards encode a claim as text, not imagery — no footage confusion,
# so no representation class and no on-screen label.
TEXT_TYPES = {"hero_title", "text_card", "callout", "CTA"}

PURPOSE_NEED = {
    "hook": "a strong pattern-interrupt visual in the first 3 seconds, before any exposition",
    "setup": "establish the subject concretely so the later reveals have an anchor",
    "show": "make the abstract claim visible as something the eye can parse",
    "contrast": "scale/shock contrast between two magnitudes on screen",
    "reveal": "the headline number or stat landing exactly when the narration names it",
    "signal": "direct attention to the part of the frame that matters now",
    "punctuate": "close the loop on the hook with a payoff visual",
}

WHY_EXISTS = {
    "hook": "the first 3 seconds must land a strong visual + hook; removing it kills the video",
    "setup": "context before the reveal; removing it leaves later beats abstract",
    "show": "grounds the claim in a concrete visual; removing it turns the story into talking",
    "contrast": "the comparison is the emotional core of the beat; removing it flattens the arc",
    "reveal": "the number/stat is the pattern interrupt; removing it defers the payoff",
    "signal": "guides the eye to the meaningful element; removing it costs attention",
    "punctuate": "the payoff shot; removing it ends the video without landing the point",
}

RISK_BY_TYPE = {
    "stat_card": "medium - headline number; verify against playbook facts before publish",
    "comparison": "medium - magnitudes must match the sourced facts",
    "timeline": "low - built graphic; timeline must match sourced facts",
    "bar_chart": "low - built graphic of playbook data",
    "line_chart": "low - built graphic of playbook data",
    "pie_chart": "low - built graphic of playbook data",
    "kpi_grid": "low - built graphic of playbook data",
    "progress_bar": "low - built graphic of playbook data",
    "hero_title": "low - text claim, sourced in the script",
    "text_card": "low - text claim, sourced in the script",
    "callout": "low - text claim, sourced in the script",
    "anime_scene": "low - labeled simulation, cannot be mistaken for footage",
    "terminal_scene": "low - labeled simulation",
    "screenshot_scene": "low - labeled simulation",
}


def default_v21_fields(shot: dict, playbook: dict) -> dict:
    """Fill V2.1 fields for a built-graphic shot. Playbook facts stay the
    source of truth; these describe the visual's role and risk only."""
    v = shot.get("visual", {})
    vtype = "text_card" if v.get("type") == "CTA" else v.get("type", "text_card")
    purpose = shot.get("purpose", "show")

    if vtype in TEXT_TYPES:
        representation = None
    elif vtype in SIMULATION_TYPES:
        representation = "SIMULATION"
    elif vtype in ("image", "video"):
        representation = "STOCK" if vtype == "image" else "REAL"
    else:
        representation = "ILLUSTRATION"

    fields = {
        "visual_need": PURPOSE_NEED.get(purpose, PURPOSE_NEED["show"]),
        "representation": representation,
        "source_type": "text" if representation is None else
                       ("WIKIMEDIA_PHOTO" if representation == "STOCK" else
                        "WIKIMEDIA_VIDEO" if representation == "REAL" else
                        "built_graphic" if representation == "ILLUSTRATION" else "built_scene"),
        "source_label": "text on screen (no imagery claim)" if representation is None else
                        ("Wikimedia Commons photograph (license recorded at render)" if representation == "STOCK"
                         else "Wikimedia Commons footage (license recorded at render)" if representation == "REAL"
                         else "built graphic (local render)" if representation == "ILLUSTRATION"
                         else "built simulation (local render)"),
        "visual_claim": (shot.get("narration") or "").strip(),
        "factual_risk": RISK_BY_TYPE.get(vtype, "low"),
        "why_shot_exists": WHY_EXISTS.get(purpose, WHY_EXISTS["show"]),
        "on_screen_label": "ILLUSTRATION" if representation == "ILLUSTRATION"
                           else ("SIMULATION" if representation == "SIMULATION" else None),
    }
    return {k: (shot.get(k) or fields[k]) for k in fields}


# ---------------------------------------------------------------------------
# Topic scoring gate (before production)
# ---------------------------------------------------------------------------

TOPIC_THRESHOLD = 5.0


def score_topic(playbook: dict) -> dict:
    """Score a playbook topic 0-10. Below threshold -> skip for today.

    Honest scoring, no invented metrics: concreteness, number-content,
    contradiction, specificity of the title, source tier, recency.
    """
    score = 5.0
    reasons = []
    name = (playbook.get("name") or "") + " " + (playbook.get("title", "") or playbook.get("name") or "")
    title = playbook.get("title") or playbook.get("name") or ""
    hook_text = " ".join(h.get("template", "") for h in playbook.get("hook_variants", []))

    if re.search(r"\d", title + hook_text):
        score += 1.5
        reasons.append("numeric hook")
    if any(w in hook_text.lower() for w in ["lie", "myth", "wrong", "actually", "never",
                                            "no way", "but", "impossible", "only"]):
        score += 1.0
        reasons.append("contradiction angle")
    if len(title) >= 4:
        score += 1.0
        reasons.append("specific title")
    if len(title) > 60:
        score -= 1.0
        reasons.append("title too long")

    facts = playbook.get("facts", [])
    tier1 = [f for f in facts if str(f.get("tier", 3)) == "1"]
    if len(tier1) >= 3:
        score += 1.5
        reasons.append(f"{len(tier1)} tier-1 sources")
    elif not facts:
        score -= 2.0
        reasons.append("no facts to trace claims to")

    if playbook.get("news_slot"):
        score -= 2.0
        reasons.append("news_slot (not for shorts)")

    if playbook.get("last_used"):
        score -= 1.0
        reasons.append("recently used")

    score = max(0.0, min(10.0, score))
    return {"score": round(score, 1), "pass": score >= TOPIC_THRESHOLD,
            "reasons": reasons}


# ---------------------------------------------------------------------------
# V2.1 checks (after render) — mirrors samples/neutron-star/sample_qa.py
# ---------------------------------------------------------------------------

ALLOWED_SOURCE_TYPES = {
    "built_graphic", "built_scene", "photograph", "photograph_reframed",
    "NASA_artist_impression", "Hubble_observation", "NASA_telescopic_timelapse",
    "built_animation", "built_comparison",
    "built stat graphic over the same photo",
    "WIKIMEDIA_PHOTO", "WIKIMEDIA_VIDEO",
}
SFX_BUDGET = 3


def _resolve(shots, starts, ends):
    return [(s, starts.get(s["id"], 0.0), ends.get(s["id"], 0.0)) for s in shots]


def check_v21(job: dict, shots: list[dict], starts: dict, ends: dict,
              captions: list[dict], sfx_events: list[dict]) -> dict:
    """V2.1 video-first checks. Advisory except: filler shots, representation
    validity, unlabelled simulations/illustrations, SFX over budget."""
    checks = []
    total = max((ends.get(s["id"], 0.0) for s in shots), default=1.0)
    resolved = _resolve(shots, starts, ends)

    # 1. first 3 seconds: strong visual + hook, moving representation
    first = resolved[0] if resolved else None
    if not first:
        checks.append({"check": "v21_first_3s", "status": "fail", "msg": "no shots"})
    else:
        s, st, _ = first
        ok = st <= 0.2 and s.get("purpose") == "hook" and \
            s.get("motion") not in (None, "static") and bool(s.get("narration", "").strip())
        checks.append({"check": "v21_first_3s", "status": "pass" if ok else "fail",
                       "msg": f"first shot {s['id']} @ {st:.1f}s purpose={s.get('purpose')} "
                              f"motion={s.get('motion')} text={bool(s.get('narration'))}"})

    # 2. no static/filler shots (motion 'static' only for self-animated scenes)
    from director import SELF_ANIMATED_TYPES
    static_bad = []
    for s, _st, _en in resolved:
        vtype = s.get("visual", {}).get("type")
        self_animated = vtype in SELF_ANIMATED_TYPES
        if s.get("motion") in (None, "static") and not self_animated:
            static_bad.append(s["id"])
    checks.append({"check": "v21_no_static_filler", "status": "fail" if static_bad else "pass",
                   "msg": f"static/filler shots: {static_bad or 'none'}"})

    # 3. representation validity + labels
    bad_rep = [s["id"] for s in shots
               if s.get("representation") not in (None,) + REPRESENTATIONS]
    checks.append({"check": "v21_representation_valid", "status": "fail" if bad_rep else "pass",
                   "msg": f"invalid representation: {bad_rep or 'none'}"})
    unlabelled = [s["id"] for s in shots
                  if s.get("representation") in ("ILLUSTRATION", "SIMULATION")
                  and not s.get("on_screen_label")]
    checks.append({"check": "v21_representation_labelled", "status": "fail" if unlabelled else "pass",
                   "msg": f"simulation/illustration without on-screen label: {unlabelled or 'none'}"})

    # 4. V2.1 fields present
    missing = [s["id"] for s in shots
               if not s.get("visual_claim") or not s.get("factual_risk")
               or not s.get("why_shot_exists") or not s.get("visual_need")]
    checks.append({"check": "v21_fields_present", "status": "fail" if missing else "pass",
                   "msg": f"shots missing V2.1 fields: {missing or 'none'}"})

    # 4b. provenance: real footage/stock photos must record where they came from
    no_prov = [s["id"] for s in shots
               if s.get("representation") in ("REAL", "STOCK")
               and not s.get("source_label")]
    checks.append({"check": "v21_provenance", "status": "warn" if no_prov else "pass",
                   "msg": f"REAL/STOCK shots without source_label: {no_prov or 'none'}"})

    # 5. SFX budget
    checks.append({"check": "v21_sfx_sparse", "status": "fail" if len(sfx_events) > SFX_BUDGET else "pass",
                   "msg": f"{len(sfx_events)} SFX events (budget {SFX_BUDGET})"})

    # 6. footage ratio (measured, never gated)
    motion_time = sum(en - st for s, st, en in resolved
                      if s.get("motion") not in (None, "static"))
    checks.append({"check": "v21_footage_ratio", "status": "pass",
                   "msg": f"motion-bearing runtime {motion_time:.1f}s / {total:.1f}s "
                          f"({motion_time / max(total, 0.01) * 100:.0f}%) - measured only, not gated"})

    # 7. long shot warning: >7s only OK if the visual moves with purpose
    long_moving = [(s["id"], round(en - st, 1)) for s, st, en in resolved
                   if en - st > 7.0 and s.get("motion") not in (None, "static")]
    long_static = [(s["id"], round(en - st, 1)) for s, st, en in resolved
                   if en - st > 7.0 and s.get("motion") in (None, "static")]
    if long_static:
        checks.append({"check": "v21_no_long_static", "status": "warn",
                       "msg": f"long static shots: {long_static}"})
    else:
        checks.append({"check": "v21_no_long_static", "status": "pass",
                       "msg": f"long moving shots (OK if purposeful): {long_moving or 'none'}"})

    # 8. caption variety: karaoke + at least one stat/hero moment
    emph = sum(1 for c in captions if c.get("emphasize"))
    has_stat = any(s.get("visual", {}).get("type") == "stat_card" for s in shots)
    has_hero = any(s.get("visual", {}).get("type") == "hero_title" for s in shots)
    variety = emph >= 2 and (has_stat or has_hero)
    checks.append({"check": "v21_caption_variety", "status": "pass" if variety else "warn",
                   "msg": f"styles: karaoke+{'stat_card' if has_stat else ''}"
                          f"{'hero_title' if has_hero else ''}, {emph} emphasized words"})

    # 9. reuse audit: same asset with identical motion+role is gratuitous
    uses = {}
    for s in shots:
        uses.setdefault(s.get("visual", {}).get("text"), []).append(s)
    reuse_bad = []
    for key, ss in uses.items():
        if not key or len(ss) < 2:
            continue
        roles = {(s.get("motion"), s.get("purpose")) for s in ss}
        if len(roles) == 1:
            reuse_bad.append(key[:40])
    checks.append({"check": "v21_reuse_audit", "status": "pass" if not reuse_bad else "warn",
                   "msg": f"gratuitous repeats: {reuse_bad or 'none'}"})

    fails = [c for c in checks if c["status"] == "fail"]
    score = round(sum(1 for c in checks if c["status"] == "pass") / max(1, len(checks)) * 100)
    return {"score": score, "checks": checks, "passed": len(checks) - len(fails),
            "total": len(checks), "fails": [c["msg"] for c in fails]}