"""Steering loop (section 6): phase 1 updates state, phase 2 selects exactly one directive. Deterministic."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from ..contracts import Directive, VerifiedEntity
from .verifier import Verifier

PRIORITY = ["upi", "bank_account", "ifsc", "phone"]
AFFIRM = {"haan", "haa", "ji", "sahi", "correct", "yes", "bilkul", "theek"}
NEGATE = {"nahi", "nahin", "galat", "no", "wrong"}
RISK_THRESHOLD = 0.6
NO_PROGRESS_LIMIT = 8


@dataclass
class Goal:
    status: str = "missing"  # missing|suspect|heard|confirmed|given_up
    value: Optional[str] = None
    ask_attempts: int = 0
    readback_attempts: int = 0
    method_failed_used: bool = False


@dataclass
class SteerState:
    goals: dict
    pending_readback: Optional[str] = None
    turns_without_progress: int = 0
    wrapup_stalls_left: Optional[int] = None
    end_reason: Optional[str] = None
    turn_seq: int = 0
    recent: list = field(default_factory=list)
    tactic_bump: int = 0
    active_directive: Optional[Directive] = None

    def snapshot(self) -> dict:
        return {t: {"status": g.status, "value": g.value, "ask_attempts": g.ask_attempts,
                    "readback_attempts": g.readback_attempts, "method_failed_used": g.method_failed_used}
                for t, g in self.goals.items()}


def new_state(goal_set: list) -> SteerState:
    return SteerState(goals={t: Goal() for t in sorted(goal_set, key=PRIORITY.index)})


def _words(text: str) -> set:
    return set(re.findall(r"[a-z]+", text.lower()))


class Steering:
    def __init__(self, fx: dict, verifier: Verifier, max_turns: int = 30, max_seconds: float = 300.0):
        self.fx, self.verifier = fx, verifier
        self.max_turns, self.max_seconds = max_turns, max_seconds

    # ---- phase 1: state update -----------------------------------------
    def update(self, st: SteerState, scammer_text: str, candidates: list) -> None:
        st.turn_seq += 1
        before = {t: (g.status, g.value) for t, g in st.goals.items()}
        words = _words(scammer_text)
        st.recent = (st.recent + [scammer_text])[-3:]

        # 1. read-back result
        x = st.pending_readback
        if x and x in st.goals:
            g = st.goals[x]
            conflicting = [c for c in candidates if c.type == x and c.value != g.value]
            if (words & NEGATE) or conflicting:
                g.readback_attempts += 1
            elif words & AFFIRM:
                g.status = "confirmed"
                self.verifier.confirm(x, g.value)
            else:
                g.readback_attempts += 1
            st.pending_readback = None

        # 2. merge candidates (each already passed through the Verifier)
        for c in candidates:
            g = st.goals.get(c.type)
            if g is None or g.status in ("confirmed", "given_up"):
                continue
            if self.verifier.is_valid(c):
                g.status, g.value = "heard", c.value
            elif g.status == "missing":
                g.status, g.value = "suspect", c.value

        # 3. close exhausted goals
        for g in st.goals.values():
            if g.status == "heard" and g.readback_attempts >= 2:
                g.status = "given_up"
            elif g.status in ("missing", "suspect") and g.ask_attempts >= 3 and g.method_failed_used:
                g.status = "given_up"

        # 4. progress counter
        changed = any((g.status, g.value) != before[t] for t, g in st.goals.items())
        st.turns_without_progress = 0 if changed else st.turns_without_progress + 1

    # ---- phase 2: select one directive ---------------------------------
    def _directive(self, st: SteerState, kind: str, target, idx: int = 0) -> Directive:
        tactics = self.fx["tactics"][kind]
        tac = tactics[(idx + st.tactic_bump) % len(tactics)]
        label = self.fx["target_labels"][target]["en"] if target else ""
        d = Directive(directive_id="d_" + uuid.uuid4().hex[:10], kind=kind, target=target,
                      tactic_id=tac["tactic_id"], text=tac["text"].replace("{target_label}", label)[:240])
        st.active_directive = d
        return d

    @staticmethod
    def _repeating(st: SteerState) -> bool:
        r = st.recent
        return len(r) == 3 and all(SequenceMatcher(None, r[i], r[i + 1]).ratio() > 0.9 for i in range(2))

    def select(self, st: SteerState, risk: float, stage: str, elapsed_s: float = 0.0, kill: bool = False) -> Directive:
        if self._repeating(st):
            st.tactic_bump += 1
        goals = st.goals
        ordered = [t for t in PRIORITY if t in goals]

        # 1. guards
        reason = ("kill_switch" if kill else "max_turns" if st.turn_seq >= self.max_turns
                  else "max_duration" if elapsed_s >= self.max_seconds
                  else "no_progress" if st.turns_without_progress >= NO_PROGRESS_LIMIT else None)
        if reason:
            st.end_reason = reason
            return self._directive(st, "WRAP_UP", None)
        # 2. low risk
        if risk < RISK_THRESHOLD:
            return self._directive(st, "NEUTRAL", None)
        # 3. read back a heard goal (line is rendered by code, no LLM)
        for t in ordered:
            if goals[t].status == "heard":
                st.pending_readback = t
                return self._directive(st, "READ_BACK", t, goals[t].readback_attempts)
        # 4. suspect goals
        for t in ordered:
            g = goals[t]
            if g.status == "suspect" and g.ask_attempts < 3:
                g.ask_attempts += 1
                return self._directive(st, "REPEAT", t, g.ask_attempts)
        # 5. still in the pitch
        if stage in ("hook", "authority", "urgency"):
            return self._directive(st, "STALL", None, st.turn_seq)
        # 6. ask for missing goals
        for t in ordered:
            g = goals[t]
            if g.status == "missing" and g.ask_attempts < 3:
                g.ask_attempts += 1
                return self._directive(st, "ASK", t, g.ask_attempts - 1)
        # 7. method failed, once per goal
        for t in ordered:
            g = goals[t]
            if g.status in ("missing", "suspect") and g.ask_attempts >= 3 and not g.method_failed_used:
                g.method_failed_used = True
                return self._directive(st, "METHOD_FAILED", t)
        # 8. everything resolved: waste two more turns, then wrap up
        if all(g.status in ("confirmed", "given_up") for g in goals.values()):
            if st.wrapup_stalls_left is None:
                st.wrapup_stalls_left = 2
            if st.wrapup_stalls_left > 0:
                st.wrapup_stalls_left -= 1
                return self._directive(st, "STALL", None, st.turn_seq)
            st.end_reason = "all_resolved"
            return self._directive(st, "WRAP_UP", None)
        # 9. otherwise
        return self._directive(st, "STALL", None, st.turn_seq)
