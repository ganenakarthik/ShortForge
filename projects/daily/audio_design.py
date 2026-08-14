"""Audio design: style-based generative music, SFX synthesis, narration ducking.

All synthesis is local and deterministic (seed-driven numpy), matching the
free/offline philosophy. The music bed is written first, then a sidechain
envelope derived from the aligned narration word timeline ducks the music
under the voice, then SFX hits are baked onto the same track. The final
track is normalized to a safe peak so the mix never clips.

Honest status: synthesized beds are musical but simple (chord pads + bass +
patterned drums). They are not human-composed; quality target is 'present but
unobtrusive', not 'chart hit'.
"""

import math
import os
import random
import wave

import numpy as np

SR = 44100
PEAK_TARGET = 0.45  # -7 dBFS headroom for the music+sfx bed


# ---------------------------------------------------------------------------
# Music styles — chord sets, tempo, drum pattern density, instrumentation
# ---------------------------------------------------------------------------

def _midi(f: float) -> float:
    return 440.0 * (2.0 ** ((f - 69) / 12))


def _chord_from_midis(midis: list[float]) -> list[float]:
    return [_midi(m) for m in midis]


STYLES = {
    # modern, lightly pulsing — for curiosity/chain stories
    "upbeat_pulse": {
        "bpm": 118,
        "chords": [
            _chord_from_midis([48, 55, 60, 64]),   # Cmaj
            _chord_from_midis([45, 52, 57, 60]),   # Am7
            _chord_from_midis([43, 50, 55, 59]),   # F
            _chord_from_midis([47, 53, 55, 62]),   # G (sus-ish)
        ],
        "chord_per": 4.0,
        "arpeggio": [0, 1, 2, 3, 2, 1],           # pattern offsets within chord
        "arpeg_gate": 0.16,
        "kick_every": 1.0,                         # every beat
        "hat_every": 0.25,
        "snare_every": 2.0,
        "pad_weight": 0.30,
        "energy_drive": 1.0,
    },
    # deeper, slower — myth-busting / tension reveals
    "dark_mystery": {
        "bpm": 92,
        "chords": [
            _chord_from_midis([45, 57, 60, 64]),   # Am
            _chord_from_midis([43, 55, 59, 62]),   # F
            _chord_from_midis([41, 53, 57, 60]),   # Dm
            _chord_from_midis([47, 55, 59, 62]),   # G -> back to Am
        ],
        "chord_per": 4.0,
        "arpeggio": [0, 2, 3, 2],
        "arpeg_gate": 0.22,
        "kick_every": 2.0,
        "hat_every": 0.5,
        "snare_every": 4.0,
        "pad_weight": 0.42,
        "energy_drive": 0.7,
    },
    # bright, light — wonder payoff
    "wonder": {
        "bpm": 104,
        "chords": [
            _chord_from_midis([48, 55, 60, 67]),   # Cmaj (high)
            _chord_from_midis([53, 57, 60, 64]),   # F
            _chord_from_midis([50, 57, 62, 65]),   # Dm
            _chord_from_midis([55, 62, 64, 67]),   # G
        ],
        "chord_per": 3.0,
        "arpeggio": [0, 1, 3, 1, 2, 3],
        "arpeg_gate": 0.12,
        "kick_every": 1.0,
        "hat_every": 0.25,
        "snare_every": 2.0,
        "pad_weight": 0.22,
        "energy_drive": 0.85,
    },
}


def _env(n: int) -> np.ndarray:
    """Smooth fade in/out envelope for the whole bed."""
    fade = int(SR * 1.5)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return env


