"""Deterministic verifier (C4). Code only: no LLM, nothing from Band or the transcript decides status."""
from __future__ import annotations

import re

from ..contracts import Entity, VerifiedEntity
from ..fixtures import planted_values

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCT_RE = re.compile(r"^\d{9,18}$")
UPI_RE = re.compile(r"^[a-z0-9.\-_]{2,256}@[a-z]{2,64}$")


def normalise_phone(v: str) -> str:
    d = re.sub(r"[^\d]", "", v)
    if d.startswith("91") and len(d) == 12:
        d = d[2:]
    if d.startswith("0") and len(d) == 11:
        d = d[1:]
    return d


class Verifier:
    def __init__(self, fx: dict, demo_synthetic_only: bool = True):
        self.fx = fx
        self.demo_only = demo_synthetic_only
        self.planted = planted_values(fx)
        self.handles = set(fx["upi_handles"])
        self.store: dict[tuple[str, str], VerifiedEntity] = {}

    # -- format + lookup -------------------------------------------------
    def _check_format(self, t: str, v: str):
        reasons: list[str] = []
        lookup = None
        handle_ok = None
        if t == "phone":
            ok = bool(PHONE_RE.match(v))
        elif t == "ifsc":
            ok = bool(IFSC_RE.match(v))
            if ok:
                bank = self.fx["ifsc_banks"].get(v[:4])
                if bank:
                    lookup = {"bank": bank["bank"], "branch": bank["branch"], "fictional": True}
                else:
                    reasons.append("unknown bank code")
        elif t == "bank_account":
            ok = (bool(ACCT_RE.match(v)) and len(set(v)) > 1
                  and not PHONE_RE.match(v) and not PHONE_RE.match(normalise_phone(v)))
        elif t == "upi":
            ok = bool(UPI_RE.match(v))
            if ok:
                handle_ok = v.rsplit("@", 1)[1] in self.handles
                ok = handle_ok
                if not handle_ok:
                    reasons.append("handle not allowlisted")
        else:
            ok = False
        if not ok:
            reasons.append("format check failed")
        return ok, reasons, lookup, handle_ok

    def check(self, e: Entity) -> VerifiedEntity:
        """Register one sighting of a candidate and return its current verified record."""
        t = e.type
        v = normalise_phone(e.normalized) if t == "phone" else e.normalized
        key = (t, v)
        prev = self.store.get(key)
        ok, reasons, lookup, handle_ok = self._check_format(t, v)
        planted = v in self.planted
        ve = prev or VerifiedEntity(call_id=e.call_id, type=t, value=v, status="unverified", confidence="low",
                                    first_turn=e.turn_seq, last_turn=e.turn_seq)
        ve.heard_count += 1
        ve.last_turn = e.turn_seq
        ve.lookup = lookup
        ve.checks = {"format": ok, "planted_match": planted, "handle_allowlisted": handle_ok,
                     "dedup_of": f"{t}:{v}" if prev else None}
        ve.reasons = list(reasons)
        self._grade(ve, ok, planted)
        self.store[key] = ve
        return ve

    def _grade(self, ve: VerifiedEntity, fmt_ok: bool, planted: bool) -> None:
        if not fmt_ok:
            ve.status, ve.confidence = "invalid", "low"
            return
        if self.demo_only and not planted:
            ve.status, ve.confidence = "unverified", "low"
            ve.reasons.append("not planted")
            return
        if ve.readback_confirmed:
            ve.status, ve.confidence = "verified", "high"
        elif ve.heard_count >= 2:
            ve.status, ve.confidence = "verified", "medium"
        else:
            ve.status, ve.confidence = "unverified", "medium"

    def is_valid(self, ve: VerifiedEntity) -> bool:
        """Valid format and (planted, in synthetic-only mode): allowed to reach a read-back."""
        return bool(ve.checks.get("format")) and (bool(ve.checks.get("planted_match")) or not self.demo_only)

    def confirm(self, t: str, v: str):
        ve = self.store.get((t, v))
        if ve:
            ve.readback_confirmed = True
            self._grade(ve, bool(ve.checks.get("format")), bool(ve.checks.get("planted_match")))
        return ve

    def get(self, t: str, v: str):
        return self.store.get((t, v))
