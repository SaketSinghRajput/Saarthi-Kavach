"""Spoken-number / spoken-symbol normaliser (ARCHITECTURE 7.1). Pure, no I/O."""
from __future__ import annotations

import re
import unicodedata

DIGIT_WORDS: dict[str, str] = {}
for _d, _ws in {
    "0": "shunya sifar sifr zero oh शून्य सिफ़र सिफर",
    "1": "ek one एक",
    "2": "do two दो",
    "3": "teen three तीन",
    "4": "char chaar four चार",
    "5": "paanch panch five पांच पाँच",
    "6": "chhe chhah cheh chheh six छह छः",
    "7": "saat seven सात",
    "8": "aath eight आठ",
    "9": "nau nine नौ",
}.items():
    for _w in _ws.split():
        DIGIT_WORDS[unicodedata.normalize("NFC", _w)] = _d

MULT = {"double": 2, "dabal": 2, "डबल": 2, "triple": 3, "tripal": 3, "ट्रिपल": 3}
JOINERS = {"dot": ".", "underscore": "_", "dash": "-", "hyphen": "-"}
KNOWN_HANDLES = {"okaxis", "okhdfcbank", "oksbi", "ybl", "paytm", "upi", "ibl", "axl", "kavachtest"}
_DEVA = str.maketrans("०१२३४५६७८९", "0123456789")
_TOKEN = re.compile(r"[^\s,;:।!?()@._\-+]+|[@._\-+]|[,;:।!?()]")
_BREAK = set(",;:।!?().")
SYNTH_RE = re.compile(r"\(\s*synthetic\s*\)", re.I)  # display-only suffix, never part of a value
RUN_MIN = 4  # a run of 4+ digit tokens joins; "do teen din" stays words


def _tokens(text: str) -> list[str]:
    text = SYNTH_RE.sub(" ", unicodedata.normalize("NFC", text)).translate(_DEVA).lower()
    return _TOKEN.findall(text)


def _is_digits(t: str) -> bool:
    return t.isdigit() and t.isascii()


def normalise(text: str) -> str:
    """Return a lowercase working copy: digit runs joined, spoken symbols mapped inside candidate windows."""
    toks = _tokens(text)
    # 1. expand double/triple, mark digit tokens: (display, digits|None)
    items: list[tuple[str, str | None]] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if t in MULT and nxt is not None and (nxt in DIGIT_WORDS or (_is_digits(nxt) and len(nxt) == 1)):
            d = DIGIT_WORDS.get(nxt, nxt)
            items.append((f"{t} {nxt}", d * MULT[t]))
            i += 2
            continue
        if _is_digits(t):
            items.append((t, t))
        elif t in DIGIT_WORDS:
            items.append((t, DIGIT_WORDS[t]))
        else:
            items.append((t, None))
        i += 1
    # 2. join runs of digit tokens (hyphen between digit tokens is a joiner); keep words if run < RUN_MIN
    out: list[str] = []
    i = 0
    while i < len(items):
        if items[i][1] is None:
            out.append(items[i][0])
            i += 1
            continue
        j, digits, shown = i, "", []
        while j < len(items):
            if items[j][1] is not None:
                digits += items[j][1]
                shown.append(items[j][0])
                j += 1
            elif items[j][0] == "-" and j + 1 < len(items) and items[j + 1][1] is not None and digits:
                j += 1
            else:
                break
        out.extend([digits] if len(digits) >= RUN_MIN else " ".join(shown).split(" "))
        i = j
    # 3. spoken symbols: "at the rate" / "at <handle>" -> @ ; then dot/underscore/dash near an @
    sym: list[str] = []
    i = 0
    while i < len(out):
        if out[i:i + 3] == ["at", "the", "rate"]:
            sym.append("@")
            i += 3
        elif out[i] == "at" and i + 1 < len(out) and out[i + 1] in KNOWN_HANDLES:
            sym.append("@")
            i += 1
        else:
            sym.append(out[i])
            i += 1
    at_pos = [k for k, t in enumerate(sym) if t == "@"]
    for k, t in enumerate(sym):
        if t in JOINERS and any(0 < a - k <= 8 for a in at_pos):
            sym[k] = JOINERS[t]
    # 4. assemble local@handle
    res: list[str] = []
    k = 0
    while k < len(sym):
        t = sym[k]
        if t == "@" and res and k + 1 < len(sym) and re.fullmatch(r"[a-z][a-z0-9]*", sym[k + 1]) and re.fullmatch(r"[a-z0-9]+", res[-1] or "-"):
            local = res.pop()
            while len(res) >= 2 and res[-1] in (".", "_", "-") and re.fullmatch(r"[a-z0-9]+", res[-2]):
                local = res[-2] + res[-1] + local
                del res[-2:]
            res.append(f"{local}@{sym[k + 1]}")
            k += 2
            continue
        res.append(t)
        k += 1
    # 5. four single letters followed by a 7-digit run starting with 0 -> spelled IFSC ("d e m o 0000417")
    fin: list[str] = []
    k = 0
    while k < len(res):
        if (k + 4 < len(res) and all(len(x) == 1 and x.isalpha() for x in res[k:k + 4])
                and _is_digits(res[k + 4]) and len(res[k + 4]) == 7 and res[k + 4].startswith("0")):
            fin.append("".join(res[k:k + 4]))
            k += 4
            continue
        fin.append(res[k])
        k += 1
    return " ".join(fin)
