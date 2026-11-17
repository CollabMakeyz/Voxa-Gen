from __future__ import annotations

import json
import string
from typing import Callable

LANGUAGES: dict[str, str] = {
    "en": "English",
    "pt_PT": "Português (Portugal)",
    "pt_BR": "Português (Brasil)",
    "pt_BR_slang": "Português (Brasil, com gírias)",
    "es": "Español",
    "ja": "日本語",
    "en_pirate": "Pirate English",
    "cat": "Meowgwenge",
}
DEFAULT = "en"

_current = DEFAULT
_catalogs: dict[str, dict[str, str]] = {}
_reverse: dict[str, dict[str, str]] = {}
_listeners: list[Callable[[str], None]] = []


def _load(code: str) -> dict[str, str]:
    if code == DEFAULT:
        return {}
    if code not in _catalogs:
        from ..paths import assets_dir
        try:
            raw = json.loads((assets_dir() / "i18n" / f"{code}.json").read_text("utf-8"))
            cat = {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str) and v
                   and not k.startswith("_")}
        except (OSError, ValueError):
            cat = {}
        _catalogs[code] = cat
        _reverse[code] = {v: k for k, v in cat.items()}
    return _catalogs[code]


def language() -> str:
    return _current


def set_language(code: str) -> str:
    global _current
    code = code if code in LANGUAGES else DEFAULT
    _load(code)
    changed = code != _current
    _current = code
    if changed:
        for fn in list(_listeners):
            try:
                fn(code)
            except Exception:
                pass
    return code


def on_change(fn: Callable[[str], None]) -> None:
    _listeners.append(fn)


def remove_listener(fn) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def translate(text: str, code: str | None = None) -> str:
    code = code or _current
    if not text or code == DEFAULT:
        return text
    return _load(code).get(text, text)


def source_of(text: str, code: str | None = None) -> str | None:
    code = code or _current
    if code == DEFAULT:
        return text
    _load(code)
    return _reverse.get(code, {}).get(text)


def tr(text: str, **values) -> str:
    out = translate(text)
    if values:
        try:
            return out.format(**values)
        except (KeyError, IndexError, ValueError):
            return text.format(**values)
    return out


def placeholders(text: str) -> set[str]:
    try:
        return {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
    except ValueError:
        return {"<invalid>"}


def is_cjk(code: str | None = None) -> bool:
    return (code or _current) == "ja"
