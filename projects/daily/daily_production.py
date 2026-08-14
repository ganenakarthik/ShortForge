"""Daily production V2-A: storyboard-first Shorts, news-free.

Run:  python projects/daily/daily_production.py [--count 2] [--date YYYY-MM-DD]
Each run: pick fact playbooks (deterministic via date seed) -> Director builds
a storyboard (hook -> beats -> shots with purposes/motion/sfx) -> render ->
viewer-experience QC -> append to publish queue (upload staged, never auto).

V2-A scope: local samples only. Scheduler stays disabled while testing.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from director import direct, load_playbook  # noqa: E402
from render_job import render_job  # noqa: E402
import v21  # noqa: E402
import news_playbook  # noqa: E402

PLAYBOOKS_DIR = os.path.join(ROOT, "playbooks")


def description_for(job: dict) -> str:
    playbook_desc = job["description"]
    lines = [
        playbook_desc + " \u2014 30-second story, every claim sourced below.",
        "",
        "Key claims (with sources):",
    ]
    for f_ in job.get("facts", []):
        lines.append(f"- {f_['claim']} \u2014 {f_['source_name']} ({f_['source_url']})")
    lines += ["", "Made fully local: Edge TTS + Remotion + ffmpeg. Zero cloud \u2014 zero cost.",
              " ".join(job.get("hashtags", []))]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--news", type=int, default=2,
                    help="how many of the daily slots are fresh news (rest = fact playbooks)")
    ap.add_argument("--date", default="2026-08-13")
    ap.add_argument("--only", help="comma-separated playbook ids to force (testing)")
    args = ap.parse_args()

    date_str = args.date
    seed = int(date_str.replace("-", ""))
    out_root = os.path.join(ROOT, "out", date_str)
    os.makedirs(out_root, exist_ok=True)
    jobs_dir = os.path.join(ROOT, "queue", "jobs")
    os.makedirs(jobs_dir, exist_ok=True)

    playbook_files = sorted(p for p in os.listdir(PLAYBOOKS_DIR) if p.endswith(".json"))
    playbooks = [json.load(open(os.path.join(PLAYBOOKS_DIR, p), encoding="utf-8")) for p in playbook_files]
    if not playbooks:
        print("[daily] no playbooks found"); return 1
    by_id = {p["id"]: p for p in playbooks}

    forced = [x.strip() for x in args.only.split(",")] if args.only else []
    if forced:
        missing = [f for f in forced if f not in by_id]
        if missing:
            print(f"[daily] unknown playbooks: {missing}"); return 1
        picks = [by_id[f] for f in forced[: args.count]]
    else:
        # Fresh news playbooks first (always pass the topic gate — they are
        # fresh by definition), then seeded fact-playbook rotation.
        news_ids = []
        try:
            news_ids = news_playbook.produce(args.news)
            news_ids = [os.path.basename(p)[:-5] for p in news_ids]
        except Exception as exc:
            print(f"[daily] news fetch failed ({exc}); using fact playbooks for news slots")
        for nid in news_ids:
            by_id.setdefault(nid, load_playbook(nid))

        picks = [by_id[nid] for nid in news_ids if nid in by_id][: args.news]
        used = [nid for nid in news_ids if nid in by_id]

        # V2.1 topic scoring gate: only produce topics that pass the bar
        scored = []
        for p in playbooks:
            s = v21.score_topic(p)
            if s["pass"]:
                scored.append((s["score"], p))
            else:
                print(f"[daily] topic skip (score {s['score']} < {v21.TOPIC_THRESHOLD}): "
                      f"{p['id']} — {', '.join(s['reasons'])}")
        scored.sort(key=lambda x: (-x[0], x[1]["id"]))
        while len(picks) < args.count:
            available = [p for _, p in scored if p["id"] not in used] or [p for _, p in scored]
            if not available:
                break
            pb = available[(seed + len(picks)) % len(available)]
            used.append(pb["id"])
            picks.append(pb)

    entries = []
    for i, pb in enumerate(picks):
        job = direct(pb, date_str, i + 1, seed)
        job_path = os.path.join(jobs_dir, f"{date_str}_{i + 1}.json")
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)

        out_mp4 = os.path.join(out_root, f"short_{i + 1}.mp4")
        if os.path.exists(out_mp4):
            print(f"[daily] job {i + 1}: output exists, reusing {out_mp4}")
            result = {"output": out_mp4, "duration": None, "size_mb": round(os.path.getsize(out_mp4) / 1048576, 1),
                      "probe_ok": None, "n_shots": len(job["shots"])}
        else:
            try:
                result = render_job(job_path)
            except Exception as exc:
                print(f"[daily] job {i + 1} FAILED: {exc}")
                continue
        qc = result.get("qc") or {}
        v21r = result.get("v21") or {}
        print(f"[daily] job {i + 1} -> {result['output']} "
              f"({result.get('duration')}s, {result.get('size_mb')}MB, probe_ok={result.get('probe_ok')}, "
              f"shots={result.get('n_shots')}, align={result.get('align_engine')}, "
              f"qc={qc.get('score')}% ({qc.get('passed')}/{qc.get('total')}), "
              f"v21={v21r.get('score')}% ({v21r.get('passed')}/{v21r.get('total')}))")
        if qc.get("fails"):
            print(f"[daily]   QC FAILS: {qc['fails']}")
        if v21r.get("fails"):
            print(f"[daily]   V2.1 FAILS: {v21r['fails']}")

        if v21r.get("fails"):
            print(f"[daily]   job {i + 1} NOT queued — V2.1 gate failed, human review required")
            continue

        entries.append({
            "date": date_str, "index": i + 1, "status": "ready",
            "file": os.path.relpath(result["output"], os.path.join(ROOT, "..", "..")),
            "title": job["title"],
            "description": description_for(job),
            "theme": job["theme"], "playbook": pb["id"],
            "story": {"style": job.get("style", {}).get("music"),
                      "shots": [s["purpose"] for s in job["shots"]]},
            "qc_score": qc.get("score"),
            "v21_score": v21r.get("score"),
        })

    queue_path = os.path.join(ROOT, "queue", "publish_queue.json")
    queue = []
    if os.path.exists(queue_path):
        queue = json.load(open(queue_path, encoding="utf-8"))
    new_ids = {(e["date"], e["index"]) for e in entries}
    queue = [e for e in queue if (e.get("date"), e.get("index")) not in new_ids]
    queue.extend(entries)
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)
    print(f"[daily] queue now has {len(queue)} entries")
    return 0 if entries else 1


if __name__ == "__main__":
    sys.exit(main())