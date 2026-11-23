"""Regex candidate extraction (ARCHITECTURE 7.2). Runs on the raw and the normalised text."""
from __future__ import annotations

import re

from .normalise import SYNTH_RE, normalise

UPI_RE = re.compile(r"(?<![a-z0-9._\-])([a-z0-9][a-z0-9.\-_]{1,255})@([a-z]{2,64})(?![a-z0-9])")
IFSC_RE = re.compile(r"(?<![a-z0-9])([a-z]{4})\s?(0[a-z0-9]{6})(?![a-z0-9])")
DIGITS_RE = re.compile(r"(?<![\d])(\d{9,18})(?![\d])")
PHONE_RE = re.compile(r"(?<![\d])((?:\+?91[\s-]?)?0?[6-9]\d{9})(?![\d])")


def _clean_phone(s: str) -> str:
    return re.sub(r"[^\d]", "", s)[-10:]


def extract(text: str) -> list[tuple[str, str, str]]:
    """-> [(type, normalised_value, raw_span)], deduped, in order of appearance."""
    found: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(t: str, v: str, raw: str) -> None:
        if (t, v) not in seen:
            seen.add((t, v))
            found.append((t, v, raw[:120]))

    text = SYNTH_RE.sub(" ", text)
    for src in (text.lower(), normalise(text)):
        for m in UPI_RE.finditer(src):
            add("upi", f"{m.group(1)}@{m.group(2)}", m.group(0))
        for m in IFSC_RE.finditer(src):
            add("ifsc", (m.group(1) + m.group(2)).upper(), m.group(0))
        for m in PHONE_RE.finditer(src):
            add("phone", _clean_phone(m.group(1)), m.group(0))
        for m in DIGITS_RE.finditer(src):
            v = m.group(1)
            if re.fullmatch(r"(?:0|91)?[6-9]\d{9}", v):
                continue  # a valid phone shape is a phone, not an account
            add("bank_account", v, v)
    return found
