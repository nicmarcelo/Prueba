#!/usr/bin/env python3
"""Synthesises the ASMR soundtrack for the whiteboard video.

Reads the timeline exported by scripts/render.mjs (build/timeline.json) and
writes a 48 kHz stereo WAV with:
  * marker squeaks that follow every stroke and every written letter,
  * soft "squish" / "pop" sounds when a squishy gets its colour,
  * a felt-eraser whoosh for each scene wipe,
  * a very quiet room tone plus an airy pad underneath.

Usage: python3 scripts/make_audio.py build/timeline.json build/audio.wav [--no-pad]
"""
import json
import math
import sys
import wave

import numpy as np

SR = 48000
rng = np.random.default_rng(20251010)


# ----------------------------------------------------------------- helpers
def seconds(n):
    return int(round(n * SR))


def env_ad(n, attack, decay_tau, hold=0.0):
    """Attack (linear, seconds) then exponential decay with time constant."""
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    d = np.where(t > hold, np.exp(-(t - hold) / max(decay_tau, 1e-4)), 1.0)
    return a * d


def fade(sig, fin=0.01, fout=0.02):
    n = len(sig)
    fi, fo = min(seconds(fin), n // 2), min(seconds(fout), n // 2)
    out = sig.copy()
    if fi > 0:
        out[:fi] *= np.linspace(0, 1, fi)
    if fo > 0:
        out[n - fo:] *= np.linspace(1, 0, fo)
    return out


def noise(n):
    return rng.standard_normal(n)


def spectral(sig, shape_fn):
    """Apply a magnitude shaping function f(freqs) to a signal via FFT."""
    spec = np.fft.rfft(sig)
    f = np.fft.rfftfreq(len(sig), 1 / SR)
    spec *= shape_fn(f)
    return np.fft.irfft(spec, n=len(sig))


def bandpass_noise(n, lo, hi, slope=1.0):
    def shape(f):
        g = np.ones_like(f)
        g[f < lo] = np.exp(-((lo - f[f < lo]) / (lo * 0.5 + 1)) ** 2 * slope)
        g[f > hi] = np.exp(-((f[f > hi] - hi) / (hi * 0.35 + 1)) ** 2 * slope)
        return g
    sig = spectral(noise(n), shape)
    return sig / (np.max(np.abs(sig)) + 1e-9)


def pink_noise(n):
    def shape(f):
        g = np.ones_like(f)
        g[1:] = 1 / np.sqrt(f[1:])
        g[0] = 0
        return g
    sig = spectral(noise(n), shape)
    return sig / (np.max(np.abs(sig)) + 1e-9)


def lowpass_sweep(sig, f_start, f_end, curve=1.0):
    """One-pole low-pass whose cutoff glides from f_start to f_end."""
    n = len(sig)
    u = (np.arange(n) / max(n - 1, 1)) ** curve
    fc = f_start * (f_end / f_start) ** u
    alpha = 1 - np.exp(-2 * math.pi * fc / SR)
    out = np.empty(n)
    y = 0.0
    for i in range(n):
        y += alpha[i] * (sig[i] - y)
        out[i] = y
    return out


def chirp(dur, f0, f1, curve=1.0):
    n = seconds(dur)
    u = (np.arange(n) / max(n - 1, 1)) ** curve
    f = f0 * (f1 / f0) ** u
    phase = 2 * math.pi * np.cumsum(f) / SR
    return np.sin(phase)


def pan_gains(x):
    """Equal-power pan from a stage x coordinate (0..1080)."""
    p = (np.clip(x / 1080, 0, 1) - 0.5) * 0.7  # keep it gentle
    th = (p + 0.5) * math.pi / 2
    return math.cos(th), math.sin(th)


class Mix:
    def __init__(self, dur):
        self.n = seconds(dur)
        self.L = np.zeros(self.n)
        self.R = np.zeros(self.n)

    def add(self, t, sig, gain=1.0, x=540):
        i = seconds(t)
        if i >= self.n:
            return
        sig = sig[: self.n - i]
        gl, gr = pan_gains(x)
        self.L[i:i + len(sig)] += sig * gain * gl
        self.R[i:i + len(sig)] += sig * gain * gr


# --------------------------------------------------------------- sound design
def marker_tick(x_pos):
    """A single letter being written: short dry scratch, occasionally squeaky."""
    dur = rng.uniform(0.05, 0.11)
    n = seconds(dur)
    s = bandpass_noise(n, 1500, 7000) * env_ad(n, 0.004, dur * 0.35)
    if rng.random() < 0.25:
        f = rng.uniform(2200, 4200)
        sq = chirp(dur, f, f * rng.uniform(0.85, 1.15)) * env_ad(n, 0.01, dur * 0.3)
        s = s * 0.8 + sq * 0.25
    return fade(s, 0.002, 0.01), rng.uniform(0.55, 1.0)


def marker_stroke(a, b, length):
    """Continuous marker drag with wobble; long strokes get a squeaky tone."""
    dur = max(0.05, b - a)
    n = seconds(dur)
    base = bandpass_noise(n, 900, 5500)
    # amplitude wobble from slow filtered noise
    wob = pink_noise(n)
    wob = lowpass_sweep(wob, 12, 12)
    wob = 0.65 + 0.35 * wob / (np.max(np.abs(wob)) + 1e-9)
    s = base * wob
    speed = length / dur  # px per second
    if speed > 350 and rng.random() < 0.6:
        f = rng.uniform(1700, 3100)
        vib = 1 + 0.04 * np.sin(2 * math.pi * rng.uniform(4, 8) * np.arange(n) / SR)
        phase = 2 * math.pi * np.cumsum(f * vib) / SR
        tone = np.sin(phase) * (0.5 + 0.5 * wob)
        s = s * 0.85 + tone * 0.22
    s = fade(s, 0.03, 0.05)
    s /= (np.max(np.abs(s)) + 1e-9)
    return s


def squish(size=1.0):
    """Slow-rise foam being pressed: wet low noise with a falling resonance."""
    dur = rng.uniform(0.34, 0.46) * (0.8 + 0.3 * min(size, 2.5) / 2.5)
    n = seconds(dur)
    body = lowpass_sweep(noise(n), 2200, 220, curve=0.7)
    body /= (np.max(np.abs(body)) + 1e-9)
    body *= env_ad(n, 0.03, dur * 0.4, hold=dur * 0.15)
    # wet "glurp" component
    g = chirp(min(dur, 0.18), rng.uniform(380, 480), rng.uniform(90, 130), curve=0.8)
    g *= env_ad(len(g), 0.006, 0.07)
    s = body
    s[: len(g)] += g * 0.6
    # a couple of tiny bubbles
    for _ in range(rng.integers(1, 4)):
        off = seconds(rng.uniform(0.05, dur * 0.7))
        bd = rng.uniform(0.02, 0.05)
        bb = chirp(bd, rng.uniform(900, 1600), rng.uniform(300, 600)) * env_ad(seconds(bd), 0.002, bd * 0.3)
        s[off: off + len(bb)] += bb[: max(0, n - off)] * 0.18
    return fade(s, 0.004, 0.04)


def pop():
    """Small satisfying pop/click."""
    dur = 0.075
    n = seconds(dur)
    s = chirp(dur, 1300, 380, curve=0.7) * env_ad(n, 0.0015, 0.02)
    click = bandpass_noise(n, 2500, 9000) * env_ad(n, 0.0005, 0.004)
    return fade(s * 0.8 + click * 0.5, 0.0005, 0.01)


def fill_hush(size=1.0):
    """Colour fading in: a soft marker rub."""
    dur = 0.3
    n = seconds(dur)
    s = bandpass_noise(n, 300, 2500) * env_ad(n, 0.05, 0.12, hold=0.05)
    return fade(s, 0.02, 0.05)


def eraser_whoosh(dur, rows=5):
    n = seconds(dur)
    u = np.arange(n) / max(n - 1, 1)
    base = pink_noise(n)
    base = spectral(base, lambda f: np.exp(-(f / 1400) ** 2))
    base /= (np.max(np.abs(base)) + 1e-9)
    felt = bandpass_noise(n, 250, 1100)
    strokes = np.abs(np.sin(math.pi * rows * u)) ** 0.55
    s = (base * 0.9 + felt * 0.5) * (0.35 + 0.65 * strokes) * (1 - 0.25 * u)
    return fade(s, 0.04, 0.15)


def pad(dur):
    n = seconds(dur)
    t = np.arange(n) / SR
    freqs = [130.81, 164.81, 196.00, 246.94, 329.63]
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        lfo = 0.5 + 0.5 * np.sin(2 * math.pi * rng.uniform(0.04, 0.11) * t + rng.uniform(0, 6.28))
        det = rng.uniform(-0.3, 0.3)
        v = np.sin(2 * math.pi * (f + det) * t) + 0.5 * np.sin(2 * math.pi * (f * 2.001) * t)
        out += v * (0.3 + 0.7 * lfo) / len(freqs)
    # gentle swell in / out
    out *= np.clip(t / 3.0, 0, 1) * np.clip((dur - t) / 3.0, 0, 1)
    return out


# ------------------------------------------------------------------- main
def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    tl = json.load(open(sys.argv[1]))
    out_path = sys.argv[2]
    use_pad = '--no-pad' not in sys.argv
    dur = float(tl['duration'])
    mix = Mix(dur)

    # bed
    room = pink_noise(mix.n)
    room = spectral(room, lambda f: np.exp(-(f / 500) ** 2))
    room /= (np.max(np.abs(room)) + 1e-9)
    mix.add(0, room, 0.012, 300)
    mix.add(0, room[::-1], 0.012, 780)
    if use_pad:
        p = pad(dur)
        mix.add(0, p, 0.045, 400)
        mix.add(0, np.roll(p, 1200), 0.045, 680)

    counts = {}
    for ev in tl['events']:
        k = ev['kind']
        counts[k] = counts.get(k, 0) + 1
        if k == 'char':
            s, g = marker_tick(ev.get('x', 540))
            mix.add(ev['t'], s, 0.085 * g, ev.get('x', 540))
        elif k == 'stroke':
            s = marker_stroke(ev['a'], ev['b'], ev.get('len', 100))
            mix.add(ev['a'], s, 0.07, (ev.get('x', 540) + ev.get('x1', 540)) / 2)
        elif k == 'fill':
            sfx = ev.get('sfx')
            x = ev.get('x', 540)
            if sfx == 'squish':
                mix.add(ev['t'] + 0.03, squish(ev.get('size', 1.0)), 0.34, x)
            elif sfx == 'pop':
                mix.add(ev['t'] + 0.02, pop(), 0.2, x)
            else:
                mix.add(ev['t'], fill_hush(), 0.035, x)
        elif k == 'erase':
            mix.add(ev['a'], eraser_whoosh(ev['b'] - ev['a']), 0.2, 540)

    # master: fades, soft clip, normalise
    n = mix.n
    master = np.stack([mix.L, mix.R], axis=1)
    fi, fo = seconds(0.4), seconds(1.4)
    master[:fi] *= np.linspace(0, 1, fi)[:, None]
    master[n - fo:] *= np.linspace(1, 0, fo)[:, None]
    master = np.tanh(master * 2.6) / 2.6
    peak = np.max(np.abs(master)) + 1e-9
    master *= 0.85 / peak
    pcm = (master * 32767).astype('<i2')
    with wave.open(out_path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print('audio written:', out_path, f'{dur:.1f}s', counts)


if __name__ == '__main__':
    main()
