"""Additive event fields: skill, band t_ms/band_msg_id, entity resolved_by/upi_psp, agent_status, reporter skills line."""
import asyncio
import hashlib

from fastapi.testclient import TestClient

from app.api import create_app
from app.integrations import band_mirror
from app.integrations.band_mirror import BandMirror, _msg_id
from app.orchestrator import upi_psp
from tests.conftest import run_call


def _events(settings, fx, kind, scenario="digital_arrest"):
    orch, _ = run_call(settings, fx, scenario)
    return orch, [e for e in orch.bus.since(0) if e["event"] == kind]


def test_skill_event_has_catalogue_fields(settings, fx):
    _, evs = _events(settings, fx, "skill")
    assert evs
    e = evs[0]
    assert e["role"] == "discovery_only" and isinstance(e["total"], int)
    assert {"name", "source", "slug", "category", "free", "summary"} <= set(e["skills"][0])
    assert {"live", "query"} <= set(e)


def test_band_events_have_t_ms_and_null_msg_id_offline(settings, fx):
    _, evs = _events(settings, fx, "band")
    assert evs and all("t_ms" in e and e["band_msg_id"] is None for e in evs)
    ts = [e["t_ms"] for e in evs]
    assert all(isinstance(t, int) and t >= 0 for t in ts) and ts == sorted(ts)
    assert ts[-1] > 0  # handoff comes after the call audio


class _Resp:
    def __init__(self, body, code=200):
        self._b, self.status_code = body, code

    def json(self):
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


def test_msg_id_parse_is_lenient():
    assert _msg_id(_Resp({"id": "m1"})) == "m1"
    assert _msg_id(_Resp({"message_id": 42})) == "42"
    assert _msg_id(_Resp({"messageId": "x"})) == "x"
    assert _msg_id(_Resp({"data": {"id": "n9"}})) == "n9"
    assert _msg_id(_Resp({"ok": True})) is None
    assert _msg_id(_Resp(ValueError("not json"))) is None
    assert _msg_id(_Resp([1, 2])) is None


_PARTS = {"data": [
    {"id": "u-kamla", "handle": "own/kamla", "name": "Kamla", "type": "Agent"},
    {"id": "u-rep", "handle": "own/reporter", "name": "Reporter", "type": "Agent"},
    {"id": "u-human", "handle": "own", "name": "Saket", "type": "User"}]}


def _fake_band(calls, post_status=200):
    async def fake(method, url, s, **kw):
        calls.append((method, url, kw.get("json")))
        if method == "GET":
            return _Resp(_PARTS)
        r = _Resp({"data": {"id": "bm_7"}})
        r.status_code = post_status
        return r
    return fake


def test_band_post_ex_body_shape_and_id(settings, monkeypatch):
    settings.band_enabled, settings.band_room_id = True, "room1"
    settings.band_keys = {"kamla": "k"}
    calls = []
    monkeypatch.setattr(band_mirror.egress, "request", _fake_band(calls))
    bm = BandMirror(settings)
    text = "report job rj_0123456789ab ready"
    assert asyncio.run(bm.post_ex("kamla", "reporter", text, "handoff")) == (True, "bm_7")
    posts = [c for c in calls if c[0] == "POST"]
    assert posts[0][1].endswith("/chats/room1/messages")
    assert posts[0][2] == {"message": {"content": "@reporter " + text, "mentions": [
        {"id": "u-rep", "handle": "own/reporter", "name": "Reporter"}]}}
    assert asyncio.run(bm.post("kamla", None, "hi", "post")) is True  # no target -> mentions the human
    assert [c for c in calls if c[0] == "POST"][1][2]["message"]["mentions"][0]["id"] == "u-human"
    assert len([c for c in calls if c[0] == "GET"]) == 1  # participants cached
    assert asyncio.run(bm.post_ex("saarthi", None, "hi", "post")) == (False, None)  # no key
    assert asyncio.run(bm.post_ex("kamla", "kamla", "hi", "post")) == (False, None)  # cannot mention self
    assert asyncio.run(bm.post_ex("kamla", "ghost", "hi", "post")) == (False, None)  # unknown peer


def test_band_4xx_not_retried(settings, monkeypatch):
    settings.band_enabled, settings.band_room_id = True, "room1"
    settings.band_keys = {"kamla": "k"}
    calls = []
    monkeypatch.setattr(band_mirror.egress, "request", _fake_band(calls, post_status=422))
    assert asyncio.run(BandMirror(settings).post_ex("kamla", "reporter", "x", "post")) == (False, None)
    assert len([c for c in calls if c[0] == "POST"]) == 1


