"""C2 output filter (Kamla, before TTS) and the Reporter narrative post-filter (5.6)."""
from __future__ import annotations

import re

from ..agents.intel.normalise import normalise
from ..agents.intel.regex import UPI_RE, IFSC_RE, extract

SAFE_LINE = "Arre beta, ye sab mujhe samajh nahi aa raha, thoda dheere samjhao."
_SECRET_WORD = re.compile(r"\b(otp|pin|cvv|password)\b(?:\W+\w+){0,3}?\W+\d{4,6}\b")
_UPI_I = re.compile(UPI_RE.pattern, re.I)
_PAN = re.compile(r"\b[a-z]{5}\d{4}[a-z]\b")


def c2_filter(text: str, planted: set[str]) -> tuple[str, int]:
    """Return (safe_text, redaction_count). Allowlist matching is on normalised values.

    Any non-planted account/phone/UPI/IFSC/6+ digit run, PAN or OTP/PIN shape replaces the whole
    line with a neutral in-character one (we never try to repair a leak)."""
    norm = normalise(text)
    bad = 0
    for _t, v, _raw in extract(text):
        if v not in planted:
            bad += 1
    rest = IFSC_RE.sub(" ", UPI_RE.sub(" ", norm))  # digits inside an IFSC/UPI are judged as part of it
    for m in re.finditer(r"\d{6,}", rest):
        if m.group(0) not in planted:
            bad += 1
    if _SECRET_WORD.search(norm) or _PAN.search(norm):
        bad += 1
    return (SAFE_LINE, bad) if bad else (text, 0)


def filter_narrative(text: str, allowed_values: set[str]) -> str:
    """Replace anything the template should own with [redacted]."""
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", "[redacted]", text)  # markdown links
    out = re.sub(r"https?://\S+|www\.\S+", "[redacted]", out)
    out = re.sub(r"\b(approved|verified)\b", "[redacted]", out, flags=re.I)
    out = _UPI_I.sub(lambda m: m.group(0) if m.group(0).lower() in allowed_values else "[redacted]", out)
    out = re.sub(r"\b[A-Za-z]{4}0[A-Za-z0-9]{6}\b", lambda m: m.group(0) if m.group(0).upper() in allowed_values else "[redacted]", out)
    out = re.sub(r"\d{6,}", lambda m: m.group(0) if m.group(0) in allowed_values else "[redacted]", out)
    return out
