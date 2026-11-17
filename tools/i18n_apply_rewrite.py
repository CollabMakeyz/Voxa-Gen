from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "i18n"
sys.path.insert(0, str(ROOT / "tools"))
from i18n_extract import decode, encode

MANUAL = {"pt_BR": "pt_BR.part5.txt", "es": "es.part4.txt", "ja": "ja.part4.txt"}


def replace_literals(old_to_new: dict[str, str]) -> int:
    changed = 0
    for path in sorted((ROOT / "voxagen").rglob("*.py")):
        text = path.read_text("utf-8")
        tree = ast.parse(text)
        joined = {id(c) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for c in ast.walk(n)}
        hits = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value in old_to_new and id(n) not in joined]
        if not hits:
            continue
        lines = text.splitlines(keepends=True)
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line.encode("utf-8")))
        raw = text.encode("utf-8")
        for n in sorted(hits, key=lambda n: (n.lineno, n.col_offset), reverse=True):
            a = starts[n.lineno - 1] + n.col_offset
            b = starts[n.end_lineno - 1] + n.end_col_offset
            raw = raw[:a] + repr(old_to_new[n.value]).encode("utf-8") + raw[b:]
            changed += 1
        new_text = raw.decode("utf-8")
        ast.parse(new_text)
        path.write_text(new_text, "utf-8")
    return changed


def set_lines(files: list[Path], num: str, text: str, fallback: Path) -> None:
    for f in files:
        lines = f.read_text("utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith(num + "|"):
                lines[i] = f"{num}|{encode(text)}"
                f.write_text("\n".join(lines) + "\n", "utf-8")
                return
    with open(fallback, "a", encoding="utf-8") as fh:
        fh.write(f"{num}|{encode(text)}\n")


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    src_path = SRC / "sources_v1.txt"
    src = {l.split("|", 1)[0]: decode(l.split("|", 1)[1]) for l in src_path.read_text("utf-8").splitlines() if "|" in l}
    old_to_new = {src[n]: d["en"] for n, d in data.items() if "en" in d}
    print("code literals replaced:", replace_literals(old_to_new))
    for n, d in data.items():
        if "en" in d:
            set_lines([src_path], n, d["en"], src_path)
        for code, part in MANUAL.items():
            if code in d:
                files = [SRC / f"{code}.txt"] + sorted(SRC.glob(f"{code}.part*.txt"))
                set_lines(files, n, d[code], SRC / part)
    print("entries:", len(data))


if __name__ == "__main__":
    main()
