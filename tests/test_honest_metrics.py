"""Honesty: HUD latency must include real Kamla compute; scout status/liveness must mirror the real scout result."""
import asyncio
import time as real_time

from app import orchestrator as orch_mod
from app.bus import EventBus
from app.orchestrator import Orchestrator


class _FakeTime:
    """perf_counter is a manual clock; everything else is the real time module."""

    def __init__(self):
        self.now = 0.0

    def perf_counter(self):
        return self.now

    def __getattr__(self, name):
        return getattr(real_time, name)


def _run(settings, fx, latencies_ms, scout=None):
    ft = _FakeTime()
    orch_mod.time = ft
    try:
        orch = Orchestrator(settings, fx, EventBus(":memory:"))
        orig, it = orch.decoy.reply, iter(latencies_ms)

        async def slow_reply(*a, **k):
            ft.now += next(it, latencies_ms[-1]) / 1000  # stubbed real Lyzr compute
            return await orig(*a, **k)

        orch.decoy.reply = slow_reply
        if scout is not None:
            orch.finch.scout = scout

        async def go():
            orch.start("digital_arrest", "scripted")
            return await orch.wait()

        return orch, asyncio.run(go())
    finally:
        orch_mod.time = real_time


def test_hud_p95_includes_real_compute(settings, fx):
    _, res = _run(settings, fx, [3700, 4100])
    assert res["compute_p95_ms"] >= 4100 - 1
    assert res["substantive_p95_ms"] >= res["compute_p95_ms"] >= 3700
    assert res["substantive_p95_ms"] > 3500  # would be flagged over the 3.5 s budget, not hidden


def test_metrics_event_never_below_compute(settings, fx):
    orch, _ = _run(settings, fx, [3700, 4100, 3900])
    ms = [e for e in orch.bus.since(0) if e["event"] == "metrics"]
    assert ms and all(m["substantive_p95_ms"] >= m["compute_p95_ms"] >= 3700 for m in ms)
    turns = [e for e in orch.bus.since(0) if e["event"] == "turn" and e["speaker"] == "kamla"]
    assert max(t["latency_ms"] for t in turns) <= ms[-1]["compute_p95_ms"]


def _scout_stub(live):
    async def scout(scam_type):
        return {"skills": [{"name": "x", "slug": "x", "category": "c", "free": True, "summary": "",
                            "source": "finch_live" if live else "finch_snapshot"}],
                "live": live, "query": "scam", "total": 1, "role": "discovery_only"}
    return scout


def test_scout_status_live_only_when_result_live(settings, fx):
    settings.finch_enabled = True
    orch, _ = _run(settings, fx, [10], scout=_scout_stub(False))
    assert orch.agent_status()["agents"]["scout"]["mode"] == "stub"
    orch, _ = _run(settings, fx, [10], scout=_scout_stub(True))
    assert orch.agent_status()["agents"]["scout"]["mode"] == "live"


def test_slow_scout_does_not_stall_call_and_still_publishes(settings, fx):
    settings.finch_enabled = True

    async def slow(scam_type):
        await asyncio.sleep(0.3)
        return await _scout_stub(True)(scam_type)

    orch, res = _run(settings, fx, [10], scout=slow)
    skills = [e for e in orch.bus.since(0) if e["event"] == "skill"]
    assert res["turns"] > 1 and len(skills) == 1 and skills[0]["live"] is True
