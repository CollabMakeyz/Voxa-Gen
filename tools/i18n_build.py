from __future__ import annotations

import json
import re
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "i18n"
OUT = ROOT / "assets" / "i18n"
sys.path.insert(0, str(ROOT / "tools"))
from i18n_extract import decode

PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def read_lines(path: Path) -> dict[int, str]:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text("utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        num, _, text = line.partition("|")
        if num.strip().isdigit():
            out[int(num)] = decode(text)
    return out


def sources() -> dict[int, str]:
    return read_lines(SRC / "sources_v1.txt")


def manual(code: str) -> dict[int, str]:
    out = read_lines(SRC / f"{code}.txt")
    for part in sorted(SRC.glob(f"{code}.part*.txt")):
        out.update(read_lines(part))
    return out


def placeholders(s: str) -> list[str]:
    try:
        return sorted(f for _, f, _, _ in string.Formatter().parse(s) if f is not None)
    except ValueError:
        return ["<invalid>"]


def _protect(text: str):
    keep = []

    def sub(m):
        keep.append(m.group(0))
        return f"\x00{len(keep) - 1}\x00"
    t = re.sub(r"\{[^{}]*\}|\*\.[a-z0-9]+|#[0-9A-Fa-f]{6}|Ctrl\+\w+", sub, text)
    return t, keep


def _restore(text: str, keep: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)


def _words(text: str, table: dict[str, str]) -> str:
    def rep(m):
        w = m.group(0)
        low = w.lower()
        if low not in table:
            return w
        r = table[low]
        if w.isupper() and len(w) > 1:
            return r.upper()
        if w[0].isupper():
            return r[0].upper() + r[1:]
        return r
    pattern = r"\b(" + "|".join(sorted((re.escape(k) for k in table), key=len, reverse=True)) + r")\b"
    return re.sub(pattern, rep, text, flags=re.IGNORECASE)


PT_PT_WORDS = {
    "arquivo": "ficheiro", "arquivos": "ficheiros", "tela": "ecrã", "telas": "ecrãs", "usuário": "utilizador",
    "usuários": "utilizadores", "salvar": "guardar", "salvo": "guardado", "salva": "guardada", "salvos": "guardados",
    "salvas": "guardadas", "salve": "guarde", "salvando": "a guardar", "salvá-lo": "guardá-lo", "time": "equipa",
    "trem": "comboio", "registro": "registo", "registros": "registos", "ônibus": "autocarro", "você": "você",
    "baixar": "transferir", "mouse": "rato", "deletar": "eliminar", "apagar": "eliminar", "apague": "elimine",
    "apagado": "eliminado", "tchau": "adeus", "legal": "fixe", "detecção": "deteção", "detectada": "detetada",
    "detectado": "detetado", "detectar": "detetar", "detecta": "deteta", "detectadas": "detetadas",
    "detectados": "detetados", "ótimo": "ótimo", "contato": "contacto", "fato": "facto", "seção": "secção",
    "projeto": "projeto", "atualizar": "atualizar", "aperte": "carregue em", "apertar": "carregar em",
    "clique duas vezes": "faça duplo clique", "ícone": "ícone", "planilha": "folha de cálculo", "cadastro": "registo",
    "renderizar": "renderizar", "pra": "para",
}
GERUND = re.compile(r"\b([A-Za-zÀ-ÿ]+?)(ando|endo|indo)\b")
_GERUND_KEEP = {"quando", "comando", "comandos", "fundo", "segundo", "segundos", "mundo", "lindo", "vindo",
                "tendo", "sendo", "estando", "grande", "brando", "bando", "lando", "fazendo", "vendo"}


def _gerund(m):
    word = m.group(0)
    if word.lower() in _GERUND_KEEP:
        return {"tendo": "a ter", "sendo": "a ser", "fazendo": "a fazer", "vendo": "a ver",
                "estando": "a estar"}.get(word.lower(), word)
    stem, end = m.group(1), m.group(2)
    inf = stem + {"ando": "ar", "endo": "er", "indo": "ir"}[end]
    return ("A " if word[0].isupper() else "a ") + inf.lower()


def to_pt_pt(text: str) -> str:
    t, keep = _protect(text)
    t = _words(t, PT_PT_WORDS)
    t = GERUND.sub(_gerund, t)
    t = re.sub(r"\b([Aa]) a ", r"\1 ", t)
    t = t.replace("Ouça", "Oiça").replace("ouça", "oiça").replace("ouvi-los", "ouvi-los")
    return _restore(t, keep)


SLANG_WORDS = {
    "muito": "muito", "você": "tu", "seus": "teus", "suas": "tuas", "seu": "teu", "sua": "tua",
    "exportação concluída": "exportou, show de bola", "erro": "deu ruim", "atenção": "se liga",
    "concluído": "feito", "cancelado": "cancelado", "ótimo": "massa", "rápido": "ligeiro",
    "sample": "sample", "samples": "samples", "aguarde": "segura aí", "espere": "segura aí",
    "nenhum": "nenhum", "tudo bem": "de boa", "recomendado": "a boa é", "dica": "papo reto",
    "talvez": "pode ser", "começar": "começar", "pronto": "prontinho", "problema": "treta",
    "problemas": "tretas", "apagar": "apagar", "salvar": "salvar",
}


def to_slang(text: str) -> str:
    t, keep = _protect(text)
    t = _words(t, SLANG_WORDS)
    t = re.sub(r"\btu (\w+)a\b", r"tu \1a", t)
    t = t.replace("Você", "Tu")
    return _restore(t, keep)


PIRATE_WORDS = {
    "you": "ye", "your": "yer", "yours": "yers", "you're": "ye be", "my": "me", "is": "be", "are": "be",
    "the": "th'", "hello": "ahoy", "yes": "aye", "no": "nay", "friend": "matey", "friends": "hearties",
    "folder": "chest", "folders": "chests", "file": "scroll", "files": "scrolls", "export": "plunder",
    "exports": "plunders", "exported": "plundered", "exporting": "plunderin'", "save": "stow", "saved": "stowed",
    "delete": "scuttle", "deleted": "scuttled", "remove": "toss overboard", "error": "blunder", "errors": "blunders",
    "settings": "riggin'", "setting": "riggin'", "cancel": "belay", "cancelled": "belayed", "stop": "avast",
    "open": "crack open", "find": "hunt fer", "search": "scour", "for": "fer", "of": "o'", "and": "an'",
    "to": "t'", "with": "wi'", "before": "afore", "nothing": "naught", "everything": "all th' booty",
    "money": "doubloons", "load": "haul", "loaded": "hauled", "samples": "shanties", "sample": "shanty",
    "voice": "voice", "quickly": "smartly", "window": "porthole", "queue": "fleet", "jobs": "voyages",
    "job": "voyage", "warning": "ill omen", "done": "done, arr", "attention": "ahoy",
}


def to_pirate(text: str) -> str:
    t, keep = _protect(text)
    t = _words(t, PIRATE_WORDS)
    t = re.sub(r"\b(\w{3,})ing\b", r"\1in'", t)
    return _restore(t, keep)


CAT_WORDS = {
    "now": "meow", "new": "mew", "perfect": "purrfect", "perfectly": "purrfectly", "please": "pleaseow",
    "export": "meowxport", "exports": "meowxports", "exported": "meowxported", "exporting": "meowxporting",
    "error": "hairball", "errors": "hairballs", "cancel": "knock it off", "cancelled": "knocked off the table",
    "warning": "ears up", "attention": "ears up", "done": "done, purr", "finished": "finished, purr",
    "save": "stash", "saved": "stashed", "delete": "knock off the table",
    "deleted": "knocked off the table", "folder": "box", "folders": "boxes", "file": "yarn ball",
    "files": "yarn balls", "noise": "purring", "queue": "line of kittens", "job": "hunt", "jobs": "hunts",
    "search": "sniff out", "find": "sniff out", "start": "stretch", "fast": "fast as a cat",
    "slow": "lazy", "project": "nest", "projects": "nests", "friend": "furriend", "friends": "furriends",
    "about": "abowt", "mouse": "mousie", "listen": "perk your ears", "fur": "fur",
}


def to_cat(text: str) -> str:
    t, keep = _protect(text)
    t = _words(t, CAT_WORDS)
    t = re.sub(r"\bper", "purr", t)
    t = re.sub(r"\bPer", "Purr", t)
    stripped = t.rstrip()
    if len(stripped.split()) >= 6 and stripped.endswith(".") and "\x00" not in stripped[-3:]:
        t = stripped[:-1] + ", meow."
    return _restore(t, keep)


DERIVED = {
    "pt_PT": ("pt_BR", to_pt_pt),
    "pt_BR_slang": ("pt_BR", to_slang),
    "en_pirate": ("en", to_pirate),
    "cat": ("en", to_cat),
}


def build() -> None:
    src = sources()
    OUT.mkdir(parents=True, exist_ok=True)
    built: dict[str, dict[int, str]] = {"en": dict(src)}
    for code in ("pt_BR", "es", "ja"):
        built[code] = manual(code)
    for code, (base, fn) in DERIVED.items():
        base_map = built[base]
        derived = {i: fn(t) for i, t in base_map.items()}
        derived.update(read_lines(SRC / f"{code}.overrides.txt"))
        built[code] = derived
    for code, table in built.items():
        if code == "en":
            continue
        out, bad = {}, []
        for i, text in table.items():
            if i not in src:
                continue
            en = src[i]
            if placeholders(en) != placeholders(text):
                bad.append(i)
                continue
            out[en] = text
        meta = {"_language": code, "_entries": len(out), "_sources": len(src)}
        (OUT / f"{code}.json").write_text(json.dumps({**meta, **out}, ensure_ascii=False, indent=0), "utf-8")
        print(f"{code}: {len(out)}/{len(src)} entries" + (f", {len(bad)} dropped (placeholders): {bad[:12]}" if bad else ""))


if __name__ == "__main__":
    build()
