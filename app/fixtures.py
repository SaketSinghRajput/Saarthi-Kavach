"""Fixture loader and the synthetic-data helpers (G1, C2 allowlist)."""
from __future__ import annotations

import json
import re
from functools import lru_cache

PHONE_SHAPE = re.compile(r"(?<!\w)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\w)(?!\s*\(synthetic\))")


@lru_cache(maxsize=4)
def load_fixtures(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tag_phones(text: str) -> str:
    """G1: every phone number shown anywhere carries the inline suffix '(synthetic)'."""
    return PHONE_SHAPE.sub(lambda m: m.group(0) + " (synthetic)", text)


def planted_values(fx: dict) -> set[str]:
    """All planted entity values (incl. correction variants), as normalised strings."""
    out: set[str] = set()
    for sc in fx["scenarios"].values():
        for e in sc["entities"].values():
            out.add(e["value"])
            if e.get("variant"):
                out.add(e["variant"]["value"])
    return out


def spoken_form(value: str, etype: str, fx: dict) -> str:
    """Hinglish rendering of a planted value for the code-rendered read-back (round-trips the normaliser)."""
    words = fx["digit_words_hi"]
    if etype == "upi":
        local, _, handle = value.partition("@")
        return " ".join(local.replace(".", " dot ").replace("_", " underscore ").split()) + " at the rate " + handle
    if etype == "ifsc":
        return " ".join(list(value[:4])) + " " + " ".join(words[int(c)] if c.isdigit() else c for c in value[4:])
    return " ".join(words[int(c)] for c in value if c.isdigit())
