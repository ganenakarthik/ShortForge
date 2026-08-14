"""Viewer-experience QC for V2 shorts.

Technical QC (probe, size, duration) lives in render_job. This module checks
the *experience*: pacing, shot purpose, density, hook, payoff, captions,
audio. The hard rule:

    If removing a shot would not change the viewer's understanding, emotion
    or emphasis, that shot should fail QC.

Every check returns (status: pass|warn|fail, message). Checks are advisory
except the filler rule, which fails the render.
"""

import json

ALLOWED_PURPOSES = ["hook", "setup", "show", "contrast", "reveal", "signal", "punctuate"]
STATIC_TYPES = {"hero_title", "CTA"}
PAYOFF_TYPES = {"callout", "hero_title", "CTA", "text_card"}
# Scenes that animate internally (bars draw, milestones pop, progress advances):
# a 'static' wrapper motion still yields a moving frame.
SELF_ANIMATED_TYPES = {"timeline", "bar_chart", "line_chart", "pie_chart", "kpi_grid",
                       "progress_bar", "terminal_scene"}
MAX_STATIC_SECONDS = 4.5
MAX_SHOT_SECONDS = 8.0
TARGET_DENSITY_MIN = 2.0       # meaningful visual changes per 10s (warn below)
TARGET_DENSITY_HIGH = 6.0


def _resolve(shots, starts, ends):
    return [(s, starts.get(s["id"], 0.0), ends.get(s["id"], 0.0)) for s in shots]