def synth_music(style: str, duration: float, seed: int) -> np.ndarray:
    st = STYLES[style]
    rng = np.random.default_rng(seed)
    n = int(SR * duration)
    t = np.arange(n) / SR
    bed = np.zeros(n)

    beat = 60.0 / st["bpm"]
    chord_len = st["chord_per"]
    arpeg = st["arpeggio"]
    arpeg_gate = st["arpeg_gate"]
    note_step = beat * 0.25  # sixteenth note grid for arpeggios

    kick_f = 55.0
    hat_noise = rng.normal(0, 1, int(SR * 0.03))

    for j in range(0, n, int(SR * note_step)):
        beat_pos = (j / SR) % chord_len
        ci = int((j / SR) // chord_len) % len(st["chords"])
        chord = st["chords"][ci]
        # pad: gentle slow chord
        pad_env = math.exp(-((j / SR) % chord_len) / (chord_len * 0.5))
        for k, f in enumerate(chord):
            bed[j:j + int(SR * 0.3)] += (
                st["pad_weight"] * pad_env * math.sin(2 * math.pi * f * 0.5 * ((j / SR) % chord_len) + k)
                * 0.10
            )
        # arpeggio note
        note = chord[arpeg[int((j / SR) // note_step) % len(arpeg)]]
        gate = int(SR * arpeg_gate)
        for k in range(gate):
            idx = j + k
            if idx >= n:
                break
            tt = k / SR
            bed[idx] += math.sin(2 * math.pi * note * tt) * math.exp(-tt * 6.0) * 0.14

    # drums
    kick_offsets = []
    hh_offsets = []
    snare_offsets = []
    kt = 0.0
    while kt < duration:
        kick_offsets.append(kt)
        kt += beat * st["kick_every"]
    ht = 0.0
    while ht < duration:
        hh_offsets.append(ht)
        ht += beat * st["hat_every"]
    st_ = 0.0
    while st_ < duration:
        snare_offsets.append(st_)
        st_ += beat * st["snare_every"]

    for kt in kick_offsets:
        ki = int(kt * SR)
        for k in range(int(SR * 0.12)):
            idx = ki + k
            if idx >= n:
                break
            tt = k / SR
            env = math.exp(-tt * 40.0)
            bed[idx] += (math.sin(2 * math.pi * (kick_f + tt * 90) * tt) * env * 0.32
                         + 0.05 * math.sin(2 * math.pi * 120 * tt) * env)
    for ht in hh_offsets:
        hi = int(ht * SR)
        for k in range(int(SR * 0.02)):
            idx = hi + k
            if idx >= n:
                break
            tt = k / SR
            bed[idx] += hat_noise[min(k, len(hat_noise) - 1)] * math.exp(-tt * 120.0) * 0.05
    for so in snare_offsets:
        si = int(so * SR)
        for k in range(int(SR * 0.09)):
            idx = si + k
            if idx >= n:
                break
            tt = k / SR
            bed[idx] += hat_noise[min(k, len(hat_noise) - 1)] * math.exp(-tt * 35.0) * 0.16

    # energy rise near payoff (last 3s): gentle crescendo
    rise_start = max(0, n - int(SR * 3.0))
    rise = np.linspace(1.0, 1.25, n - rise_start)
    bed[rise_start:] *= rise

    bed *= _env(n)
    peak = float(np.max(np.abs(bed))) or 1.0
    return bed / peak * 0.8


# ---------------------------------------------------------------------------
# SFX synthesis
# ---------------------------------------------------------------------------

def synth_sfx(kind: str, duration: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * duration)
    t = np.arange(n) / SR

    if kind == "whoosh":
        # filtered noise sweep down
        noise = rng.normal(0, 1, n)
        alpha = 0.6 - 0.4 * (t / duration)          # lowpass cutoff drops
        y = np.zeros(n)
        prev = 0.0
        for i in range(n):
            prev = prev * alpha[i] + noise[i] * (1 - alpha[i])
            y[i] = prev
        env = np.sin(np.linspace(0, np.pi, n)) ** 1.5
        return y * env * 0.5

    if kind == "impact":
        # low boom + click
        y = np.zeros(n)
        for k in range(n):
            tt = t[k]
            y[k] = (math.sin(2 * math.pi * 62 * tt) * math.exp(-tt * 14.0) * 0.9
                    + rng.normal(0, 1) * math.exp(-tt * 70.0) * 0.15)
        return y * 0.9

    if kind == "rise":
        # riser sweep up with shimmer
        y = np.zeros(n)
        for k in range(n):
            tt = t[k]
            f = 120 + 1400 * (tt / duration) ** 1.6
            y[k] = math.sin(2 * math.pi * f * tt) * 0.5
        y += rng.normal(0, 1, n) * np.linspace(0, 0.18, n)
        env = np.linspace(0, 1, n) ** 1.6
        return y * env * 0.7

    if kind == "pop":
        # short high blip
        y = np.zeros(n)
        for k in range(n):
            tt = t[k]
            y[k] = math.sin(2 * math.pi * (800 + 500 * math.exp(-tt * 30)) * tt) * math.exp(-tt * 25.0)
        return y * 0.6

    if kind == "ding":
        # bell: two detuned partials
        y = np.zeros(n)
        for k in range(n):
            tt = t[k]
            y[k] = (math.sin(2 * math.pi * 1046.5 * tt) + 0.5 * math.sin(2 * math.pi * 1568 * tt)) \
                * math.exp(-tt * 4.5)
        return y * 0.5

    raise ValueError(f"unknown sfx kind: {kind}")


# ---------------------------------------------------------------------------
# Mix: ducking + sfx bake + write
# ---------------------------------------------------------------------------

def _duck_envelope(narration_windows: list[tuple[float, float]], n: int,
                   duck_db: float = 9.0, attack: float = 0.04, release: float = 0.22) -> np.ndarray:
    """Sidechain envelope: 1.0 when narration silent, 10^(-duck/20) while speaking."""
    g = np.ones(n)
    ratio = 10 ** (-duck_db / 20.0)
    for s0, s1 in narration_windows:
        a = int(s0 * SR); b = int(s1 * SR)
        a = max(0, a); b = min(n, b)
        aa = max(0, a - int(attack * SR))
        bb = min(n, b + int(release * SR))
        seg = g[aa:bb]
        if len(seg) == 0:
            continue
        # ramp down to ratio, hold, ramp back
        x = np.ones(len(seg)) * ratio
        r = len(seg)
        x[:min(len(seg), len(seg))] = 1.0
        hold = min(len(seg), max(1, int((b - a) * SR * 0.98) if (b - a) > 0 else 1))
        # simple piecewise: attack ramp (if any), hold at ratio, release ramp
        att_n = max(1, min(len(seg), int((a - aa) if (a - aa) > 0 else 0)))
        rel_n = max(1, min(len(seg), int((bb - b) if (bb - b) > 0 else 0)))
        if att_n > 0:
            seg[:att_n] = np.linspace(1.0, ratio, att_n)
        seg[att_n:att_n + hold] = ratio
        tail_start = min(len(seg), att_n + hold)
        tail_len = len(seg) - tail_start
        if tail_len > 0:
            seg[tail_start:] = np.linspace(ratio, 1.0, tail_len)
    return g


def mix_music(music: np.ndarray, sfx_events: list[dict], narration_windows: list[tuple[float, float]],
              out_wav: str) -> None:
    """Duck music under narration, bake SFX, normalize, write stereo wav."""
    n = len(music)
    g = _duck_envelope(narration_windows, n)
    mixed = music * g

    sfx_bed = np.zeros(n)
    for ev in sfx_events:
        start = int(ev["in_seconds"] * SR)
        if start >= n:
            continue
        y = synth_sfx(ev["type"], min(ev.get("duration", 0.8), (n - start) / SR),
                      ev.get("seed", 0))
        seg_len = min(len(y), n - start)
        sfx_bed[start:start + seg_len] += y[:seg_len] * ev.get("volume", 1.0)

    mixed = mixed + sfx_bed
    peak = float(np.max(np.abs(mixed))) or 1.0
    mixed = mixed / peak * PEAK_TARGET

    pcm = (mixed * 32767).astype(np.int16)
    stereo = np.column_stack([pcm, pcm]).ravel()
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(stereo.tobytes())


def save_mono(x: np.ndarray, out_wav: str, peak: float = 0.9) -> None:
    x = x / (float(np.max(np.abs(x))) or 1.0) * peak
    pcm = (x * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())