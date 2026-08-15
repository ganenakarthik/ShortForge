"""V2 render: storyboard-first short production.

job (v2 JSON)
  -> narration beats -> Edge TTS (Piper lessac-high fallback)
  -> faster-whisper word alignment -> per-word caption timeline (with emphasis)
  -> shot anchors resolved against the narration timeline (cuts can happen
     mid-sentence; shots can span beats)
  -> music bed + SFX + sidechain ducking baked into one mix
  -> Remotion ExplainerVertical render (each cut carries its own motion,
     transition and purpose)
  -> loudnorm master pass -> technical probe -> viewer-experience QC report

Deterministic per seed; idempotent per output file (existing mp4 is reused).
"""

import json
import math
import os
import shutil
import subprocess
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
OPENMONTAGE = os.path.normpath(os.path.join(ROOT, "..", ".."))
REMOTION = os.path.join(OPENMONTAGE, "remotion-composer")
VENV = os.path.join(OPENMONTAGE, ".venv", "Scripts")
GAP = 0.16
TAIL = 0.9
MIN_SHOT = 0.9
# V2.1: no hard shot-length rule — the rule is NO STATIC/FILLER SHOTS.
# MAX_SHOT is a runaway safety net only (12s), V2.1 QC warns on long shots.
MAX_SHOT = 12.0
SFX_BUDGET = 3
TRANSITION_DUR = {"fade": 0.30, "punch": 0.24, "slide_left": 0.34, "slide_right": 0.34,
                  "cut": 0.0, "none": 0.0}

sys.path.insert(0, ROOT)
import tts_engine  # noqa: E402
import align  # noqa: E402
import audio_design as ad  # noqa: E402
import qc as qc_mod  # noqa: E402
import sources  # noqa: E402

ASSETS = os.path.join(ROOT, "tmp", "assets")
OUT_TMP = os.path.join(ROOT, "tmp")


def _asset_path(name: str) -> str:
    """Absolute path so Remotion can load it via file:// ."""
    return os.path.join(ASSETS, name)


# ---------------------------------------------------------------------------
# Step 1-2: narration synthesis + timeline
# ---------------------------------------------------------------------------

def _synthesize_narration(job: dict) -> tuple[dict, dict, float]:
    """TTS per narration segment. Returns (durations, starts/ends, total)."""
    durations, starts, ends = {}, {}, {}
    voice_index = job["seed"] % 3
    t = 0.0
    for i, seg in enumerate(job["narration"]):
        wav = _asset_path(f"{seg['id']}.wav")
        dur = tts_engine.synthesize(seg["text"], wav, voice_index + i)
        durations[seg["id"]] = dur
        starts[seg["id"]] = t
        ends[seg["id"]] = t + dur
        t = ends[seg["id"]] + GAP
    total = t - GAP
    return durations, starts, ends, total


def _concat_narration(job: dict, durations: dict) -> str:
    wavs = [(os.path.join(ASSETS, f"{s['id']}.wav"), durations[s["id"]]) for s in job["narration"]]
    out = os.path.join(ASSETS, "narration.wav")
    tts_engine.concatenate(wavs, out, gap=GAP)
    return out


# ---------------------------------------------------------------------------
# Step 3: alignment -> captions with emphasis
# ---------------------------------------------------------------------------

def _build_captions(job: dict, starts: dict, ends: dict, durations: dict,
                    narration_wav: str) -> tuple[list[dict], str]:
    segments = [dict(s, _start=starts[s["id"]], _end=ends[s["id"]]) for s in job["narration"]]
    seg_words, engine = align.align_words(segments, durations, starts, narration_wav)

    emph_sets = {}
    for seg in job["narration"]:
        emph_sets[seg["id"]] = {w.lower().strip(".,!?") for w in seg.get("emphasis", [])}

    caps = []
    for sg in seg_words:
        sid = sg["id"]
        for w in sg["words"]:
            if w["text"] == "\u200b":
                continue
            caps.append({
                "word": w["text"],
                "startMs": round(w["start"] * 1000),
                "endMs": round(w["end"] * 1000),
                "emphasize": w["text"].lower().strip(".,!?") in emph_sets.get(sid, set()),
            })
    # Words are already in correct segment order from align (per-segment
    # greedy ordered match). Whisper per-word timestamps near segment
    # boundaries are unreliable, so a GLOBAL timestamp sort would scatter
    # words across beats — never re-sort the whole timeline.
    for i in range(1, len(caps)):
        prev_end = caps[i - 1]["endMs"]
        if caps[i]["startMs"] < prev_end:
            caps[i]["startMs"] = prev_end
        if caps[i]["endMs"] <= caps[i]["startMs"]:
            caps[i]["endMs"] = caps[i]["startMs"] + 30
    return caps, engine


