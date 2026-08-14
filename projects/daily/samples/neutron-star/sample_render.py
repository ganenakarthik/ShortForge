"""Sample 1 render driver: neutron-star-teaspoon.

Sample-only. Reuses the existing modules (tts_engine, align, audio_design, qc)
and the ExplainerVertical composition; does NOT change the daily pipeline.

Storyboard-driven with the approved V2.1 fields (visual_need, representation,
source_type, source_label, visual_claim, why_shot_exists).
"""
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DAILY = os.path.dirname(os.path.dirname(ROOT))     # projects/daily
OPENMONTAGE = os.path.normpath(os.path.join(ROOT, "..", "..", "..", ".."))
REMOTION = os.path.join(OPENMONTAGE, "remotion-composer")
SAMPLE_DIR = os.path.join(REMOTION, "public", "daily-sample-1")
ASSETS = os.path.join(ROOT, "assets")
BUILD = os.path.join(ROOT, "build")
OUT_DIR = os.path.join(DAILY, "out", "2026-08-14")
OUT_MP4 = os.path.join(OUT_DIR, "sample_neutron_star.mp4")

sys.path.insert(0, DAILY)
import tts_engine    # noqa: E402
import align         # noqa: E402
import audio_design as ad  # noqa: E402
import qc as qc_mod  # noqa: E402

GAP = 0.16
TAIL = 0.9
VOICE = 0            # en-US-ChristopherNeural for the whole sample (one voice)


def _wav_duration(path: str) -> float:
    import wave
    with wave.open(path, "rb") as w:
        return round(w.getnframes() / w.getframerate(), 3)


def synthesize(job: dict) -> tuple[dict, dict, dict, float]:
    durations, starts, ends = {}, {}, {}
    t = 0.0
    for i, seg in enumerate(job["narration"]):
        wav = os.path.join(ASSETS, f"{seg['id']}.wav")
        dur = tts_engine.synthesize(seg["text"], wav, VOICE)
        durations[seg["id"]] = dur
        starts[seg["id"]] = t
        ends[seg["id"]] = t + dur
        t = ends[seg["id"]] + GAP
    total = t - GAP
    return durations, starts, ends, total


def build_captions(job: dict, durations: dict, starts: dict, ends: dict, narration_wav: str):
    segments = [dict(s, _start=starts[s["id"]], _end=ends[s["id"]]) for s in job["narration"]]
    seg_words, engine = align.align_words(segments, durations, starts, narration_wav)

    emph_sets = {
        "n1": {"billion", "tons"},
        "n2": {"neutron", "star"},
        "n3": {"twenty"},
        "n4": {"second"},
        "n5": {"supernova", "collapsing"},
        "n6": {"two", "city"},
        "n7": {"neutrons"},
        "n8": {"billion"},
    }
    caps = []
    for sg in seg_words:
        for w in sg["words"]:
            if w["text"] == "\u200b":
                continue
            caps.append({
                "word": w["text"],
                "startMs": round(w["start"] * 1000),
                "endMs": round(w["end"] * 1000),
                "emphasize": w["text"].lower().strip(".,!?") in emph_sets.get(sg["id"], set()),
            })
    caps.sort(key=lambda c: c["startMs"])
    for i in range(1, len(caps)):
        prev_end = caps[i - 1]["endMs"]
        if caps[i]["startMs"] < prev_end:
            caps[i]["startMs"] = prev_end
        if caps[i]["endMs"] <= caps[i]["startMs"]:
            caps[i]["endMs"] = caps[i]["startMs"] + 30
    return caps, engine


def resolve_shots(job: dict, starts: dict, ends: dict, video_end: float):
    def anchor_time(shot: dict) -> float:
        a = shot.get("anchor", {})
        sid = a.get("narration") or shot.get("narration")
        s0 = starts.get(sid, 0.0)
        s1 = ends.get(sid, s0 + 2.0)
        at = a.get("at", "start")
        if at == "end":
            return s1
        if at == "fraction":
            f = float(a.get("fraction", 0.5))
            return s0 + (s1 - s0) * max(0.05, min(0.95, f))
        return s0

    shots = job["shots"]
    ins = [anchor_time(s) for s in shots]
    outs = {}
    for i, s in enumerate(shots):
        nxt = ins[i + 1] if i + 1 < len(shots) else video_end
        outs[s["id"]] = max(ins[i] + 0.9, nxt - 0.02) if nxt > ins[i] + 0.9 else nxt
    return ins, outs