def test_upi_psp_map():
    assert upi_psp("a@okaxis") == "Axis (PSP)"
    assert upi_psp("a@ybl") == "PhonePe/Yes (PSP)"
    assert upi_psp("a@paytm") == "Paytm (PSP)"
    assert upi_psp("a@oksbi") == "SBI (PSP)"
    assert upi_psp("a@ibl") == "ICICI (PSP)"
    assert upi_psp("a@zzz") is None and upi_psp("nohandle") is None


def test_entity_resolved_by(settings, fx):
    _, evs = _events(settings, fx, "entity")
    upis = [e for e in evs if e["type"] == "upi"]
    ifs = [e for e in evs if e["type"] == "ifsc" and e.get("ifsc_bank")]
    assert upis and ifs
    assert all(e["resolved_by"] == "action_agent:upi_psp_lookup" and "upi_psp" in e for e in upis)
    assert all(e["resolved_by"] == "action_agent:ifsc_lookup" for e in ifs)
    assert all("resolved_by" not in e for e in evs if e["type"] in ("phone", "bank_account"))


def test_agent_status_stub_by_default(settings, fx):
    orch, evs = _events(settings, fx, "agent_status")
    assert evs
    a = evs[0]["agents"]
    assert set(a) == {"kamla", "scammer", "reporter", "scout", "room", "host"}
    assert a["kamla"] == {"platform": "Lyzr", "mode": "stub"}
    assert a["reporter"]["platform"] == "AdaL" and a["room"]["platform"] == "Band"
    assert a["host"] == {"platform": "local", "mode": "stub"}
    assert a["scammer"]["mode"] == "scripted"  # tests run with a real passcode, so the hosted guard is on
    assert all(v["mode"] in ("live", "stub", "scripted") for v in a.values())
    assert a["scout"]["mode"] == "stub"  # snapshot, not live


def test_agent_status_modes_follow_settings(settings, fx):
    from app.bus import EventBus
    from app.orchestrator import Orchestrator
    settings.lyzr_api_key, settings.lyzr_user_id, settings.lyzr_agent_kamla = "k", "u", "a"
    settings.agent37_instance = "inst1"
    settings.band_room_id, settings.band_keys = "r", {"kamla": "k"}
    settings.adal_enabled, settings.adal_provider_key = True, "p"
    settings.finch_enabled = True
    settings.hosted_scripted_only = False  # this test is about the non-hosted vocabulary
    a = Orchestrator(settings, fx, EventBus(":memory:")).agent_status()["agents"]
    assert a["kamla"]["mode"] == "live" and a["scammer"]["mode"] == "stub"  # scammer live needs app_mode live
    assert a["host"] == {"platform": "Agent37", "mode": "live"}
    assert a["room"]["mode"] == "live" and a["reporter"]["mode"] == "live" and a["scout"]["mode"] == "live"
    settings.band_keys = {}
    settings.adal_provider_key = ""
    settings.adal_bin = "definitely-not-installed-adal"
    b = Orchestrator(settings, fx, EventBus(":memory:")).agent_status()["agents"]
    assert b["room"]["mode"] == "stub" and b["reporter"]["mode"] == "stub"


def test_api_state_exposes_agent_status(settings, fx):
    with TestClient(create_app(settings)) as c:
        st = c.get("/api/state", headers={"X-Passcode": "test-pass"}).json()
    assert set(st["agent_status"]["agents"]) == {"kamla", "scammer", "reporter", "scout", "room", "host"}


def test_drafts_carry_skills_line_and_sha_matches(settings, fx):
    orch, skill_evs = _events(settings, fx, "skill")
    names = ", ".join(s["name"] for s in skill_evs[0]["skills"])
    drafts = [e for e in orch.bus.since(0) if e["event"] == "draft"]
    assert drafts
    line = "Related skills discovered via Finch catalogue (discovery only, not executed): " + names
    for d in drafts:
        assert line in d["body"]
        assert d["body"].rstrip().endswith(d["watermark"])
        assert d["sha256"] == hashlib.sha256(d["body"].encode("utf-8")).hexdigest()
        assert d["body"].startswith(d["watermark"])


def test_no_skills_line_without_skill_event(settings, fx):
    from app.agents.reporter import skills_line
    assert skills_line([]) == []
