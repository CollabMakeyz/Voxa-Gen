from collections import Counter

import pytest

from voxagen.core.samples.library import SampleLibrary
from voxagen.core.samples.naming import natural_key, parse_sequence_text, sample_id_from_path
from voxagen.core.sequences.order import (
    BF_CLASSIC_TEXT, BF_CLASSIC_TOKENS, MissingSampleError, OrderError, build_order,
    resolve_sequence, validate_sequence,
)
from voxagen.models.config import OrderSettings

BF_EXPECTED = ("a e2 o e a2 o u i a o a2 e2 e u i a o i u a2 e2 u i u2 i u a a3 e2 e3 "
               "u a2 a e e2 u e2 e2 u a a2 e e2 u e2").split()


def test_numbered_natural_sort():
    names = [str(i) for i in range(1, 13)]
    shuffled = ["10", "2", "1", "12", "3", "11", "4", "5", "6", "7", "8", "9"]
    assert sorted(shuffled, key=natural_key) == names


def test_lettered_and_variation_sort():
    ids = ["e2", "a3", "a", "u", "a2", "e", "a10"]
    assert sorted(ids, key=natural_key) == ["a", "a2", "a3", "a10", "e", "e2", "u"]


def test_identifiers_from_names():
    assert sample_id_from_path("C:/x/A2.WAV") == "a2"
    assert sample_id_from_path("1.wav") == "1"
    assert sample_id_from_path("breath_long.wav") == "breath_long"


def test_sequential_cycles_in_order():
    s = OrderSettings(mode="sequential")
    out = build_order(7, ["3", "1", "10", "2"], s)
    assert out == ["1", "2", "3", "10", "1", "2", "3"]


def test_shuffle_no_repeat_within_cycle():
    ids = [str(i) for i in range(1, 8)]
    s = OrderSettings(mode="shuffle", use_seed=True, seed=99)
    out = build_order(7 * 6, ids, s)
    for c in range(6):
        cycle = out[c * 7:(c + 1) * 7]
        assert sorted(cycle, key=natural_key) == ids
    assert all(out[i] != out[i + 1] for i in range(len(out) - 1))


def test_shuffle_partial_cycle_has_no_duplicates():
    ids = list("abcdefgh")
    out = build_order(5, ids, OrderSettings(mode="shuffle"))
    assert len(set(out)) == 5


def test_random_allows_repetition_and_seed_is_reproducible():
    ids = ["a", "b"]
    s = OrderSettings(mode="random", use_seed=True, seed=7)
    out1 = build_order(200, ids, s)
    out2 = build_order(200, ids, s)
    assert out1 == out2
    assert any(out1[i] == out1[i + 1] for i in range(199))
    assert set(Counter(out1)) == {"a", "b"}


def test_bf_classic_exact():
    assert list(BF_CLASSIC_TOKENS) == BF_EXPECTED
    assert len(BF_CLASSIC_TOKENS) == 45
    available = set(BF_EXPECTED)
    s = OrderSettings(mode="vocal", sequence=list(BF_CLASSIC_TOKENS))
    out = build_order(90, sorted(available), s)
    assert out[:45] == BF_EXPECTED
    assert out[45:] == BF_EXPECTED
    assert parse_sequence_text(BF_CLASSIC_TEXT) == BF_EXPECTED


def test_variation_is_a_distinct_file_not_a_fallback():
    with pytest.raises(MissingSampleError) as ei:
        resolve_sequence(["a", "a2", "e"], {"a", "e"})
    assert "a2" in ei.value.missing
    assert ei.value.missing["a2"] == [1]
    assert "a2.wav" in str(ei.value)


def test_missing_remap_and_skip():
    tokens = ["a", "a2", "e", "u2"]
    assert resolve_sequence(tokens, {"a", "e", "u"}, {"a2": "a", "u2": ""}) == ["a", "a", "e"]
    st = validate_sequence(tokens, {"a", "e", "u"}, {"a2": "a"})
    assert [x.state for x in st] == ["ok", "remapped", "ok", "missing"]


def test_custom_sequence_with_arbitrary_names():
    s = OrderSettings(mode="vocal", sequence=["breath", "1", "ah_long", "1"])
    assert build_order(6, ["1", "ah_long", "breath"], s) == ["breath", "1", "ah_long", "1", "breath", "1"]


def test_all_skipped_is_error():
    with pytest.raises(OrderError):
        resolve_sequence(["x"], {"a"}, {"x": ""})


def test_library_scan(make_wav, tmp_path):
    for n in ["1.wav", "2.wav", "10.wav", "a.wav", "a2.wav", "notes.txt"]:
        if n.endswith(".wav"):
            make_wav(n)
        else:
            (tmp_path / "samples" / n).write_text("x")
    lib = SampleLibrary()
    res = lib.add_folder(tmp_path / "samples")
    assert lib.ids() == ["1", "2", "10", "a", "a2"]
    assert len(res.skipped) == 1
    s = lib.get("a2")
    assert s.sample_rate == 48000 and s.channels == 1 and s.bit_depth_label == "16-bit"
    assert lib.get("2").duplicate_of == "1"


def test_library_remove_does_not_touch_disk(make_wav):
    p = make_wav("a.wav")
    lib = SampleLibrary()
    lib.add_files([p])
    lib.remove("a")
    assert "a" not in lib and p.exists()


def test_library_missing_and_replace(make_wav):
    p = make_wav("a.wav")
    q = make_wav("other.wav", f0=300)
    lib = SampleLibrary()
    lib.add_files([p])
    p.unlink()
    lib.reload()
    assert lib.get("a").status == "missing"
    lib.replace("a", q)
    assert lib.get("a").status == "ok" and lib.get("a").path == str(q)
