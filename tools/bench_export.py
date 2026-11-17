from __future__ import annotations

import cProfile
import hashlib
import io
import os
import pstats
import shutil
import sys
import tempfile
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
warnings.filterwarnings("ignore")

MODES = ["natural", "robot", "legacy", "natural+fx"]


def make_samples(folder: Path) -> list[Path]:
    import soundfile as sf
    from conftest import synth_vowel
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    vowels = {"a": ((700, 80), (1220, 90), (2600, 120)), "e": ((500, 70), (1800, 90), (2500, 110)),
              "i": ((300, 60), (2300, 100), (3000, 120)), "o": ((450, 70), (800, 80), (2830, 120)),
              "u": ((325, 60), (700, 70), (2530, 110))}
    for i, (name, fm) in enumerate(vowels.items()):
        p = folder / f"{name}.wav"
        sf.write(p, synth_vowel(f0=200 + 15 * i, dur=1.2, formants=fm, vibrato_cents=25, noise_onset=0.05,
                                seed=i), 48000, subtype="PCM_24")
        out.append(p)
    return out


def config_for(mode: str):
    from voxagen.models.config import GeneratorConfig
    c = GeneratorConfig()
    c.mode = mode.split("+")[0]
    c.musical.start_note, c.musical.start_octave, c.musical.semitones = 0, 3, 36
    c.export.bit_depth = "pcm24"
    c.export.dither = False
    c.export.write_individual = True
    if mode.endswith("+fx"):
        c.effects.enabled = True
        _add_fx(c)
    return c


def _add_fx(c):
    from voxagen.models.config import EffectSlot
    c.effects.chain = [EffectSlot(eid) for eid in ("double_pitch", "chorus", "eq")]


def audio_digest(folder: Path) -> dict[str, str]:
    import soundfile as sf
    out = {}
    for p in sorted(folder.rglob("*.wav")):
        data, sr = sf.read(p, dtype="float32", always_2d=True)
        out[str(p.relative_to(folder))] = hashlib.sha256(data.tobytes() + str(sr).encode()).hexdigest()
    return out


def run(action: str, ref: Path, profile: bool) -> int:
    work = Path(tempfile.mkdtemp(prefix="vxbench-"))
    os.environ["VOXAGEN_DATA_DIR"] = str(work / "appdata")
    os.environ["VOXAGEN_CACHE_DIR"] = str(work / "cache")
    from voxagen.core.audio.pipeline import clear_memory_caches
    from voxagen.core.export.exporter import export_chromatic
    from voxagen.core.samples.library import SampleLibrary
    lib = SampleLibrary()
    lib.add_files(make_samples(work / "samples"))
    bad = 0
    total = 0.0
    for mode in MODES:
        clear_memory_caches()
        shutil.rmtree(work / "cache", ignore_errors=True)
        cfg = config_for(mode)
        dest = work / "out" / mode
        prof = cProfile.Profile() if profile else None
        t = time.perf_counter()
        if prof:
            prof.enable()
        export_chromatic(cfg, lib, dest)
        if prof:
            prof.disable()
        dt = time.perf_counter() - t
        total += dt
        digest = audio_digest(dest)
        line = f"{mode:12s} {dt:7.2f} s  ({len(digest)} files)"
        if action == "save":
            (ref / mode).mkdir(parents=True, exist_ok=True)
            (ref / mode / "digest.txt").write_text("\n".join(f"{k} {v}" for k, v in digest.items()), "utf-8")
            (ref / mode / "time.txt").write_text(f"{dt:.3f}", "utf-8")
        else:
            want = dict(l.rsplit(" ", 1) for l in (ref / mode / "digest.txt").read_text("utf-8").splitlines())
            diff = [k for k in want if want[k] != digest.get(k)] + [k for k in digest if k not in want]
            before = float((ref / mode / "time.txt").read_text())
            line += f"  before {before:6.2f} s  x{before / dt:4.2f}  " + ("IDENTICAL" if not diff else
                                                                      f"DIFFERENT: {len(diff)} files")
            bad += bool(diff)
        print(line, flush=True)
        if prof:
            s = io.StringIO()
            pstats.Stats(prof, stream=s).sort_stats("cumulative").print_stats(25)
            print(s.getvalue())
    print(f"total {total:.2f} s")
    shutil.rmtree(work, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    act, ref = sys.argv[1], Path(sys.argv[2])
    sys.exit(run(act, ref, "--profile" in sys.argv))
