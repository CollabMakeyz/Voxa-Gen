from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [
    "voxagen/ui/**/*.py",
    "voxagen/core/effects/*.py",
    "voxagen/core/samples/analyzer.py",
    "voxagen/core/samples/library.py",
    "voxagen/core/presets/manager.py",
    "voxagen/core/pitch/detect.py",
    "voxagen/core/audio/pipeline.py",
    "voxagen/core/audio/engines/*.py",
    "voxagen/core/export/exporter.py",
    "voxagen/core/export/batch.py",
    "voxagen/core/sequences/order.py",
    "voxagen/core/projects/project.py",
    "voxagen/models/app_settings.py",
]
SKIP_FILES = {"voxagen/ui/i18n_qt.py"}
LABEL_CALLS = {"label", "button", "hint", "Badge", "QCheckBox", "QPushButton", "QLabel", "tr", "setText", "addItem",
               "row", "Card", "Param", "HelpButton"}
CAMEL = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+$")
NOT_TEXT = re.compile(r"^(#|\*\.|Q[A-Z]|\.|/|\\\\|https?:|[a-z_]+\.[a-z]+$|%|\{t\.|<|\[\^|[A-Z0-9_]+$"
                      r"|[a-z]\d? ([a-z]\d? )+[a-z]\d?$)")


def _is_docstring(node, parents) -> bool:
    p = parents.get(node)
    if isinstance(p, ast.Expr):
        gp = parents.get(p)
        if isinstance(gp, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            return gp.body and gp.body[0] is p
    return False


def _call_name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def extract() -> list[str]:
    out: dict[str, None] = {}
    files = sorted({p for pat in SOURCES for p in ROOT.glob(pat)})
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if rel in SKIP_FILES:
            continue
        tree = ast.parse(f.read_text("utf-8"))
        parents = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n):
                parents[c] = n
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
                continue
            v = n.value
            p = parents.get(n)
            if isinstance(p, ast.JoinedStr) or _is_docstring(n, parents):
                continue
            if isinstance(p, ast.Subscript) or (isinstance(p, ast.Compare)):
                continue
            if isinstance(p, ast.Call) and _call_name(p) in ("call", "getattr", "setattr", "hasattr", "property",
                                                              "setProperty", "setObjectName", "connect", "get",
                                                              "findData", "startswith", "endswith", "replace",
                                                              "icon", "tool_button", "round_button"):
                if not (_call_name(p) == "tool_button" and p.args[1:2] == [n]) and                         not (_call_name(p) == "round_button" and p.args[1:2] == [n]):
                    continue
            if isinstance(p, ast.keyword) and p.arg not in ("text", "label", "help", "title", "tip", "tooltip"):
                continue
            if not re.search(r"[A-Za-z]", v) or len(v) > 900 or NOT_TEXT.match(v) or "{t." in v or "{{" in v:
                continue
            if "\n" in v and ":" in v and "{" in v and ";" in v:
                continue
            stripped = v.strip()
            if " " not in stripped:
                owner = p if isinstance(p, ast.Call) else parents.get(p)
                named = isinstance(owner, ast.Call) and _call_name(owner) in ("Effect", "Param", "Preset")
                if (CAMEL.match(stripped) and not named) or stripped.isupper() and len(stripped) <= 4:
                    continue
                if not stripped[0].isupper() and not any(ord(ch) > 127 for ch in stripped):
                    call = p if isinstance(p, ast.Call) else None
                    if call is None or _call_name(call) not in LABEL_CALLS or call.args[:1] != [n]:
                        continue
            if re.fullmatch(r"[a-z0-9_]+(:[a-z0-9_]+)?", stripped):
                if not (isinstance(p, ast.Call) and _call_name(p) in {"label", "button", "hint", "tr", "QCheckBox",
                                                                      "QLabel", "QPushButton"}):
                    continue
            out[v] = None
    return list(out)


def encode(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n")


def decode(s: str) -> str:
    return re.sub(r"\\(\\|n)", lambda m: "\n" if m.group(1) == "n" else "\\", s)


def main() -> None:
    strings = extract()
    d = ROOT / "assets" / "i18n"
    d.mkdir(parents=True, exist_ok=True)
    if "--check" in sys.argv:
        for cat in sorted(d.glob("*.json")):
            data = json.loads(cat.read_text("utf-8"))
            missing = [s for s in strings if s not in data]
            print(f"{cat.stem}: {len(missing)} missing of {len(strings)}")
            for m in missing[:40]:
                print("   ", encode(m)[:110])
        return
    (ROOT / "tools" / "i18n" / "_extracted.txt").write_text("".join(f"{i:04d}|{encode(s)}\n" for i, s in enumerate(strings)), "utf-8")
    print(len(strings), "strings,", sum(len(s) for s in strings), "characters")


if __name__ == "__main__":
    main()