def build_sfx_bed(job: dict, ins: list, outs: dict, starts: dict, ends: dict, video_end: float) -> str:
    events = []
    for i, s in enumerate(job["shots"]):
        for fx in s.get("sfx", []):
            t_ = ins[i] if fx.get("at", "start") == "start" else outs[s["id"]]
            events.append({"type": fx["type"], "in_seconds": round(t_, 3),
                           "duration": 0.6, "seed": 900 + i,
                           "volume": fx.get("volume", 0.7)})
    n = int(ad.SR * (video_end + 0.5))
    silence = np.zeros(n)
    windows = [(starts[s["id"]], ends[s["id"]] + 0.05) for s in job["narration"]]
    out_wav = os.path.join(ASSETS, "sfx_bed.wav")
    ad.mix_music(silence, events, windows, out_wav)
    return out_wav


def build_props(job: dict, ins: list, outs: dict, caps: list, video_end: float):
    p = "daily-sample-1"
    cuts = []
    for i, s in enumerate(job["shots"]):
        cut = {
            "id": s["id"],
            "in_seconds": round(ins[i], 2),
            "out_seconds": round(outs[s["id"]], 2),
            "motion": None,
            "transition_in": s.get("transition_in", "cut"),
            "transition_out": "fade",
            "transitionOutDuration": 0.25,
        }
        if s["id"] in ("shot-1b", "shot-8"):
            cut["type"] = "stat_card"
            cut["stat"], cut["subtitle"] = s["overlay_text"], ""
            cut["backgroundImage"] = f"{p}/spoon_crop.jpg" if s["id"] == "shot-8" else f"{p}/spoon_full.jpg"
            cut["backgroundOverlay"] = 0.62 if s["id"] == "shot-1b" else 0.5
            cut["accentColor"] = "#FBBF24" if s["id"] == "shot-1b" else "#38BDF8"
            cut["motion"] = {"type": s.get("motion", "pop_up")}
        elif s["id"] == "shot-4":
            cut["type"] = "anime_scene"
            cut["images"] = [f"{p}/collapse_{k}.png" for k in (1, 2, 3)]
            cut["animation"] = "ken-burns"
            cut["vignette"] = False
        elif s["id"] == "shot-7":
            cut["type"] = "anime_scene"
            cut["images"] = [f"{p}/neutron_sea_{k}.png" for k in (1, 2)]
            cut["animation"] = "ken-burns"
            cut["vignette"] = False
        elif s["id"] == "shot-5":
            cut["source"] = f"{p}/crab_timelapse.mp4"
            cut["source_in_seconds"] = 4.0
            cut["motion"] = {"type": s.get("motion", "zoom_out")}
        else:
            cut["source"] = f"{p}/{s['asset']}"
            cut["motion"] = {"type": s.get("motion", "punch_in")}
        cuts.append(cut)

    props = {
        "theme": job["theme"]["name"],
        "themeConfig": job["theme"]["themeConfig"],
        "cuts": cuts,
        "overlays": [],
        "captions": caps,
        "audio": {
            "narration": {"src": f"{p}/narration.wav", "volume": 1.0},
            "music": {"src": f"{p}/sfx_bed.wav", "volume": 1.0,
                      "fadeInSeconds": 0.2, "fadeOutSeconds": 0.5},
        },
        "avatar": {"enabled": False},
    }
    props_path = os.path.join(BUILD, "props.json")
    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f, indent=2)
    return props_path


def stage_assets(job: dict, narration_wav: str, sfx_wav: str) -> None:
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    names = {s["asset"] for s in job["shots"]}
    for name in list(names):
        src = os.path.join(ASSETS, name)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(SAMPLE_DIR, name))
    for f in ("collapse_1.png", "collapse_2.png", "collapse_3.png",
              "neutron_sea_1.png", "neutron_sea_2.png"):
        shutil.copyfile(os.path.join(ASSETS, f), os.path.join(SAMPLE_DIR, f))
    shutil.copyfile(narration_wav, os.path.join(SAMPLE_DIR, "narration.wav"))
    shutil.copyfile(sfx_wav, os.path.join(SAMPLE_DIR, "sfx_bed.wav"))


