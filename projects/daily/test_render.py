import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import director
import render_job

pid = sys.argv[1] if len(sys.argv) > 1 else "misconception-brain"
date_str = sys.argv[2] if len(sys.argv) > 2 else "2026-08-16"

pb = director.load_playbook(pid)
job = director.direct(pb, date_str, 9, 20260816)
job_path = os.path.join(ROOT, "tmp", f"test_{pid}.json")
with open(job_path, "w", encoding="utf-8") as f:
    json.dump(job, f, indent=2)
print(f"job written: {job_path} ({len(job['shots'])} shots)")
r = render_job.render_job(job_path)
print(json.dumps({"output": r["output"], "duration": r["duration"],
                  "n_shots": r["n_shots"], "n_caption_words": r["n_caption_words"],
                  "qc": r["qc"], "v21": r["v21"]}, indent=2))