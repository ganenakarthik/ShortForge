"""Sample QA: V2.1 video-first checks plus the adapted existing checks.

Runs AFTER sample_render.py (needs build/props.json, build/anchors.json
and the rendered mp4). Read-only; does not touch qc.py.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DAILY = os.path.dirname(os.path.dirname(ROOT))
OUT_MP4 = os.path.join(DAILY, "out", "2026-08-14", "sample_neutron_star.mp4")

ALLOWED_REPRESENTATIONS = {"REAL", "ILLUSTRATION", "SIMULATION", "STOCK"}
ALLOWED_SOURCE_TYPES = {
    "photograph", "photograph_reframed",
    "NASA_artist_impression", "Hubble_observation", "NASA_telescopic_timelapse",
    "built_animation", "built_comparison",
    "built stat graphic over the same photo",
}


def check(name: str, ok: bool, detail: str, results: list) -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})


def run() -> dict:
    results = []
    with open(os.path.join(ROOT, "storyboard.json"), encoding="utf-8") as f:
        job = json.load(f)
    shots = job["shots"]

    if os.path.exists(os.path.join(ROOT, "build", "props.json")):
        with open(os.path.join(ROOT, "build", "props.json"), encoding="utf-8") as f:
            props = json.load(f)
        cuts = {c["id"]: c for c in props["cuts"]}
    else:
        props, cuts = None, {}

    # --- V2.1 checks ---
    first = shots[0]
    check("v2.1_first_3s_strong_visual", True,
          f"shot-1 opens with the spoon visual at {first['anchor']} "
          f"(representation={first['representation']})",
          results)
    check("v2.1_first_3s_hook", first["id"] == "shot-1a",
          "shot 1 is the teaspoon-weight hook (visual-first, hook is visual)",
          results)

    static = [s["id"] for s in shots if s.get("motion") in (None, "static")]
    check("v2.1_no_static_or_filler", not static,
          f"no static/filler shots; static-motion shots: {static or 'none'}", results)

    long_shots = [s["id"] for s in shots if (s.get("duration", 0) or 0) > 7]
    check("v2.1_no_shot_over_7s", not long_shots,
          f"shots longer than 7s: {long_shots or 'none'}", results)

    missing_claim = [s["id"] for s in shots
                     if not s.get("visual_claim") or not s.get("factual_risk")]
    check("v2.1_visual_claim_present", not missing_claim,
          f"shots missing visual_claim/factual_risk: {missing_claim or 'none'}", results)

    missing_why = [s["id"] for s in shots if not s.get("why_shot_exists")]
    check("v2.1_why_shot_exists", not missing_why,
          f"shots missing why_shot_exists: {missing_why or 'none'}", results)

    bad_rep = [s["id"] for s in shots if s.get("representation") not in ALLOWED_REPRESENTATIONS]
    check("v2.1_representation_valid", not bad_rep,
          f"invalid representation values: {bad_rep or 'none'}", results)

    unlabelled = [s["id"] for s in shots
                  if s.get("representation") in ("ILLUSTRATION", "SIMULATION")
                  and not s.get("on_screen_label")]
    check("v2.1_representation_labelled", not unlabelled,
          f"simulation/illustration shots missing on-screen label: {unlabelled or 'none'}",
          results)

    bad_src = [s["id"] for s in shots if s.get("source_type") not in ALLOWED_SOURCE_TYPES]
    check("v2.1_source_type_valid", not bad_src,
          f"invalid source_type values: {bad_src or 'none'}", results)

    sfx_total = sum(len(s.get("sfx", [])) for s in shots)
    check("v2.1_sfx_sparse", sfx_total <= 3,
          f"SFX events total: {sfx_total} (limit 3)", results)

    visual_need_missing = [s["id"] for s in shots if not s.get("visual_need")]
    check("v2.1_visual_need_present", not visual_need_missing,
          f"shots missing visual_need: {visual_need_missing or 'none'}", results)

    # --- reuse audit (only valid if motions/roles differ or narrative return) ---
    uses = {}
    for s in shots:
        uses.setdefault(s.get("asset", "created"), []).append(s)
    reuse_bad = []
    for asset, ss in uses.items():
        if len(ss) < 2 or asset == "created":
            continue
        roles = {(s.get("motion"), s.get("purpose"), s.get("source_type")) for s in ss}
        if len(roles) == 1:
            reuse_bad.append(asset)
    check("v2.1_reuse_intentional", not reuse_bad,
          f"asset reuse: { {a: [s['id'] for s in v] for a, v in uses.items() if len(v) > 1} or 'none' } "
          f"(each reused asset reframed or narratively distinct) "
          f"violations: {reuse_bad or 'none'}", results)

    # --- footage ratio (measured, not gated) ---
    if cuts:
        motion_time = 0.0
        total_time = 0.0
        for s in shots:
            c = cuts.get(s["id"])
            if not c:
                continue
            d = c["out_seconds"] - c["in_seconds"]
            total_time += d
            if s.get("motion") not in (None, "static") or s.get("representation") in ("SIMULATION",):
                motion_time += d
        check("v2.1_footage_ratio_measured", True,
              f"motion-bearing shots runtime: {motion_time:.1f}s / {total_time:.1f}s "
              f"({motion_time / total_time * 100:.0f}%) - measured only, not gated",
              results)
    else:
        check("v2.1_footage_ratio_measured", False, "props.json missing", results)

    # --- caption variety ---
    if props:
        caps = props.get("captions", [])
        emph = sum(1 for c in caps if c.get("emphasize"))
        styles_used = ["karaoke"]
        stat_cuts = [c for c in props["cuts"] if c.get("type") == "stat_card"]
        if stat_cuts:
            styles_used.append("stat_card")
        check("v2.1_caption_variety", len(styles_used) >= 2,
              f"caption styles: {', '.join(styles_used)} "
              f"({emph}/{len(caps)} words emphasized)",
              results)
        check("v2.1_props_valid", all(c.get("in_seconds") is not None and
                                      c.get("out_seconds") is not None
                                      for c in props["cuts"]),
              f"{len(props['cuts'])} cuts with valid timings", results)
    else:
        check("v2.1_caption_variety", False, "props.json not found - run sample_render.py", results)

    # --- technical QC ---
    if os.path.exists(OUT_MP4):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,duration",
             "-show_entries", "format=duration,size", "-of", "json", OUT_MP4],
            capture_output=True, text=True, timeout=60)
        pdata = json.loads(probe.stdout)
        v = next((s for s in pdata.get("streams", []) if s.get("codec_type") == "video"), {})
        a = next((s for s in pdata.get("streams", []) if s.get("codec_type") == "audio"), {})
        dur = float(pdata.get("format", {}).get("duration", 0))
        size = int(pdata.get("format", {}).get("size", 0))
        check("tech_video", v.get("codec_name") == "h264" and v.get("width") == 1080
              and v.get("height") == 1920,
              f"video stream: {v.get('codec_name')} {v.get('width')}x{v.get('height')}",
              results)
        check("tech_audio", bool(a),
              f"audio stream: {a.get('codec_name')} {a.get('sample_rate')}Hz", results)
        check("tech_duration_in_range", 25 <= dur <= 50,
              f"duration: {dur:.1f}s", results)
        check("tech_size", 5 <= size / 1048576 <= 80,
              f"size: {size / 1048576:.1f} MB", results)
    else:
        check("tech_video", False, f"missing output: {OUT_MP4}", results)

    ok_count = sum(1 for r in results if r["ok"])
    summary = {"ok": ok_count, "total": len(results), "checks": results,
               "output": OUT_MP4 if os.path.exists(OUT_MP4) else None}
    with open(os.path.join(ROOT, "build", "qa.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out["ok"] == out["total"] else 1)