def main(dry: bool = False) -> dict:
    with open(os.path.join(ROOT, "storyboard.json"), encoding="utf-8") as f:
        job = json.load(f)

    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    durations, starts, ends, total = synthesize(job)
    narration_wav = os.path.join(ASSETS, "narration.wav")
    tts_engine.concatenate([(os.path.join(ASSETS, f"{s['id']}.wav"), durations[s["id"]])
                            for s in job["narration"]], narration_wav, gap=GAP)
    video_end = round(total + TAIL + 0.35, 2)

    caps, align_engine = build_captions(job, durations, starts, ends, narration_wav)
    ins, outs = resolve_shots(job, starts, ends, video_end)
    sfx_wav = build_sfx_bed(job, ins, outs, starts, ends, video_end)
    props_path = build_props(job, ins, outs, caps, video_end)
    stage_assets(job, narration_wav, sfx_wav)

    print(json.dumps({
        "video_end": video_end,
        "narration_total": round(total, 2),
        "shots": [{"id": s["id"], "in": round(ins[i], 2), "out": round(outs[s["id"]], 2),
                   "dur": round(outs[s["id"]] - ins[i], 2)} for i, s in enumerate(job["shots"])],
        "captions": len(caps),
        "align_engine": align_engine,
    }, indent=2))

    if dry:
        return {"dry": True, "video_end": video_end, "props": props_path}

    npx = "npx.cmd" if os.name == "nt" else "npx"
    r = subprocess.run(
        [npx, "remotion", "render", "src/index.tsx", "ExplainerVertical", OUT_MP4,
         "--props", props_path, "--crf", "17", "--concurrency", "4", "--log", "error"],
        cwd=REMOTION, capture_output=True, text=True, timeout=3600,
    )
    if r.returncode != 0:
        raise RuntimeError(f"remotion render failed: {r.stderr[-800:]}")

    master = subprocess.run(
        ["ffmpeg", "-y", "-i", OUT_MP4, "-map", "0:v", "-map", "0:a",
         "-c:v", "libx264", "-crf", "17", "-preset", "medium",
         "-af", "loudnorm=I=-13:TP=-1.5:LRA=11:print_format=json",
         "-c:a", "aac", "-b:a", "192k", "-ar", "44100", OUT_MP4 + ".master.mp4"],
        capture_output=True, text=True, timeout=900,
    )
    if master.returncode != 0:
        print(f"[warn] loudnorm pass failed: {master.stderr[-200:]}")
    elif os.path.exists(OUT_MP4 + ".master.mp4"):
        os.replace(OUT_MP4 + ".master.mp4", OUT_MP4)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height",
         "-show_entries", "format=duration", "-of", "json", OUT_MP4],
        capture_output=True, text=True, timeout=60,
    )
    try:
        pdata = json.loads(probe.stdout)
        streams = pdata.get("streams", [])
        has_video = any(s.get("codec_type") == "video" and s.get("codec_name") == "h264"
                        and s.get("width") == 1080 and s.get("height") == 1920 for s in streams)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        probe_ok = bool(has_video and has_audio)
        duration = round(float(pdata.get("format", {}).get("duration", 0)), 2)
    except Exception:
        probe_ok, duration = False, 0.0

    return {
        "output": OUT_MP4,
        "duration": duration,
        "size_mb": round(os.path.getsize(OUT_MP4) / 1048576, 1),
        "probe_ok": probe_ok,
        "video_end_planned": video_end,
        "align_engine": align_engine,
        "tts_engine": "edge-tts (Christopher)",
        "n_shots": len(job["shots"]),
        "n_caption_words": len(caps),
    }


if __name__ == "__main__":
    dry_run = "--dry" in sys.argv
    result = main(dry=dry_run)
    print(json.dumps(result, indent=2))
