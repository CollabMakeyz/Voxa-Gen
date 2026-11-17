import json

import pytest

from voxagen.core.presets.manager import Preset, PresetError, PresetManager
from voxagen.core.sequences.order import BF_CLASSIC_NAME, BF_CLASSIC_TOKENS
from voxagen.models.app_settings import AppSettings, SettingsStore
from voxagen.models.config import NaturalParams
from voxagen.models.serialization import from_dict, to_dict


def test_native_presets_present_and_bf_exact(tmp_path):
    pm = PresetManager(tmp_path)
    bf = pm.get("sequence", BF_CLASSIC_NAME)
    assert bf.builtin and tuple(bf.tokens()) == BF_CLASSIC_TOKENS
    assert pm.list("natural") and pm.list("export") and pm.list("lab")


def test_create_rename_duplicate_delete(tmp_path):
    pm = PresetManager(tmp_path)
    pm.save(Preset("sequence", "Mine", {"tokens": ["a", "e2"]}))
    pm.rename("sequence", "Mine", "Ours")
    assert pm.get("sequence", "Mine") is None and pm.get("sequence", "Ours").tokens() == ["a", "e2"]
    dup = pm.duplicate("sequence", "Ours")
    assert dup.name == "Ours copy"
    pm.delete("sequence", "Ours")
    assert pm.get("sequence", "Ours") is None
    with pytest.raises(PresetError):
        pm.delete("sequence", BF_CLASSIC_NAME)
    with pytest.raises(PresetError):
        pm.save(Preset("sequence", "Empty", {"tokens": []}))


def test_native_override_and_restore(tmp_path):
    pm = PresetManager(tmp_path)
    pm.save(Preset("sequence", BF_CLASSIC_NAME, {"tokens": ["a"]}))
    p = pm.get("sequence", BF_CLASSIC_NAME)
    assert p.modified and p.tokens() == ["a"]
    pm.restore("sequence", BF_CLASSIC_NAME)
    assert tuple(pm.get("sequence", BF_CLASSIC_NAME).tokens()) == BF_CLASSIC_TOKENS
    pm.save(Preset("natural", "Natural · Clean", to_dict(NaturalParams(smoothing=0.9))))
    assert pm.restore_all() == 1


def test_import_export_roundtrip_and_name_collision(tmp_path):
    pm = PresetManager(tmp_path / "a")
    pm.save(Preset("lab", "Bright", to_dict(NaturalParams(formant_preservation=0.5, tools_enabled={"smoothing": False}))))
    f = tmp_path / "bright.json"
    pm.export_to("lab", "Bright", f)
    data = json.loads(f.read_text())
    assert data["format"] == "voxagen-preset" and data["version"] == 1
    other = PresetManager(tmp_path / "b")
    p = other.import_from(f)
    assert p.typed().formant_preservation == 0.5 and not p.typed().tool_on("smoothing")
    p2 = other.import_from(f)
    assert p2.name == "Bright 2"


def test_future_version_and_unknown_fields_are_tolerated(tmp_path):
    f = tmp_path / "future.json"
    f.write_text(json.dumps({"format": "voxagen-preset", "version": 99, "kind": "natural", "name": "Future",
                             "data": {"smoothing": 0.4, "brand_new_option": True}}))
    p = PresetManager(tmp_path / "pm").import_from(f)
    assert p.typed().smoothing == 0.4


def test_settings_persist_and_survive_corruption(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    s = store.load()
    s.theme = "light"
    s.generator.order.sequence = list(BF_CLASSIC_TOKENS)
    s.generator.export.bit_depth = "pcm24"
    s.ui_sounds.event("error").volume = 0.25
    store.save(s)
    s2 = store.load()
    assert s2.theme == "light" and s2.generator.export.bit_depth == "pcm24"
    assert tuple(s2.generator.order.sequence) == BF_CLASSIC_TOKENS
    assert s2.ui_sounds.events["error"].volume == 0.25
    (tmp_path / "settings.json").write_text("{not json")
    assert store.load().theme == "dark"
    assert (tmp_path / "settings.corrupt.json").exists()


def test_from_dict_ignores_bad_values():
    p = from_dict(NaturalParams, {"smoothing": "oops", "humanization": 0.3, "unknown": 1})
    assert p.humanization == 0.3


def test_lab_tool_switches_neutralise():
    p = NaturalParams(humanization=0.8, smoothing=0.5, tools_enabled={"humanization": False, "vuv": False})
    e = p.effective()
    assert e.humanization == 0 and e.smoothing == 0.5 and not e.vuv_processing
    assert p.humanization == 0.8
