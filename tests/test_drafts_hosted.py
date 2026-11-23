"""Panel round 1 fixes: IFSC format, structured drafts + shared case id, hosted scripted-only, band_mirrored_ok."""
import asyncio
import hashlib
import json
import re

from fastapi.testclient import TestClient

from app.agents.intel.regex import extract
from app.agents.reporter import case_id_for, trim_sentences
from app.agents.verifier import IFSC_RE, Verifier
from app.api import create_app
from app.config import load_settings
from app.contracts import Entity
from tests.conftest import run_call, needs_full_fixture
from tests.test_gates import NAKED_PHONE, drafts_of


def ent(t, v, seq=1):
    return Entity(entity_id="e", call_id="c", type=t, normalized=v, turn_seq=seq)


# ---- IFSC ------------------------------------------------------------------
def test_fixture_ifscs_are_valid_and_resolve(fx):
    for sc in fx["scenarios"].values():
        e = sc["entities"].get("ifsc")
        if e:
            assert len(e["value"]) == 11 and IFSC_RE.match(e["value"])
            r = Verifier(fx).check(ent("ifsc", e["value"]))
            assert r.lookup and "fictional" in r.lookup["bank"].lower()


def test_malformed_ifsc_never_verified(fx):
    v = Verifier(fx)
    for bad in ("DEMO00001234", "DEMO0001", "DEM00000417", "DEMO1000417", "demo0000417"):
        for i in range(3):
            r = v.check(ent("ifsc", bad, i))
        v.confirm("ifsc", bad)
        assert v.get("ifsc", bad).status == "invalid" and not v.is_valid(v.get("ifsc", bad)), bad
    assert extract("ifsc DEMO00001234") == []  # a 12-char code is not truncated into a valid-looking IFSC


# ---- drafts ----------------------------------------------------------------
@needs_full_fixture
def test_drafts_structured_complete_and_share_case_id(settings, fx):
    orch, res = run_call(settings, fx, "fake_investment")
    jid, drafts = drafts_of(orch)
    assert {d.kind for d in drafts} == {"bank_alert", "helpline_1930"}
    ids = set()
    for d in drafts:
        b = d.body_text
        m = re.search(r"Case ID: (SK-\d{8}-[0-9a-f]{6})", b)
        assert m
        ids.add(m.group(1))
        for label in ("Beneficiary account", "IFSC", "UPI handle", "Scammer phone(s)", "Scam type", "Stages observed",
                      "Call start (IST)", "Call ID", "Job ID", "Evidence"):
            assert label in b, label
        assert re.search(r"Call start \(IST\)\s+: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+05:30", b)
        assert f"Call ID             : {d.call_id}" in b and jid in b
        assert "TO BE FILLED BY COMPLAINANT BEFORE SUBMISSION" in b
        for f in ("Complainant name / account", "UTR / transaction reference", "Amount (INR)", "Debit date and time"):
            assert f"{f}: ____" in b
        assert "Request: please review under your own procedures and, if warranted, flag or hold the beneficiary account and UPI handle pending investigation." in b
        assert "(Kavach" in b or "(Saarthi" in b or "Fictional" in b  # IFSC bank resolved
        assert not NAKED_PHONE.search(b) and "(synthetic)" in b
        assert b.startswith(d.watermark) and b.rstrip().endswith(d.watermark)
        assert d.sha256 == hashlib.sha256(b.encode()).hexdigest()
    assert len(ids) == 1
    # evidence is the transcript hash, never transcript text
    with orch.bus.lock:
        turns = [json.loads(r[0]) for r in orch.bus.db.execute(
            "SELECT payload FROM events WHERE type='turn' ORDER BY id").fetchall()]
    want = hashlib.sha256("\n".join(f"{t['speaker']}: {t['text']}" for t in turns).encode()).hexdigest()
    assert f"transcript sha256 {want}" in drafts[0].body_text
    assert not any(t["text"] in drafts[0].body_text for t in turns if len(t["text"]) > 30)
    # the draft event carries the same case_id
    evs = [e for e in orch.bus.since(0) if e["event"] == "draft"]
    assert evs and {e["case_id"] for e in evs} == ids


def test_case_id_deterministic_from_call_id():
    from datetime import datetime, timezone
    t = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)  # 01:30 IST next day
    a = case_id_for("c_abc", t)
    assert a == case_id_for("c_abc", t) and a.startswith("SK-20261124-") and a != case_id_for("c_abd", t)


def test_trim_sentences_never_mid_sentence():
    s = "One sentence here. Two sentence here. " * 40
    out = trim_sentences(s, 100)
    assert len(out) <= 100 and out.endswith(".")
    assert trim_sentences("short.", 100) == "short."
    assert trim_sentences("x" * 200, 50).endswith("...")


# ---- hosted scripted-only ------------------------------------------------------
def test_hosted_scripted_only_defaults(monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "real-pass")
    monkeypatch.delenv("HOSTED_SCRIPTED_ONLY", raising=False)
    assert load_settings().hosted_scripted_only is True
    monkeypatch.setenv("HOSTED_SCRIPTED_ONLY", "false")
    assert load_settings().hosted_scripted_only is False
    monkeypatch.delenv("APP_PASSCODE")
    monkeypatch.delenv("HOSTED_SCRIPTED_ONLY")
    s = load_settings()
    assert s.passcode_is_dev and s.hosted_scripted_only is False


def test_hosted_scripted_only_blocks_live_scammer(settings, fx, monkeypatch):
    from app.orchestrator import Orchestrator
    from app.bus import EventBus
    settings.app_mode, settings.hosted_scripted_only = "live", True
    calls = []

    async def go():
        o = Orchestrator(settings, fx, EventBus(":memory:"))
        monkeypatch.setattr(type(o.lyzr), "live", property(lambda self: True))

        async def boom(*a, **k):
            calls.append(1)
            return "LLM line"
        monkeypatch.setattr(o.lyzr, "scammer", boom)
        assert o.agent_status()["agents"]["scammer"]["mode"] == "scripted"
        o.start("fake_kyc", "scripted")
        await o.wait()
        return o
    o = asyncio.run(go())
    assert calls == []
    turns = [e for e in o.bus.since(0) if e["event"] == "turn" and e["speaker"] == "scammer"]
    assert turns and all(t["source"] == "scripted" for t in turns)


def test_hosted_scripted_only_typed_input_still_works(settings, fx):
    from app.orchestrator import Orchestrator
    from app.bus import EventBus
    settings.hosted_scripted_only = True

    async def go():
        o = Orchestrator(settings, fx, EventBus(":memory:"))
        o.start("fake_kyc", "ptt")
        await asyncio.sleep(0.05)
        assert o.submit_ptt("Main bank se bol raha hoon, aapka KYC expire ho gaya hai")
        await asyncio.sleep(0.3)
        o.kill()
        o.submit_ptt("ok")
        await o.wait()
        return o
    o = asyncio.run(go())
    assert any(e["event"] == "turn" and e["speaker"] == "scammer" and e["source"] == "human_stt"
               for e in o.bus.since(0))


# ---- band_mirrored_ok -----------------------------------------------------------
def test_health_band_last_post_null_before_any_post(settings):
    with TestClient(create_app(settings)) as c:
        h = c.get("/api/health").json()
        assert h["band_last_post"] is None and "band_mirrored_ok" not in h
    settings2 = settings
    assert settings2.band_room_id == ""