# ---------------------------------------------------------------------------
# Step 4: resolve shot anchors -> absolute in/out + transitions
# ---------------------------------------------------------------------------

def _resolve_anchor(anchor: dict, starts: dict, ends: dict) -> float:
    sid = anchor.get("narration")
    s0 = starts.get(sid, 0.0)
    s1 = ends.get(sid, s0 + 2.0)
    at = anchor.get("at", "start")
    if at == "end":
        return s1
    if at == "mid":
        return (s0 + s1) / 2.0
    if at == "fraction":
        frac = float(anchor.get("fraction", 0.5))
        return s0 + (s1 - s0) * max(0.05, min(0.95, frac))
    return s0


def _resolve_shots(job: dict, starts: dict, ends: dict, video_end: float):
    """Absolute times, overlaps for transitions, per-cut transition fields."""
    shots = job["shots"]
    ins = []
    for s in shots:
        ins.append(_resolve_anchor(s["anchor"], starts, ends))

    out = {}
    for i, s in enumerate(shots):
        nxt_in = ins[i + 1] if i + 1 < len(shots) else video_end
        dur = nxt_in - ins[i]
        if dur < MIN_SHOT:                      # too tight: hold to next boundary
            dur = MIN_SHOT
        out[s["id"]] = ins[i] + min(dur, MAX_SHOT if s.get("purpose") not in ("signal", "punctuate") else 9.0)

    # transition overlap: previous shot extends into the next transition
    for i in range(len(shots) - 1):
        nxt = shots[i + 1]
        tr = nxt.get("transition", "cut")
        tr_dur = TRANSITION_DUR.get(tr, 0.0)
        if tr_dur > 0:
            cur_out = out[shots[i]["id"]]
            nxt_in = ins[i + 1]
            if cur_out <= nxt_in:
                out[shots[i]["id"]] = nxt_in + tr_dur

    # clamp so no overlap exceeds the next shot's full duration
    for i in range(len(shots) - 1):
        if out[shots[i]["id"]] > ins[i + 1] + max(0.0, out[shots[i + 1]["id"]] - ins[i + 1]):
            out[shots[i]["id"]] = ins[i + 1] + 0.2

    return ins, out


# ---------------------------------------------------------------------------
# Step 5: audio bed — music + sfx + ducking
# ---------------------------------------------------------------------------

def _sfx_events(job: dict, ins: list, outs: dict) -> list[dict]:
    events = []
    for i, s in enumerate(job["shots"]):
        for fx in s.get("sfx", []):
            if len(events) >= SFX_BUDGET:
                break
            at = fx.get("at", "start")
            t_ = ins[i] if at == "start" else outs[s["id"]]
            kind = fx.get("type")
            duration = {"whoosh": 0.5, "impact": 0.6, "rise": 1.4, "pop": 0.25, "ding": 0.8}.get(kind, 0.5)
            events.append({"type": kind, "in_seconds": round(t_, 3),
                           "duration": duration, "seed": job["seed"] + i,
                           "volume": 0.5 if kind in ("whoosh", "ding", "pop") else 0.75})
        if len(events) >= SFX_BUDGET:
            break
    return events


def _audio_stats(narration_wav: str, music_wav: str, windows: list[tuple[float, float]]) -> dict:
    def read(wav):
        with wave.open(wav, "rb") as w:
            data = w.readframes(w.getnframes())
            return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    narr = read(narration_wav)
    music = read(music_wav)
    sr = 44100
    peak_db = 20 * math.log10(max(1e-6, float(np.max(np.abs(music)))))
    active_mask = np.zeros(len(music), dtype=bool)
    for s0, s1 in windows:
        active_mask[int(s0 * sr):int(s1 * sr)] = True
    narr_rms = 20 * math.log10(max(1e-6, float(np.sqrt(np.mean(narr ** 2)))))
    music_rms = 20 * math.log10(max(1e-6, float(np.sqrt(np.mean(music ** 2)))))
    return {"peak_db": round(peak_db, 2), "narration_rms_db": round(narr_rms, 2),
            "music_rms_db": round(music_rms, 2),
            "narration_active_s": round(float(active_mask.sum()) / sr, 2)}


