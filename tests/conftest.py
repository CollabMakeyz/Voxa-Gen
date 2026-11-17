import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", category=UserWarning, module="pyworld")
warnings.filterwarnings("ignore", message=".*pkg_resources.*")


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXAGEN_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("VOXAGEN_CACHE_DIR", str(tmp_path / "cache"))


def synth_vowel(f0=220.0, sr=48000, dur=0.8, formants=((700, 80), (1220, 90), (2600, 120)),
                vibrato_cents=0.0, vibrato_hz=5.5, noise_onset=0.0, stereo=False, seed=0):
    from scipy.signal import lfilter
    rng = np.random.default_rng(seed)
    n = int(sr * dur)
    t = np.arange(n) / sr
    f_inst = f0 * 2 ** ((vibrato_cents / 1200.0) * np.sin(2 * np.pi * vibrato_hz * t))
    phase = 2 * np.pi * np.cumsum(f_inst) / sr
    src = np.zeros(n)
    k = 1
    while k * f0 * 1.05 < sr / 2 * 0.9:
        src += np.sin(k * phase) / k
        k += 1
    y = np.zeros(n)
    for fc, bw in formants:
        r = np.exp(-np.pi * bw / sr)
        th = 2 * np.pi * fc / sr
        a = [1, -2 * r * np.cos(th), r * r]
        y += lfilter([1 - r], a, src)
    if noise_onset > 0:
        m = int(noise_onset * sr)
        noise = rng.standard_normal(m) * 0.3
        y = np.concatenate([noise, y])[: n + m]
    env = np.ones(len(y))
    fl = int(0.02 * sr)
    env[:fl] = np.linspace(0, 1, fl)
    env[-fl:] = np.linspace(1, 0, fl)
    y = y * env
    y = 0.5 * y / (np.max(np.abs(y)) + 1e-12)
    if stereo:
        return np.stack([y, 0.6 * y], axis=1).astype(np.float32)
    return y.astype(np.float32)


@pytest.fixture
def make_wav(tmp_path):
    def _make(name, f0=220.0, sr=48000, dur=0.6, stereo=False, subtype="PCM_16", folder="samples", **kw):
        d = tmp_path / folder
        d.mkdir(exist_ok=True)
        p = d / name
        sf.write(p, synth_vowel(f0, sr, dur, stereo=stereo, **kw), sr, subtype=subtype)
        return p
    return _make
