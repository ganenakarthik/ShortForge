<p align="center">
  <img src="assets/monty-light.svg" alt="ShortForge" width="140">
</p>

<h1 align="center">ShortForge</h1>

<p align="center"><strong>Agentic video production — with a fully automated daily YouTube Shorts pipeline.</strong></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPLv3-blue.svg" alt="License"></a>
  <a href="#daily-pipeline"><img src="https://img.shields.io/badge/feature-Daily%20Auto%2DPublish-22c55e" alt="Daily auto-publish"></a>
  <a href="#architecture"><img src="https://img.shields.io/badge/stack-Remotion%20%E2%80%A2%20ffmpeg%20%E2%80%A2%20whisper-8b5cf6" alt="Stack"></a>
</p>

---

## Overview

ShortForge turns your AI coding assistant into a complete video production studio — research, scripting, asset sourcing, narration, editing, and composition — and then, if you want, **publishes new videos to YouTube every day with zero human interaction**.

Two layers:

| Layer | What it does |
|---|---|
| **Agentic framework** | Plain-language video production: pick a pipeline, and the agent drives every stage (research → script → scene plan → assets → edit → compose), with quality gates and human checkpoints |
| **Daily Shorts pipeline** | Production-grade automation: every morning it pulls fresh tech news + a rotating "nobody knows this" fact playbook, sources real footage from Wikimedia Commons (no API keys), renders three vertical Shorts, runs automated QC, and uploads them public to YouTube |

## Flagship feature: the daily pipeline

Runs fully unattended via a scheduled task (e.g. Windows Task Scheduler, 09:00 daily):

```
news (Hacker News + Google News)
  → sourced claims (article sentences only — never invented)
  → playbook (2 news items + 1 obscure-fact playbook)
  → director (shot list, narration, captions, SFX)
  → real footage beats (Commons video clips, license-filtered, transcoded h264)
  → Remotion render (1080×1920, loudnorm −13 LUFS)
  → QC + V2.1 checks (gate the publish queue)
  → YouTube upload (public) → local files deleted after upload
```

Highlights:

- **Sourced, honest content** — every claim is a sentence from the source article (or the headline when the site blocks bots); the source URL ships in the video metadata. No fabricated facts, ever.
- **Real video footage, not stills** — beats resolve to license-safe Commons clips (PD / CC0 / CC BY / CC BY-SA only), capped at 45 s and re-encoded for fast renders (a full day of 3 Shorts renders in ~7 minutes).
- **Quality gates** — per-shot purpose, visual claims, caption variety, SFX budget, first-3-seconds hook, provenance checks. Passing videos only.
- **Self-cleaning** — rendered files and staged assets are deleted from disk after upload (with retry + sweep for Windows file locks).
- **Keyless** — Wikimedia Commons search + local TTS/whisper/ffmpeg/Remotion. No paid APIs required.

See [`projects/daily/README.md`](projects/daily/README.md) for setup and operation.

## Quick start

```bash
# Production pipeline (agent-driven, human-approved)
python -c "from lib.checkpoint import init_project; init_project('my-project')"

# Daily Shorts automation
python projects/daily/news_playbook.py 2          # build today's news playbooks
python projects/daily/daily_production.py --count 3 --news 2
```

YouTube upload needs a one-time OAuth consent (browser) — after that it is fully automatic:

```bash
python projects/daily/upload_youtube.py
```

## Architecture

```
remotion-composer/   React scene library (Explainer, caption burn, corner labels)
projects/daily/      The daily automation pipeline
  ├─ news_playbook.py    fresh news → sourced playbook
  ├─ news.py             Hacker News + Google News fetchers (keyless)
  ├─ sources.py          Wikimedia Commons search/download/transcode (keyless)
  ├─ director.py         playbook → shot list (hooks, beats, SFX, captions)
  ├─ v21.py              V2.1 quality checks (topic gate, provenance, variety)
  ├─ qc.py               render QC (probe, alignment, captions)
  ├─ render_job.py       Remotion render + loudnorm master
  ├─ upload_youtube.py   resumable upload + privacy flips + storage cleanup
  ├─ run_daily.ps1       end-to-end runner with retries until 23:30
  └─ playbooks/          curated "nobody knows" fact playbooks
```

## Stack

Remotion (React) · ffmpeg · faster-whisper · edge-tts · Wikimedia Commons API · YouTube Data API v3

## License

[AGPL-3.0](LICENSE)

---

*Made by Rex*
