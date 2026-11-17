from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "assets" / "i18n"
sys.path.insert(0, str(ROOT / "tools"))

TELLS = {
    "en": r"\b(additionally|furthermore|moreover|seamless\w*|ensur\w+|simply|effortless\w*|perfectly|crucial|robust|"
          r"leverag\w+|showcas\w+|vibrant|it'?s (important|worth)|in order to|note that|whether you)\b",
    "pt": r"\b(além disso|adicionalmente|ademais|garant\w+|simplesmente|perfeitamente|de forma \w+|facilmente|crucial|"
          r"robust\w+|sem esforço|vale (a pena )?(notar|ressaltar)|é importante|a fim de|seja você)\b",
    "es": r"\b(además|adicionalmente|asimismo|garantiz\w+|simplemente|perfectamente|de forma \w+|fácilmente|crucial|"
          r"robust\w+|sin esfuerzo|cabe (destacar|señalar)|es importante|con el fin de)\b",
    "ja": r"(さらに|加えて|簡単に|完全に|確実に|ことができます|シームレス|重要です|ぜひ)",
}
CLOSER = {
    "en": r"[,;] so (the|you|it|every|nothing|a|notes?|the app)\b",
    "pt": r"[,;] (então|assim|para que) ",
    "es": r"[,;] (así que|por lo que|para que|de modo que) ",
    "ja": r"(ので、|ため、)",
}
FAMILY = {"en": "en", "en_pirate": "en", "cat": "en", "pt_BR": "pt", "pt_PT": "pt", "pt_BR_slang": "pt",
          "es": "es", "ja": "ja"}
SENT = re.compile(r"(?<=[.!?。！？])\s*")


def catalog(code: str) -> list[str]:
    if code == "en":
        from i18n_extract import decode
        return [decode(l.split("|", 1)[1]) for l in (ROOT / "tools" / "i18n" / "sources_v1.txt")
                .read_text("utf-8").splitlines() if "|" in l]
    data = json.loads((CAT / f"{code}.json").read_text("utf-8"))
    return [v for k, v in data.items() if not k.startswith("_")]


def measure(code: str) -> dict:
    fam = FAMILY[code]
    texts = catalog(code)
    long = [t for t in texts if len(t) > 60]
    tell = re.compile(TELLS[fam], re.I)
    closer = re.compile(CLOSER[fam], re.I)
    sents = [s for t in long for s in SENT.split(t) if s.strip()]
    lens = [len(s) for s in sents]
    burst = statistics.pstdev(lens) / statistics.mean(lens) if lens else 0.0
    return {
        "entries": len(texts),
        "long": len(long),
        "tells": sum(len(tell.findall(t)) for t in texts),
        "dashes": sum(t.count("—") + t.count("–") for t in texts),
        "closers": sum(len(closer.findall(t)) for t in texts),
        "burstiness": round(burst, 3),
    }


def main() -> None:
    codes = ["en", "pt_BR", "pt_PT", "pt_BR_slang", "es", "ja", "en_pirate", "cat"]
    now = {c: measure(c) for c in codes}
    before = None
    if "--compare" in sys.argv:
        before = json.loads(Path(sys.argv[sys.argv.index("--compare") + 1]).read_text("utf-8"))
    head = f"{'lang':12s} {'entries':>7s} {'long':>5s} {'tells':>9s} {'dashes':>9s} {'closers':>9s} {'burst':>11s}"
    print(head)
    for c in codes:
        m = now[c]
        if before:
            b = before[c]
            cell = lambda k, w=9: f"{b[k]}→{m[k]}".rjust(w)
            print(f"{c:12s} {m['entries']:7d} {m['long']:5d} {cell('tells')} {cell('dashes')} {cell('closers')} "
                  f"{cell('burstiness', 11)}")
        else:
            print(f"{c:12s} {m['entries']:7d} {m['long']:5d} {m['tells']:9d} {m['dashes']:9d} {m['closers']:9d} "
                  f"{m['burstiness']:11.3f}")
    if "--save" in sys.argv:
        Path(sys.argv[sys.argv.index("--save") + 1]).write_text(json.dumps(now, indent=1), "utf-8")


if __name__ == "__main__":
    main()
