import asyncio
import sys
import time
from pathlib import Path

import pytest

from app.integrations import finch_scout
from app.integrations.finch_scout import FinchScout
from app.safety import egress

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import preflight  # noqa: E402


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http")

    def json(self):
        return self._d


ITEM = {"name": "onlam", "slug": "onlam_finchip", "category": "Security Audit",
        "summary": "x" * 300, "price": {"atomic": "0", "decimals": 18}}


def scout_for(settings, fx):
    settings.finch_enabled = True
    return FinchScout(settings, fx)


def test_first_keyword_empty_second_used(settings, fx, monkeypatch):
    calls = []

    async def fake(method, url, s, **kw):
        calls.append(kw["params"]["q"])
        if kw["params"]["q"] == "scam":
            return Resp({"items": [], "totalCount": 0, "nextCursor": None})
        return Resp({"items": [ITEM], "totalCount": 7, "nextCursor": None})

    monkeypatch.setattr(egress, "request", fake)
    res = asyncio.run(scout_for(settings, fx).scout("digital_arrest"))
    assert calls == ["scam", "fraud"]
    assert res["live"] and res["query"] == "fraud" and res["total"] == 7 and res["role"] == "discovery_only"
    sk = res["skills"][0]
    assert sk["slug"] == "onlam_finchip" and sk["free"] is True and sk["source"] == "finch_live"
    assert len(sk["summary"]) <= 100


def test_paid_or_missing_price_not_marked_free(settings, fx, monkeypatch):
    async def fake(method, url, s, **kw):
        return Resp({"items": [dict(ITEM, price={"atomic": "5"}), {"name": "b"}], "totalCount": 2})

    monkeypatch.setattr(egress, "request", fake)
    res = asyncio.run(scout_for(settings, fx).scout("fake_kyc"))
    assert [k["free"] for k in res["skills"]] == [False, False]


def test_all_empty_falls_back_to_snapshot(settings, fx, monkeypatch):
    async def fake(method, url, s, **kw):
        return Resp({"items": [], "totalCount": 0})

    monkeypatch.setattr(egress, "request", fake)
    res = asyncio.run(scout_for(settings, fx).scout("fake_investment"))
    assert res["live"] is False and res["role"] == "discovery_only"
    assert res["skills"] and all(k["source"] == "finch_snapshot" for k in res["skills"])


def test_exception_falls_back_to_snapshot(settings, fx, monkeypatch):
    async def boom(method, url, s, **kw):
        raise ConnectionError("down")

    monkeypatch.setattr(egress, "request", boom)
    res = asyncio.run(scout_for(settings, fx).scout("digital_arrest"))
    assert res["live"] is False and res["skills"]


def test_disabled_makes_no_call(settings, fx, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("network used while disabled")

    monkeypatch.setattr(egress, "request", boom)
    settings.finch_enabled = False
    assert asyncio.run(FinchScout(settings, fx).scout("digital_arrest"))["live"] is False


def test_time_budget_is_overall_not_per_call(settings, fx, monkeypatch):
    monkeypatch.setattr(finch_scout, "BUDGET_S", 0.3)

    async def slow(method, url, s, **kw):
        await asyncio.sleep(0.2)
        return Resp({"items": []})

    monkeypatch.setattr(egress, "request", slow)
    t0 = time.monotonic()
    res = asyncio.run(scout_for(settings, fx).scout("digital_arrest"))  # 3 keywords x 0.2s = 0.6s unbudgeted
    assert time.monotonic() - t0 < 0.55 and res["live"] is False


def test_each_scam_type_has_ordered_keywords(fx):
    for st in ("digital_arrest", "fake_kyc", "fake_investment"):
        assert 2 <= len(fx["finch_keywords"][st]) <= 3
    assert all(s["note"].startswith("snapshot 2026-11-23") for s in fx["finch_snapshot"])


def test_preflight_s1_needs_online_and_uses_settings_budget(settings, monkeypatch):
    settings.lyzr_api_key = settings.lyzr_user_id = settings.lyzr_agent_kamla = "x"

    def no_post(*a, **k):
        raise AssertionError("paid call without --online")

    monkeypatch.setattr(preflight, "_post", no_post)
    r = preflight.s1_lyzr_latency(settings)
    assert r["status"] == "skip" and "--online" in r["detail"]
    assert settings.lyzr_turn_budget_s == 3.5


def test_preflight_tts_kokoro_ok_without_key(settings, monkeypatch):
    from app.integrations import tts
    settings.tts_provider = "kokoro"
    monkeypatch.setattr(tts.KokoroEngine, "available", staticmethod(lambda d: True))
    assert preflight.s2_tts(settings)["status"] == "ok"
    settings.tts_provider = "elevenlabs"
    assert preflight.s2_tts(settings)["status"] == "skip"  # cloud still needs keys


def test_preflight_agent37(settings, monkeypatch):
    assert preflight.agent37_check(settings, True)["status"] == "skip"
    settings.agent37_url = "https://abc.agent37.app"
    assert preflight.agent37_check(settings, False)["status"] == "skip"
    seen = []
    monkeypatch.setattr(preflight.httpx, "get", lambda url, **k: seen.append(url) or Resp({}, 200))
    assert preflight.agent37_check(settings, True)["status"] == "ok"
    assert seen == ["https://abc.agent37.app/api/health"]
