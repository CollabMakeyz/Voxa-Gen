import json
import sys
from pathlib import Path

import pytest

from voxagen import i18n

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from i18n_extract import decode, extract

CODES = [c for c in i18n.LANGUAGES if c != "en"]


def _catalog(code):
    return json.loads((ROOT / "assets" / "i18n" / f"{code}.json").read_text("utf-8"))


def test_eight_languages_available():
    assert list(i18n.LANGUAGES) == ["en", "pt_PT", "pt_BR", "pt_BR_slang", "es", "ja", "en_pirate", "cat"]
    assert i18n.LANGUAGES["ja"] == "日本語" and i18n.LANGUAGES["cat"] == "Meowgwenge"


@pytest.mark.parametrize("code", CODES)
def test_every_visible_string_is_translated(code):
    ok = {decode(l) for l in (ROOT / "tools" / "i18n" / "untranslated_ok.txt").read_text("utf-8").splitlines()
          if l and not l.startswith("#")}
    cat = _catalog(code)
    missing = [s for s in extract() if s not in cat and s not in ok]
    assert not missing, f"{code}: {len(missing)} untranslated, e.g. {missing[:5]}"


@pytest.mark.parametrize("code", CODES)
def test_placeholders_are_preserved(code):
    for en, text in _catalog(code).items():
        if en.startswith("_"):
            continue
        assert i18n.placeholders(en) == i18n.placeholders(text), (code, en, text)


def test_tr_fills_values_after_translation_and_falls_back():
    try:
        i18n.set_language("pt_BR")
        assert i18n.tr("{n} sample(s) added", n=3) == "3 sample(s) adicionado(s)"
        assert i18n.tr("A text nobody translated") == "A text nobody translated"
        assert i18n.source_of("Exportação concluída") == "Export complete"
        i18n.set_language("ja")
        assert i18n.tr("Export complete") == "書き出し完了" and i18n.is_cjk()
        i18n.set_language("xx")
        assert i18n.language() == "en"
    finally:
        i18n.set_language("en")


def test_joke_languages_stay_understandable():
    pirate, cat = _catalog("en_pirate"), _catalog("cat")
    assert pirate["Export complete"] == "Plunder complete, arr!"
    assert "Ctrl+S" in pirate["Save the project (Ctrl+S)"]
    assert "meow" in cat["Pick the folder with your voice samples (WAV). Names like 1.wav, a.wav or e2.wav are "
                         "recognised on their own. Your original files are never changed."].lower()
    assert "{name}" in cat["Project saved: {name}"] and "{n}" in pirate["{n} sample(s) added"]
    pt_pt = _catalog("pt_PT")
    assert "ficheiro" in pt_pt["Add WAV files"].lower() and pt_pt["Processing"] == "A processar"
