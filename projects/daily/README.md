# Daily Shorts Pipeline

Fully automated YouTube Shorts production: fresh news + curated facts → sourced, narrated, quality-gated vertical videos → public upload → storage cleanup.

## How a day runs

```
09:00 (Windows Task Scheduler: run_daily.ps1)
  │
  ├─ news_playbook.py     2 fresh tech items (Hacker News + Google News)
  │                        → article text webfetched → claims = real sentences
  │                        → playbook per item (video beat, sourced facts)
  │
  ├─ daily_production.py  3 videos: 2 news-driven + 1 rotating fact playbook
  │   │                     topic scoring gate (threshold 5.0)
  │   ├─ director.py       shot list: hook, beats, narration, captions, SFX ≤ 3
  │   ├─ sources.py        Commons video/image beats (license-safe, ≤45 s clips)
  │   ├─ tts + whisper     narration + word-level caption alignment
  │   ├─ render_job.py     Remotion render 1080×1920 + loudnorm −13 LUFS master
  │   └─ QC + V2.1 gates   only passing videos enter the publish queue
  │
  ├─ upload_youtube.py     resumable upload (public), deletes local mp4 + assets
  │
  └─ retries every 5 min until 23:30 if anything transient fails
```

## Setup

1. **Python deps** — `pip install -r requirements.txt` (in the repo venv).

2. **YouTube** (one-time, ~10 min):
   - [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → OAuth client ID → **Desktop app** → download JSON
   - Save it as `projects/daily/client_secret.json`
   - Enable **YouTube Data API v3**
   - Run `python upload_youtube.py` once → browser consent (full `youtube` scope, needed for privacy flips too)

3. **Schedule** (example, Windows):
   ```powershell
   $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
     -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\path\to\run_daily.ps1"
   $trigger = New-ScheduledTaskTrigger -Daily -At 09:00
   $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
   Register-ScheduledTask -TaskName "DailyShorts" -Action $action -Trigger $trigger -Settings $settings
   ```
   `StartWhenAvailable` catches up the run if the PC was off at trigger time.

## Commands

```bash
python news_playbook.py 2                            # today's news playbooks (slot 1..N)
python daily_production.py --count 3 --news 2        # render today's 3 Shorts + gate + queue
python daily_production.py --date 2026-08-14         # specific date (deterministic)
python upload_youtube.py                             # upload queued "ready" entries
python upload_youtube.py --publish                   # flip uploaded videos to public
python upload_youtube.py --entry 2                   # upload only entry 2
```

## Content integrity rules

- **Never fabricate.** Claims are article sentences or the headline (when a site blocks fetching — noted honestly in the video), each with its source URL in tier-2 facts.
- **License-safe footage only.** Commons results are filtered to Public domain / No restrictions / CC0 / CC BY / CC BY-SA (NC/ND rejected), ≥1000×700 for images, and provenance (license + URL) is recorded on every shot.
- **Quality gates are binding.** A video that fails QC or V2.1 never reaches the queue.
- **No secrets in the repo.** `client_secret.json`, `queue/`, `out/`, `tmp/` and runtime playbooks are gitignored.

## Layout

| File | Role |
|---|---|
| `news.py` | Hacker News + Google News fetchers (keyless; HN query-less fetch, GN interstitial detection) |
| `news_playbook.py` | news item → sourced playbook (article webfetch, claim extraction, video-beat query from headline) |
| `sources.py` | Commons search / license+size filters / relevance ranking / download / h264 transcode (45 s cap) |
| `director.py` | playbook → shots: hooks, beats, visual claims, SFX budget, emphasis words |
| `v21.py` | V2.1 checks: topic gate, no-filler, first-3-s, labels, provenance, caption variety |
| `qc.py` | render QC: probe, duration, alignment, captions, footage ratio |
| `render_job.py` | props build, asset staging, Remotion render, loudnorm master, results |
| `daily_production.py` | orchestrator: playbook selection (news first, then fact rotation), gates, queue |
| `upload_youtube.py` | resumable upload, `--publish` privacy flips, post-upload deletion + sweep |
| `run_daily.ps1` | scheduled end-to-end runner (public privacy, retries until 23:30) |
| `playbooks/` | curated fact playbooks (e.g. koala-fingerprints.json with video beats) |