def qc_viewer(job: dict, shots: list[dict], starts: dict, ends: dict,
              captions: list[dict], audio_stats: dict, style: dict) -> dict:
    checks = []
    total = max((ends.get(s["id"], 0.0) for s in shots), default=1.0)
    resolved = _resolve(shots, starts, ends)

    # --- 1. filler hard rule -------------------------------------------------
    fillers = [s["id"] for s in shots if s.get("purpose") not in ALLOWED_PURPOSES]
    if fillers:
        checks.append({"check": "no_filler_shots", "status": "fail",
                       "msg": f"shots without a purpose: {fillers}"})
    else:
        checks.append({"check": "no_filler_shots", "status": "pass", "msg": "every shot has a purpose"})

    # --- 2. shot relevance / representation ---------------------------------
    dup_runs = 0
    prev_type = None
    max_run = 0
    for s, _st, _en in resolved:
        v = s.get("visual", {})
        t = v.get("type")
        if t == prev_type:
            dup_runs += 1
        else:
            dup_runs = 0
        max_run = max(max_run, dup_runs)
        prev_type = t
    if max_run > 2:
        checks.append({"check": "visual_variety", "status": "warn",
                       "msg": f"{max_run} consecutive same-type visuals"})
    else:
        checks.append({"check": "visual_variety", "status": "pass", "msg": "visual types alternate"})

    # --- 3. no long static periods ------------------------------------------
    long_static = []
    for s, st, en in resolved:
        dur = en - st
        vtype = s.get("visual", {}).get("type")
        self_animated = vtype in SELF_ANIMATED_TYPES
        static = (s.get("motion") in ("static",) or vtype in STATIC_TYPES) and not self_animated
        if static and dur > MAX_STATIC_SECONDS and s.get("purpose") not in ("signal", "punctuate"):
            long_static.append(f"{s['id']} ({dur:.1f}s static)")
    if long_static:
        checks.append({"check": "no_long_static", "status": "warn", "msg": f"long static shots: {long_static}"})
    else:
        checks.append({"check": "no_long_static", "status": "pass", "msg": "no filler-length static holds"})

    # --- 4. meaningful visual changes / density ------------------------------
    changes = sum(1 for i in range(1, len(resolved))
                  if resolved[i][0].get("visual", {}).get("type") != resolved[i - 1][0].get("visual", {}).get("type")
                  or resolved[i][0].get("motion") != resolved[i - 1][0].get("motion")
                  or resolved[i][0].get("visual", {}).get("text") != resolved[i - 1][0].get("visual", {}).get("text"))
    density = changes / (total / 10.0) if total > 0 else 0
    if density < TARGET_DENSITY_MIN:
        checks.append({"check": "shot_density", "status": "warn",
                       "msg": f"{density:.1f} visual changes/10s (want {TARGET_DENSITY_MIN}-{TARGET_DENSITY_HIGH})"})
    elif density > TARGET_DENSITY_HIGH:
        checks.append({"check": "shot_density", "status": "warn",
                       "msg": f"{density:.1f} visual changes/10s — busy, likely random cuts"})
    else:
        checks.append({"check": "shot_density", "status": "pass",
                       "msg": f"{density:.1f} meaningful visual changes/10s"})

    # --- 5. hook strength -----------------------------------------------------
    first = resolved[0] if resolved else None
    if not first:
        checks.append({"check": "hook", "status": "fail", "msg": "no shots at all"})
    else:
        s, st, _en = first
        hook_ok = (st <= 0.2 and s.get("purpose") == "hook"
                   and s.get("motion") not in ("static",)
                   and s.get("visual", {}).get("text", "").strip())
        checks.append({"check": "hook", "status": "pass" if hook_ok else "warn",
                       "msg": f"hook shot {s['id']} @ {st:.1f}s purpose={s.get('purpose')} motion={s.get('motion')}"})

    # --- 6. pacing ------------------------------------------------------------
    avg = sum(en - st for _s, st, en in resolved) / max(1, len(resolved))
    too_long = [(s["id"], en - st) for s, st, en in resolved if (en - st) > MAX_SHOT_SECONDS
                and s.get("purpose") not in ("signal", "punctuate")]
    if too_long or avg > 6.0:
        checks.append({"check": "pacing", "status": "warn",
                       "msg": f"avg shot {avg:.1f}s; too long: {too_long}"})
    else:
        checks.append({"check": "pacing", "status": "pass", "msg": f"avg shot {avg:.1f}s"})

    # --- 7. payoff clarity -----------------------------------------------------
    last = resolved[-1] if resolved else None
    if not last:
        checks.append({"check": "payoff", "status": "fail", "msg": "no payoff shot"})
    else:
        s, _st, _en = last
        payoff_ok = s.get("purpose") in ("signal", "punctuate") and \
            s.get("visual", {}).get("type") in PAYOFF_TYPES
        checks.append({"check": "payoff", "status": "pass" if payoff_ok else "warn",
                       "msg": f"payoff shot {s['id']} type={s.get('visual', {}).get('type')} purpose={s.get('purpose')}"})

    # --- 8. captions -----------------------------------------------------------
    overlaps = 0
    for i in range(1, len(captions)):
        if captions[i]["startMs"] < captions[i - 1]["endMs"] - 5:
            overlaps += 1
    emph_count = sum(1 for c in captions if c.get("emphasize"))
    cap_span = captions[-1]["endMs"] - captions[0]["startMs"] if captions else 0
    coverage = cap_span / (total * 1000) if total > 0 else 0
    cap_msgs = []
    if overlaps:
        cap_msgs.append(f"{overlaps} overlapping caption words")
    if coverage < 0.7:
        cap_msgs.append(f"caption coverage {coverage:.0%} of runtime")
    if emph_count < 2:
        cap_msgs.append("fewer than 2 emphasized words")
    if cap_msgs:
        checks.append({"check": "captions", "status": "warn", "msg": "; ".join(cap_msgs)})
    else:
        checks.append({"check": "captions", "status": "pass",
                       "msg": f"{len(captions)} words, {emph_count} emphasized, {coverage:.0%} coverage"})

    # --- 9. audio quality -------------------------------------------------------
    peak_db = audio_stats.get("peak_db")
    narr_rms = audio_stats.get("narration_rms_db")
    music_rms = audio_stats.get("music_rms_db")
    narr_on = audio_stats.get("narration_active_s", 0.0)
    audio_msgs = []
    if peak_db is not None and peak_db > -1.0:
        audio_msgs.append(f"peak {peak_db:.1f} dBFS (clipping risk)")
    if narr_rms is not None and narr_rms < -40.0:
        audio_msgs.append(f"narration too quiet ({narr_rms:.1f} dBFS)")
    if music_rms is not None and music_rms > -20.0 and narr_on > 0.5 * (total or 1):
        audio_msgs.append(f"music bed too loud ({music_rms:.1f} dBFS RMS)")
    if audio_msgs:
        checks.append({"check": "audio_mix", "status": "warn", "msg": "; ".join(audio_msgs)})
    else:
        checks.append({"check": "audio_mix", "status": "pass",
                       "msg": f"peak {peak_db:.1f} dBFS, narration {narr_rms:.1f} dBFS, bed {music_rms:.1f} dBFS"})

    # --- 10. no repeated visual without narrative purpose ----------------------
    # a re-framed shot (different motion) on the same card is a deliberate
    # setup+reveal pair, not a repeated visual
    prev = None
    repeats = []
    for s, _st, _en in resolved:
        key = (s.get("visual", {}).get("type"), s.get("visual", {}).get("text"))
        if key == prev and s.get("motion") == prev_motion:
            repeats.append(s["id"])
        prev = key
        prev_motion = s.get("motion")
    if repeats:
        checks.append({"check": "no_purposeful_repeat", "status": "warn",
                       "msg": f"identical consecutive visuals: {repeats}"})
    else:
        checks.append({"check": "no_purposeful_repeat", "status": "pass", "msg": "no repeated visuals"})

    fails = [c for c in checks if c["status"] == "fail"]
    score = round(sum(1 for c in checks if c["status"] == "pass") / max(1, len(checks)) * 100)
    return {"score": score, "checks": checks, "passed": len(checks) - len(fails), "total": len(checks),
            "fails": [c["msg"] for c in fails]}


def load_job(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)