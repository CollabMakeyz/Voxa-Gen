import json
import shutil

import numpy as np
import soundfile as sf

from voxagen.core.effects import new_slot
from voxagen.core.export.batch import jobs_from_data, jobs_to_data, make_job, overall_progress, run_batch
from voxagen.core.projects import find_in_folder, load_project, save_project
from voxagen.core.samples.analyzer import analyze_library
from voxagen.core.samples.library import SampleLibrary
from voxagen.models.config import GeneratorConfig


def _lib(make_wav, names=("a", "e", "i")):
    lib = SampleLibrary()
    lib.add_files([make_wav(f"{n}.wav", f0=220 + 10 * i, dur=0.3) for i, n in enumerate(names)])
    return lib


def _cfg():
    c = GeneratorConfig()
    c.mode = "robot"
    c.musical.semitones = 3
    return c


def test_project_roundtrip_keeps_everything(tmp_path, make_wav):
    lib = _lib(make_wav)
    cfg = _cfg()
    cfg.order.mode = "vocal"
    cfg.order.sequence = ["a", "e", "a", "i"]
    cfg.order.sequence_name = "Mine"
    cfg.musical.a4_hz = 432.0
    cfg.lab.humanization = 0.4
    cfg.effects.enabled = True
    cfg.effects.chain = [new_slot("vibrato"), new_slot("eq")]
    cfg.effects.preset_name = "Warm Studio"
    cfg.export.bit_depth = "pcm24"
    cfg.disabled_samples = ["i"]
    path = save_project(tmp_path / "proj" / "song", cfg, lib, batch=[{"x": 1}])
    assert path.suffix == ".vxproj"
    lp = load_project(path)
    assert not lp.missing
    c = lp.config
    assert c.order.sequence == ["a", "e", "a", "i"] and c.musical.a4_hz == 432.0
    assert c.lab.humanization == 0.4 and c.export.bit_depth == "pcm24"
    assert [s.effect for s in c.effects.chain] == ["vibrato", "eq"] and c.effects.enabled
    assert lp.presets["effects"] == "Warm Studio" and lp.batch == [{"x": 1}]
    assert c.disabled_samples == ["i"]
    lib2 = SampleLibrary()
    lp.apply_to(lib2)
    assert lib2.ids() == ["a", "e", "i"]


def test_project_reports_missing_and_relocates(tmp_path, make_wav):
    lib = _lib(make_wav)
    path = save_project(tmp_path / "p.vxproj", _cfg(), lib)
    moved = tmp_path / "moved"
    moved.mkdir()
    shutil.move(lib.get("e").path, moved / "e.wav")
    lp = load_project(path)
    assert [s.id for s in lp.missing] == ["e"]
    found = find_in_folder(lp.missing, tmp_path)
    assert found == {"e": str(moved / "e.wav")}
    lib2 = SampleLibrary()
    lp.apply_to(lib2)
    assert lib2.get("e").status == "missing"
    lib2.add_with_id(found["e"], "e")
    assert lib2.get("e").usable


def test_project_relative_paths_survive_moving_the_folder(tmp_path, make_wav):
    lib = _lib(make_wav)
    proj = save_project(tmp_path / "p.vxproj", _cfg(), lib)
    new_root = tmp_path.parent / (tmp_path.name + "_copy")
    shutil.copytree(tmp_path, new_root)
    shutil.rmtree(tmp_path / "samples")
    lp = load_project(new_root / proj.name)
    assert not lp.missing


def test_project_rejects_other_files(tmp_path):
    import pytest
    from voxagen.core.projects import ProjectError
    p = tmp_path / "x.vxproj"
    p.write_text(json.dumps({"format": "other"}))
    with pytest.raises(ProjectError):
        load_project(p)
    with pytest.raises(ProjectError):
        load_project(tmp_path / "nope.vxproj")


def test_batch_runs_independent_jobs_and_never_overwrites(tmp_path, make_wav):
    lib = _lib(make_wav)
    cfg = _cfg()
    cfg.export.output_dir = str(tmp_path / "out")
    cfg.export.folder_name = "Job A"
    a = make_job("A", cfg, lib)
    cfg.export.folder_name = "Job B"
    cfg.mode = "legacy"
    cfg.musical.semitones = 2
    b = make_job("B", cfg, lib)
    cfg.musical.semitones = 99
    events = []
    run_batch([a, b], lambda i, j: events.append((i, j.status)))
    assert a.status == b.status == "done"
    assert (tmp_path / "out" / "Job A" / "chromatic.wav").exists()
    info = json.loads((tmp_path / "out" / "Job B" / "export_info.json").read_text("utf-8"))
    assert info["mode"] == "legacy" and len(info["notes"]) == 2
    assert overall_progress([a, b]) == 1.0
    assert (0, "running") in events and (1, "done") in events
    a.reset()
    run_batch([a])
    assert a.status == "done" and a.result_folder.endswith("Job A (2)")
    a.reset()
    a.conflict = "skip"
    run_batch([a])
    assert a.status == "skipped"


def test_batch_failure_does_not_stop_others_and_cancel(tmp_path, make_wav):
    lib = _lib(make_wav)
    cfg = _cfg()
    cfg.export.output_dir = str(tmp_path / "out")
    bad = make_job("bad", cfg, lib)
    bad.samples.append(["zz", str(tmp_path / "missing.wav")])
    cfg.export.folder_name = "good"
    good = make_job("good", cfg, lib)
    run_batch([bad, good])
    assert bad.status == "failed" and "zz" in bad.error
    assert good.status == "done"
    c1, c2 = make_job("c1", cfg, lib), make_job("c2", cfg, lib)
    run_batch([c1, c2], cancel=lambda: True)
    assert c1.status == c2.status == "cancelled"
    restored = jobs_from_data(jobs_to_data([bad, good]))
    assert [j.status for j in restored] == ["failed", "done"]


def test_analyzer_finds_real_problems(tmp_path, make_wav):
    lib = _lib(make_wav, ("a", "e", "i", "o"))
    sr = 48000
    d = tmp_path / "bad"
    d.mkdir()
    t = np.arange(sr) / sr
    clip = np.clip(np.sin(2 * np.pi * 220 * t) * 2.0, -1, 1)
    sf.write(d / "clip.wav", clip, sr, subtype="FLOAT")
    sf.write(d / "quiet.wav", np.sin(2 * np.pi * 220 * t[: sr // 3]) * 0.005, sr)
    sf.write(d / "silent.wav", np.zeros(sr // 2), sr)
    pad = np.concatenate([np.zeros(sr), np.sin(2 * np.pi * 220 * t[: sr // 3]) * 0.3, np.zeros(sr)])
    sf.write(d / "padded.wav", pad, sr)
    (d / "broken.wav").write_bytes(b"RIFFnope")
    lib.add_files(sorted(d.iterdir()))
    lib.add_missing("ghost", str(d / "ghost.wav"))
    rep = analyze_library(lib)
    kinds = {(f.sample_id, f.kind) for f in rep.findings}
    assert ("clip", "clipping") in kinds
    assert ("quiet", "volume") in kinds
    assert ("silent", "silent") in kinds
    assert ("padded", "silence") in kinds
    assert ("broken", "invalid") in kinds
    assert ("ghost", "missing") in kinds
    assert ("padded", "duration") in kinds
    assert not rep.ok and all(f.fix for f in rep.findings)
    assert rep.stats["a"].sample_rate == 48000 and rep.stats["a"].peak_db < 0
    clean = analyze_library(_lib(make_wav, ("x", "y")))
    assert clean.ok and not [f for f in clean.findings if f.severity != "info"]
