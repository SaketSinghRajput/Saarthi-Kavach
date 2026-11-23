"""Dead-air work: llm/tts split, early cached filler, reply trim, honest dead_air metric (all stubbed timings)."""
import asyncio

from app import orchestrator as orch_mod
from app.agents.decoy import trim_reply
from app.agents.lyzr_client import LlmReply
from app.bus import EventBus
from app.integrations.tts import TTS
from app.orchestrator import Orchestrator
from tests.test_honest_metrics import _FakeTime, _run


def _events(orch, name):
    return [e for e in orch.bus.since(0) if e["event"] == name]


def test_turn_and_metrics_split_llm_and_tts(settings, fx):
    orch, res = _run(settings, fx, [3000])
    kturns = [t for t in _events(orch, "turn") if t["speaker"] == "kamla"]
    assert kturns and all("llm_ms" in t and "tts_ms" in t for t in kturns)
    assert all(abs(t["llm_ms"] + t["tts_ms"] - t["latency_ms"]) <= 1 for t in kturns)
    m = _events(orch, "metrics")[-1]
    assert m["llm_p95_ms"] >= 3000 - 1 and m["tts_p95_ms"] < 50
    assert res["llm_p95_ms"] == m["llm_p95_ms"] and res["tts_p95_ms"] == m["tts_p95_ms"]


def test_tts_ms_is_measured_separately(settings, fx):
    async def go():
        ft = _FakeTime()
        orch_mod.time = ft
        try:
            o = Orchestrator(settings, fx, EventBus(":memory:"))
            orig = o.tts.synth

            async def slow(text, role):
                if role == "kamla":
                    ft.now += 1.4
                return await orig(text, role)

            o.tts.synth = slow
            o.start("digital_arrest", "scripted")
            await o.wait()
            return o
        finally:
            orch_mod.time = __import__("time")

    o = asyncio.run(go())
    m = _events(o, "metrics")[-1]
    assert m["tts_p95_ms"] >= 1400 - 1 and m["llm_p95_ms"] < 50
    assert m["compute_p95_ms"] >= m["tts_p95_ms"]


def test_dead_air_without_filler_is_compute_plus_pause_no_overlap_credit(settings, fx):
    _, res = _run(settings, fx, [3700, 4100])  # pacing 0: clip overlap is not credited
    assert res["dead_air_p95_ms"] >= 4100 - 1
    assert res["dead_air_p95_ms"] >= res["compute_p95_ms"]


def _slow_live_call(settings, fx, delay_s, speed, mode="ptt"):
    settings.pacing_speed = speed
    settings.ptt_idle_s = 0.4

    async def go():
        orch = Orchestrator(settings, fx, EventBus(":memory:"))
        orig = orch.decoy.reply

        async def slow(*a, **k):
            if delay_s == 0:  # truly instant stub reply (the canned path adds a simulated delay)
                return orch.decoy.fallback(a[4], a[1]), 0
            await asyncio.sleep(delay_s)
            return await orig(*a, **k)

        orch.decoy.reply = slow
        orch.start("fake_kyc", mode)
        await asyncio.sleep(0.05)
        orch.submit_ptt("main customer care se bol rahi hoon, aapka KYC pending hai")
        await orch.wait()
        return orch

    return asyncio.run(go())


def test_filler_after_1_2s_one_per_turn_and_caps_dead_air(settings, fx):
    assert orch_mod.FILLER_AFTER_S <= 1.2
    orch = _slow_live_call(settings, fx, 0.4, 100)  # 0.4 s real stub LLM vs 12 ms scaled filler threshold
    turns = _events(orch, "turn")
    sp = [t["speaker"] for t in turns]
    assert sp[:3] == ["scammer", "filler", "kamla"], sp
    assert sp.count("filler") == sp.count("kamla") == 1  # never two fillers for one Kamla turn
    m = _events(orch, "metrics")[-1]
    # filler plays at threshold (1.2 s / speed), far below the 400 ms real LLM stub
    assert 0 < m["dead_air_p95_ms"] < 0.5 * m["compute_p95_ms"]
    assert m["dead_air_p95_ms"] >= orch_mod.FILLER_AFTER_S * 1000 / 100 - 1


def test_fast_reply_plays_no_filler(settings, fx):
    orch = _slow_live_call(settings, fx, 0.0, 100)
    assert "filler" not in [t["speaker"] for t in _events(orch, "turn")]


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def render(self, text, voice, speed):
        import io
        import wave
        self.calls.append(text)
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\0\0" * 2400)
        return b.getvalue()


def test_prerendered_fillers_are_cache_hits(settings, fx):
    settings.tts_provider = "kokoro"
    tts = TTS(settings)
    tts.engine = _FakeEngine()
    texts = [f["text"] for f in fx["fillers"]]
    assert asyncio.run(tts.prerender(texts)) == len(texts)
    n = len(tts.engine.calls)
    clip = asyncio.run(tts.synth(texts[0], "kamla"))
    assert clip.cache_hit and len(tts.engine.calls) == n  # instant: no render at call time


def test_trim_caps_sentences_and_words():
    t = "Haan beta, ek minute ruko. Main chashma dhoond rahi hoon. Phir aapko bataungi sab kuch."
    assert trim_reply(t) == "Haan beta, ek minute ruko. Main chashma dhoond rahi hoon."
    long = " ".join(["shabd"] * 40) + "."
    out = trim_reply(long)
    assert len(out.split()) <= 22 and out.endswith(".")
    two_long = "Ek do teen char paanch chhe saat aath nau das gyarah barah. Terah chaudah pandrah solah satrah atharah unnees bees ikkees baees teyees chaubees pachchees."
    assert trim_reply(two_long).count(".") == 1  # second sentence dropped to fit 22 words
    short = "Haan beta... ek minute."
    assert trim_reply(short) == short  # ellipsis is not a sentence boundary


def test_trim_never_drops_identifiers():
    t = "Achha beta. Theek hai. Number hai 98765 43210 na?"
    assert trim_reply(t) == t
    u = "Haan beta ji. Main sun rahi hoon. Mera account 000000482195 hai."
    assert trim_reply(u) == u


def test_live_reply_trimmed_but_readback_intact(settings, fx):
    from app.agents.decoy import Decoy

    class _D:
        kind, target, text = "ASK_FOR", None, "x"

    calls = []

    class _L:
        async def kamla(self, *a, **k):
            calls.append(1)
            return LlmReply("Ek. Do. Teen sentence yahan hai.", "lyzr_live", None, 5)

    d = Decoy(fx, _L())
    r, _ = asyncio.run(d.reply("c", 0, [], "hi", _D()))
    assert r.text == "Ek. Do." and r.llm_ms == 5

    class _RB:
        kind, target, text = "READ_BACK", "upi", "x"

    r2, _ = asyncio.run(d.reply("c", 0, [], "hi", _RB(), "scam@upi", 0))
    assert len(calls) == 1  # read-back is code-rendered: no second LLM call, so nothing to trim
