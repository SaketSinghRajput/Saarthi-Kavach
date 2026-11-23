"""Detector rules (5.2): sole owner of scam_type, stage and risk. Pure Python, sync, a few ms."""
from __future__ import annotations

import re

from ..contracts import DetectorResult

TYPE_MIN_SCORE = 2
PAY_ONLY_MIN_SCORE = 4
STAGE_ORDER = ["unknown", "hook", "authority", "urgency", "payment_ask", "pressure"]


class Detector:
    def __init__(self, fx: dict, call_id: str):
        self.lex = fx["detector_lexicon"]
        self.call_id = call_id
        self.seen: set[tuple[str, str]] = set()
        self.type_scores: dict[str, int] = {}
        self.type_seen: set[tuple[str, str]] = set()
        self.stage = "unknown"
        self.scam_type = "unknown"
        self.risk = 0.0
        self.coercion = False
        self.pay_seen = False
        self.advisory = False

    @staticmethod
    def _has(text: str, kw: str) -> bool:
        return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text) is not None

    def update(self, text: str, seq: int) -> DetectorResult:
        t = text.lower()
        signals: list[str] = []
        turn_cats: list[str] = []
        weights = self.lex["category_weights"]
        weak = set(self.lex.get("weak_words", []))  # generic words (account, pay, link) count for less
        wf = self.lex.get("weak_factor", 1.0)
        self.advisory = self.advisory or any(self._has(t, m) for m in self.lex.get("advisory_markers", []))
        for cat, kws in self.lex["categories"].items():
            for kw in kws:
                if self._has(t, kw):
                    if cat == "pressure" and STAGE_ORDER.index(self.stage) < STAGE_ORDER.index("payment_ask"):
                        continue  # pressure means a payment ask after a stall
                    turn_cats.append(cat)
                    if (cat, kw) not in self.seen:
                        self.seen.add((cat, kw))
                        self.risk += weights[cat] * (wf if kw in weak else 1.0)
                        signals.append(f"{cat}:{kw}"[:40])
        self.risk = min(1.0, round(self.risk, 4))
        for cat in turn_cats:  # stage never goes backwards
            if STAGE_ORDER.index(cat) > STAGE_ORDER.index(self.stage):
                self.stage = cat
        # coercion = a threat or an authority claim; a bill / card / parcel word alone is never enough
        self.coercion = self.coercion or any(c in ("authority", "urgency", "pressure") for c in turn_cats)
        self.pay_seen = self.pay_seen or "payment_ask" in turn_cats
        strong = self.lex.get("scam_types_strong", {})
        for st, kws in self.lex["scam_types"].items():  # strong phrases weigh 2, weak ones 1
            for kw, w in [(k, 2) for k in strong.get(st, [])] + [(k, 1) for k in kws if k not in strong.get(st, [])]:
                if self._has(t, kw) and (st, kw) not in self.type_seen:
                    self.type_seen.add((st, kw))
                    self.type_scores[st] = self.type_scores.get(st, 0) + w
        if self.type_scores:
            best = max(self.type_scores, key=lambda k: self.type_scores[k])
            # a payment ask also counts when the evidence is strong (investment pitches rarely threaten)
            ok = self.coercion or (self.pay_seen and self.type_scores[best] >= PAY_ONLY_MIN_SCORE)
            if ok and self.type_scores[best] >= TYPE_MIN_SCORE and (
                    self.scam_type == "unknown" or self.type_scores[best] > self.type_scores.get(self.scam_type, 0)):
                self.scam_type = best
        risk = self._final_risk()
        if self.advisory:  # an awareness message ("never share your OTP") is not a scam call
            return DetectorResult(call_id=self.call_id, turn_seq=seq, risk=risk, scam_type="unknown",
                                  stage=self.stage, signals=signals[:10], is_scam_likely=False)
        return DetectorResult(call_id=self.call_id, turn_seq=seq, risk=risk, scam_type=self.scam_type,
                              stage=self.stage, signals=signals[:10], is_scam_likely=risk >= 0.6)

    def _final_risk(self) -> float:
        """Additive keyword risk plus a corroboration bonus: several independent phrases of ONE scam type
        (not just generic words) are stronger evidence than the same count of mixed hits."""
        c = self.lex.get("corroboration")
        risk = self.risk
        if c and self.scam_type != "unknown":
            pts = self.type_scores.get(self.scam_type, 0) - c["free_points"]
            risk += min(c["cap"], max(0, pts) * c["per_point"])
        if c and self.advisory:
            risk = min(risk, c["advisory_cap"])
        return min(1.0, round(risk, 4))
