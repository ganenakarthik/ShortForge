"""Voice engine: Edge TTS primary, Piper lessac-high offline fallback.

Synthesizes spoken-style narration per segment. Returns (wav_path, seconds).
Edge TTS produces natural prosody; Piper (local, free) covers offline runs.

Honest status: Edge TTS needs internet (Microsoft endpoint). Piper is always
available once the voice file exists. Voice caching keyed by text hash so
re-renders never re-synthesize.
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import wave

import edge_tts

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "tmp", "assets")
VOICE_DIR = r"C:\Users\ganen\piper-voices"
PIPER_EXE = os.path.join(ROOT, "..", "..", ".venv", "Scripts", "piper.exe")
FFMPEG = "ffmpeg"

EDGE_VOICES = ["en-US-ChristopherNeural", "en-US-GuyNeural", "en-GB-RyanNeural"]
EDGE_RATE = "+10%"
EDGE_PITCH = "+0Hz"

PIPER_FALLBACKS = [
    os.path.join(VOICE_DIR, "en_US-lessac-high.onnx"),
    os.path.join(VOICE_DIR, "en_US-lessac-medium.onnx"),
]


def _wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return round(w.getnframes() / w.getframerate(), 3)


def _edge_tts_sync(text: str, out_mp3: str, voice: str) -> None:
    async def _go():
        tts = edge_tts.Communicate(text, voice, rate=EDGE_RATE, pitch=EDGE_PITCH)
        await tts.save(out_mp3)
    asyncio.run(_go())


def _mp3_to_wav(mp3: str, wav: str) -> None:
    r = subprocess.run(
        [FFMPEG, "-y", "-i", mp3, "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", wav],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg mp3->wav failed: {r.stderr[-300:]}")


def _piper_sync(text: str, wav: str, model: str) -> None:
    r = subprocess.run(
        [PIPER_EXE, "--model", model, "--length-scale", "1.05",
         "--sentence-silence", "0.25", "--output_file", wav, "--data-dir", VOICE_DIR],
        input=text, capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"piper failed: {r.stderr[-300:]}")


def synthesize(text: str, out_wav: str, voice_index: int = 0, force: bool = False) -> float:
    """Synthesize one narration segment. Returns duration in seconds.

    The wav is cached by content: if a matching cached file exists for the
    same text + voice, it is reused regardless of the requested path.
    """
    cached = os.path.join(ASSETS, f"vo_{voice_index % len(EDGE_VOICES)}_{narration_cache_key(text)}.wav")
    if os.path.exists(cached) and not force:
        if os.path.abspath(cached) != os.path.abspath(out_wav):
            shutil.copyfile(cached, out_wav)
        return _wav_duration(out_wav)

    os.makedirs(os.path.dirname(out_wav) or ".", exist_ok=True)

    if not text.strip():
        raise ValueError("empty narration text")

    voice = EDGE_VOICES[voice_index % len(EDGE_VOICES)]
    used = "edge-tts"
    errors = []
    try:
        mp3 = out_wav + ".mp3"
        _edge_tts_sync(text, mp3, voice)
        _mp3_to_wav(mp3, out_wav)
        os.remove(mp3)
    except Exception as exc:  # network or endpoint failure -> piper fallback
        errors.append(f"edge-tts: {exc}")
        used = "piper"
        fallback_model = None
        for candidate in PIPER_FALLBACKS:
            if os.path.exists(candidate):
                fallback_model = candidate
                break
        if fallback_model is None:
            raise RuntimeError(f"edge-tts failed and no piper voice present: {exc}")
        try:
            _piper_sync(text, out_wav, fallback_model)
        except Exception as exc2:
            raise RuntimeError(f"edge-tts failed ({exc}) and piper failed ({exc2})")

    note_path = out_wav + ".voice.json"
    with open(note_path, "w", encoding="utf-8") as f:
        json.dump({"voice": voice if used == "edge-tts" else os.path.basename(fallback_model),
                   "engine": used}, f)
    cached_path = os.path.join(ASSETS, f"vo_{voice_index % len(EDGE_VOICES)}_{narration_cache_key(text)}.wav")
    if os.path.abspath(cached_path) != os.path.abspath(out_wav):
        shutil.copyfile(out_wav, cached_path)
    return _wav_duration(out_wav)


def narration_cache_key(text: str) -> str:
    return hashlib.sha256(f"{EDGE_RATE}|{EDGE_PITCH}|{text}".encode("utf-8")).hexdigest()[:16]


def concatenate(segments: list[tuple[str, float]], out_wav: str, gap: float = 0.12) -> float:
    """Concatenate segment wavs with a short breath gap. Returns total duration."""
    frame_rate = None
    out_frames = b""
    total = 0.0
    for wav_path, dur in segments:
        with wave.open(wav_path, "rb") as w:
            if frame_rate is None:
                frame_rate = w.getframerate()
            assert w.getframerate() == frame_rate
            out_frames += w.readframes(w.getnframes())
        if wav_path is not segments[-1][0]:
            out_frames += b"\x00" * int(frame_rate * gap) * 2
        total += dur + gap
    total -= gap
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(frame_rate)
        w.writeframes(out_frames)
    return round(total, 3)