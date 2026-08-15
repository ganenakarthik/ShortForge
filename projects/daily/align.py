"""Word-level forced alignment via faster-whisper (local, CPU, free).

Whisper 'small' transcribes the narration and returns per-word timestamps.
Because the audio is clean TTS, alignment quality is high; the expected text
(initial_prompt) keeps transcription honest. If the model cannot run (no
cache, offline), we fall back to uniform per-word timing across each segment
and mark the captions as "estimated".

Output words are merged back onto the job's narration segments by order.
"""

import json
import os
import subprocess
import wave

MODEL = "small"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp", "assets")


def _to_16k(src_wav: str, out_wav: str) -> None:
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", src_wav, "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", out_wav],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 16k conversion failed: {r.stderr[-300:]}")


def _uniform_words(segments: list[dict], durations: dict[str, float], starts: dict[str, float]) -> list[dict]:
    """Fallback alignment: equal time per word inside each segment."""
    words = []
    for seg in segments:
        sid = seg["id"]
        text = seg["text"]
        toks = [t for t in text.split() if t]
        if not toks:
            continue
        dur = durations.get(sid, 1.0)
        step = dur / len(toks)
        base = starts.get(sid, 0.0)
        for i, t in enumerate(toks):
            words.append({
                "text": t.strip(".,?!\u2014;:'\""), "start": base + i * step,
                "end": base + (i + 1) * step, "estimated": True,
            })
    return words


def _norm(tok: str) -> str:
    return tok.strip(".,?!\u2014;:'\"\u201c\u201d()[]").lower()


def _words_to_segments(words: list[dict], segments: list[dict]) -> list[dict]:
    """Rebuild per-segment word lists from the flat aligned sequence.

    Each word is assigned to the segment that contains its midpoint. Whisper
    can mis-hear, merge, or duplicate words, so we map the EXPECTED narration
    tokens onto the whisper times with a greedy ORDERED match (subsequence):
    - whisper-inserted tokens (not in the expected text) are skipped,
    - expected tokens whisper missed get estimated slots interpolated between
      the nearest known neighbours,
    so the caption text is ALWAYS the narration text in the right order.
    """
    outs = {s["id"]: [] for s in segments}
    bounds = [(seg["id"], seg.get("_start", 0.0), seg.get("_end", 1e9)) for seg in segments]

    for w in words:
        mid = (w["start"] + w["end"]) / 2
        for sid, s0, s1 in bounds:
            if s0 - 0.35 <= mid < s1 + 0.35:
                if not outs[sid] or outs[sid][-1]["start"] <= w["start"]:
                    outs[sid].append(w)
                break

    result = []
    for seg in segments:
        sid = seg["id"]
        expected = [t for t in seg["text"].split() if t]
        s0 = seg["_start"]
        s1 = seg["_end"]
        ow = outs[sid]

        # Greedy ordered match: walk the expected sequence, advancing through
        # whisper words only forward; consume a whisper word when its text
        # matches the current expected token.
        matched = []  # (expected_token, whisper_word_or_None)
        ai = 0
        for exp in expected:
            while ai < len(ow) and _norm(ow[ai]["text"]) != _norm(exp):
                ai += 1  # whisper-inserted word -> skip
            if ai < len(ow):
                matched.append((exp, ow[ai]))
                ai += 1
            else:
                matched.append((exp, None))

        # Interpolate estimated slots for the tokens whisper missed, using the
        # nearest known boundaries (neighbour times or segment edges).
        timings = {}
        for i, (exp, w) in enumerate(matched):
            if w is not None:
                timings[i] = (w["start"], w["end"])
        picked = []
        prev_end = None
        for i, (exp, w) in enumerate(matched):
            if w is not None:
                picked.append(w)
                prev_end = w["end"]
                continue
            nxt_start = next((timings[j][0] for j in range(i + 1, len(matched)) if j in timings), None)
            start = prev_end if prev_end is not None else s0
            end = nxt_start if nxt_start is not None else s1
            if end <= start:
                end = min(s1, start + max(0.12, (s1 - s0) / max(1, len(expected))))
            step = max(0.06, end - start)
            ew = {"text": exp, "start": start, "end": start + step, "estimated": True}
            picked.append(ew)
            prev_end = ew["end"]

        result.append({"id": sid, "text": seg["text"],
                       "start": s0, "end": s1, "words": picked})
    return result


def align_words(segments: list[dict], durations: dict[str, float], starts: dict[str, float],
                narration_wav: str) -> tuple[list[dict], str]:
    """Align narration words. Returns (per-segment word lists, engine used).

    segments: [{"id","text","_start","_end"}] with absolute times; durations
    and starts are the TTS-measured values (used for the fallback path).
    """
    wav16 = os.path.join(ASSETS, "align_16k.wav")
    _to_16k(narration_wav, wav16)

    expected_prompt = " ".join(s["text"] for s in segments).strip()
    words = []
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(MODEL, device="cpu", compute_type="int8")
        seg_iter, _info = model.transcribe(
            wav16, initial_prompt=expected_prompt,
            word_timestamps=True, condition_on_previous_text=False,
            vad_filter=False, language="en", beam_size=1,
        )
        for s in seg_iter:
            for w in s.words or []:
                words.append({"text": w.word.strip(), "start": w.start, "end": w.end, "estimated": False})
        engine = "faster-whisper"
    except Exception as exc:
        words = _uniform_words(segments, durations, starts)
        engine = f"uniform-fallback ({exc})"

    if not words:
        words = _uniform_words(segments, durations, starts)
        engine = "uniform-fallback (empty result)"

    result = _words_to_segments(words, segments)
    return result, engine


def captions_flat(seg_words: list[dict], gaps: dict[str, tuple[float, float]]) -> list[dict]:
    """Flatten per-segment words into a caption timeline (ms entries).

    Each segment's words get their real aligned times; a 60ms silence slot is
    inserted at segment boundaries so pages break naturally.
    """
    caps = []
    for sg in seg_words:
        for w in sg["words"]:
            caps.append({
                "word": w["text"],
                "startMs": round(w["start"] * 1000),
                "endMs": round(w["end"] * 1000),
                "estimated": w.get("estimated", False),
            })
        # small boundary gap so the caption card resets between beats
        gap_s = gaps.get(sg["id"], (0.0, 0.0))
        cap_end = max((c["endMs"] for c in caps if c["startMs"] < (gap_s[1] * 1000 + 1)), default=0)
        caps.append({"word": "\u200b", "startMs": cap_end, "endMs": round(gap_s[1] * 1000),
                     "estimated": False, "boundary": True})
    return [c for c in caps if c["startMs"] < c["endMs"]]