def _render_job_internal(job_path: str, out_mp4: str,
                         dry: bool = False) -> dict:
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)

    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)

    # 1+2 narration
    durations, starts, ends, total = _synthesize_narration(job)
    narration_wav = _concat_narration(job, durations)
    video_end = round(total + TAIL + 0.35, 2)

    # 3 alignment + captions
    captions, align_engine = _build_captions(job, starts, ends, durations, narration_wav)

    # 4 shots timeline
    ins, outs = _resolve_shots(job, starts, ends, video_end)

    # 5 audio bed
    style = job.get("style", {})
    music_style = style.get("music", "upbeat_pulse")
    music = ad.synth_music(music_style, video_end + 0.5, job["seed"])
    sfx_events = _sfx_events(job, ins, outs)
    windows = [(starts[s["id"]], ends[s["id"]] + 0.05) for s in job["narration"]]
    music_mix = _asset_path("music_mix.wav")
    ad.mix_music(music, sfx_events, windows, music_mix)
    stats = _audio_stats(narration_wav, music_mix, windows)

    # 6 props.json
    job_dir = f"daily-{job['date']}-{job['index']}"
    pub_dir = os.path.join(REMOTION, "public", job_dir)
    os.makedirs(pub_dir, exist_ok=True)
    accent_pool = ["#22D3EE", "#F59E0B", "#7C3AED", "#EC4899", "#10B981", "#EF4444",
                   "#EAB308", "#38BDF8", "#A78BFA", "#FB7185"]
    cuts = []
    for i, s in enumerate(job["shots"]):
        v = s["visual"]
        vtype = "text_card" if v["type"] == "CTA" else v["type"]
        accent = v.get("accent") or accent_pool[(job["seed"] + i) % len(accent_pool)]
        cut = {
            "id": s["id"],
            "type": vtype,
            "in_seconds": round(ins[i], 2),
            "out_seconds": round(outs[s["id"]], 2),
            "motion": {"type": s.get("motion", "zoom_in")},
            "transition_in": s.get("transition", "cut") if i > 0 else "fade",
            "transition_out": "fade",
            "transitionOutDuration": 0.3,
            "representation": s.get("representation"),
            "label": s.get("on_screen_label"),
        }
        if vtype in ("text_card", "hero_title"):
            cut["text"] = v["text"]
            if v.get("subtitle"):
                cut["heroSubtitle"] = v["subtitle"]
            if vtype == "hero_title":
                cut["heroSubtitle"] = cut.get("heroSubtitle", "")
            cut["emphasis"] = [w for w in (v.get("emphasis") or [])]
            cut["accentColor"] = accent
        elif vtype == "stat_card":
            cut["stat"] = v["stat"]
            cut["subtitle"] = v.get("subtitle", "")
            cut["accentColor"] = accent
        elif vtype == "bar_chart":
            cut["title"] = v.get("title", "")
            cut["chartData"] = v["data"]
            cut["chartColors"] = [accent]
            cut["showValues"] = True
            cut["showGrid"] = True
        elif vtype == "pie_chart":
            cut["title"] = v.get("title", "")
            cut["chartData"] = v["data"]
            cut["chartColors"] = [accent, "#334155"]
        elif vtype == "kpi_grid":
            cut["title"] = v.get("title", "")
            cut["chartData"] = v["data"]
            cut["columns"] = v.get("columns", 3)
        elif vtype == "callout":
            cut["callout_type"] = v.get("callout_type") or "info"
            cut["title"] = v.get("title", "")
            cut["text"] = v.get("body", v["text"])
            cut["accentColor"] = accent
        elif vtype == "progress_bar":
            cut["title"] = v.get("title", "")
            cut["progress"] = v.get("progress", 0.5)
            cut["progressLabel"] = v.get("label", "")
            cut["progressColor"] = accent
        elif vtype == "comparison":
            cut["title"] = v.get("title", "")
            cut["leftLabel"] = v.get("left", "")
            cut["leftValue"] = v.get("lvalue", "")
            cut["rightLabel"] = v.get("right", "")
            cut["rightValue"] = v.get("rvalue", "")
            cut["accentColor"] = accent
        elif vtype == "timeline":
            cut["title"] = v.get("title", "")
            cut["milestones"] = v.get("milestones", [])
            cut["accentColor"] = accent
        elif vtype in ("image", "video"):
            # Topic-relevant real footage: fetch + stage, fall back to text
            kind = "video" if vtype == "video" else "image"
            query = v.get("query") or v.get("search") or s.get("narration", "")
            try:
                local, meta = sources.resolve(query, kind)
                fname = os.path.basename(local)
                dst = os.path.join(pub_dir, fname)
                if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(local):
                    os.makedirs(pub_dir, exist_ok=True)
                    shutil.copyfile(local, dst)
                cut["source"] = f"{job_dir}/{fname}"
                cut["animation"] = v.get("animation") or ("zoom-in" if kind == "image" else "static")
                if vtype == "video":
                    cut["source_in_seconds"] = v.get("source_in_seconds", 0)
                s["source_label"] = f"{meta['license']} — {meta['title'][:70]}"
                s["source_url"] = meta["url"]
                s["source_type"] = "WIKIMEDIA_PHOTO" if kind == "image" else "WIKIMEDIA_VIDEO"
            except Exception as exc:
                print(f"[warn] asset fetch failed for {query!r}: {exc}; fallback to text card")
                cut["type"] = "text_card"
                cut["text"] = s.get("narration") or v.get("text", "")
        else:
            raise ValueError(f"unknown visual type: {vtype}")
        cuts.append(cut)

    caption_final = []
    for c in captions:
        caption_final.append({"word": c["word"], "startMs": c["startMs"],
                              "endMs": c["endMs"], "emphasize": bool(c.get("emphasize"))})

    theme_config = style.get("theme_config")

    # stage audio into the composer's public dir; Remotion only serves
    # staticFile()/http(s) assets, so absolute paths (-> file://) are rejected
    for name, src in (("narration.wav", narration_wav), ("music_mix.wav", music_mix)):
        dst = os.path.join(pub_dir, name)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)

    props = {
        "theme": job["theme"],
        "themeConfig": theme_config,
        "cuts": cuts,
        "overlays": [],
        "captions": caption_final,
        "audio": {
            "narration": {"src": f"{job_dir}/narration.wav", "volume": 1.0},
            "music": {"src": f"{job_dir}/music_mix.wav", "volume": 1.0, "offsetSeconds": 0.0,
                      "loop": False, "fadeInSeconds": 0.8, "fadeOutSeconds": 1.5},
        },
        "avatar": {"enabled": False},
    }
    props_path = os.path.join(OUT_TMP, f"props_{job['index']}_{job['seed']}.json")
    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f, indent=2)

    if dry:
        return {"dry": True, "video_end": video_end, "props": props_path,
                "cuts": len(cuts), "captions": len(caption_final)}

    # 7 remotion render
    npx = "npx.cmd" if os.name == "nt" else "npx"
    r = subprocess.run(
        [npx, "remotion", "render", "src/index.tsx", "ExplainerVertical", out_mp4,
         "--props", props_path, "--crf", "17", "--concurrency", "4",
         "--log", "error"],
        cwd=REMOTION, capture_output=True, text=True, timeout=3600,
    )
    if r.returncode != 0:
        raise RuntimeError(f"remotion render failed: {r.stderr[-600:]}")

    # 8 master pass (loudness + encode)
    master = subprocess.run(
        ["ffmpeg", "-y", "-i", out_mp4, "-map", "0:v", "-map", "0:a",
         "-c:v", "libx264", "-crf", "17", "-preset", "medium",
         "-af", "loudnorm=I=-13:TP=-1.5:LRA=11:print_format=json",
         "-c:a", "aac", "-b:a", "192k", "-ar", "44100", out_mp4 + ".master.mp4"],
        capture_output=True, text=True, timeout=900,
    )
    if master.returncode != 0:
        print(f"[warn] loudnorm pass failed, keeping render as-is: {master.stderr[-200:]}")
    elif os.path.exists(out_mp4 + ".master.mp4"):
        os.replace(out_mp4 + ".master.mp4", out_mp4)

    # 9 probe
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height",
         "-show_entries", "format=duration", "-of", "json", out_mp4],
        capture_output=True, text=True, timeout=60,
    )
    try:
        pdata = json.loads(probe.stdout)
        streams = pdata.get("streams", [])
        has_video = any(s.get("codec_type") == "video" and s.get("codec_name") == "h264"
                        and s.get("width") == 1080 and s.get("height") == 1920 for s in streams)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        probe_ok = bool(has_video and has_audio)
    except Exception:
        probe_ok = False

    # 10 viewer-experience QC
    qc_report = qc_mod.qc_viewer(job, job["shots"], dict(zip([s["id"] for s in job["shots"]], ins)),
                                 outs, caption_final, stats, style)

    # 10b V2.1 video-first QC (spec lives in v21.py; qc.py untouched)
    import v21
    v21_report = v21.check_v21(job, job["shots"],
                               dict(zip([s["id"] for s in job["shots"]], ins)),
                               outs, caption_final, sfx_events)

    return {
        "job": job, "output": out_mp4, "duration": round(video_end, 2),
        "size_mb": round(os.path.getsize(out_mp4) / 1048576, 1), "probe_ok": probe_ok,
        "align_engine": align_engine, "tts_engine": "edge-tts/piper",
        "n_shots": len(cuts), "n_caption_words": len(caption_final),
        "qc": qc_report, "v21": v21_report,
    }


def render_job(job_path: str, dry: bool = False) -> dict:
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)
    out_mp4 = os.path.join(ROOT, "out", job["date"], f"short_{job['index']}.mp4")
    return _render_job_internal(job_path, out_mp4, dry=dry)