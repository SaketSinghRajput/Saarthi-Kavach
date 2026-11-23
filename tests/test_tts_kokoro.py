import asyncio
import io
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import prerender_tts  # noqa: E402

from app.fixtures import load_fixtures  # noqa: E402
from app.integrations import tts as tts_mod  # noqa: E402
from app.integrations.hinglish import to_devanagari  # noqa: E402


def _wav(ms=500):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24 * ms))
    return b.getvalue()


class FakeEngine:
    def __init__(self):
        self.calls = []

    def render(self, text, voice, speed):
        tts_mod.check_voice(voice)
        self.calls.append((text, voice, speed))
        return _wav()


@pytest.fixture
def kokoro(settings, monkeypatch):
    eng = FakeEngine()
    settings.tts_provider = "kokoro"
    monkeypatch.setattr(tts_mod, "_make_engine", lambda s: eng)
    return tts_mod.TTS(settings), eng


def test_kokoro_renders_with_allowlisted_voices_and_caches(kokoro):
    t, eng = kokoro
    k = asyncio.run(t.synth("Theek hai beta", "kamla"))
    s = asyncio.run(t.synth("Namaste ji", "scammer"))
    assert (k.voice, s.voice) == ("hf_beta", "hm_psi") and k.live and not k.cache_hit
    assert k.url.endswith(".wav") and (t.cache / k.url.rsplit("/", 1)[-1]).exists()
    assert k.duration_ms == pytest.approx(500, abs=5)
    assert [c[2] for c in eng.calls] == [0.85, 1.05]
    k2 = asyncio.run(t.synth("Theek hai beta", "kamla"))
    assert k2.cache_hit and k2.url == k.url and len(eng.calls) == 2


def test_cache_key_depends_on_voice_and_text():
    assert tts_mod.clip_key("hf_beta", "a") != tts_mod.clip_key("hm_psi", "a")
    assert tts_mod.clip_key("hf_beta", "a") != tts_mod.clip_key("hf_beta", "b")


@pytest.mark.parametrize("bad", ["hf_alpha", "hm_omega", "af_heart", "../../x", "", "HF_BETA"])
def test_allowlist_rejects_other_voices(bad):
    with pytest.raises(tts_mod.VoiceNotAllowed):
        tts_mod.check_voice(bad)
    with pytest.raises(tts_mod.VoiceNotAllowed):
        tts_mod.KokoroEngine("nowhere").render("x", bad, 1.0)


def test_misconfigured_voice_disables_kokoro_and_falls_back_to_stub(settings, monkeypatch):
    settings.tts_provider = "kokoro"
    settings.tts_voice_kamla = "hf_alpha"
    eng = FakeEngine()
    monkeypatch.setattr(tts_mod, "_make_engine", lambda s: eng)
    t = tts_mod.TTS(settings)
    c = asyncio.run(t.synth("Namaste", "kamla"))
    assert not t.live and c.url is None and c.voice == "stub" and eng.calls == []


def test_falls_back_to_stub_when_kokoro_not_installed(settings, monkeypatch):
    monkeypatch.setitem(sys.modules, "kokoro", None)  # import would fail
    settings.tts_provider = "kokoro"
    t = tts_mod.TTS(settings)
    c = asyncio.run(t.synth("Namaste ji", "scammer"))
    assert t.engine is None and not t.live
    assert c.url is None and c.live is False and c.duration_ms >= 900


def test_engine_failure_falls_back_for_that_line(kokoro):
    t, eng = kokoro
    eng.render = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
    c = asyncio.run(t.synth("Namaste", "kamla"))
    assert c.url is None and not c.live


def test_devanagari_conversion_matches_bakeoff_style():
    assert to_devanagari("UPI ID likhiye: rathore dot demo at the rate kavachtest.") == \
        "यू पी आई आईडी लिखिए: राठौर डॉट डेमो एट द रेट कवचटेस्ट।"
    assert to_devanagari("ठीक है बेटा") == "ठीक है बेटा"  # already Devanagari: unchanged
    assert to_devanagari("zzq kopa")  # unknown words never raise or come back empty


def test_prerender_collects_scripted_lines_for_all_scenarios(settings):
    fx = load_fixtures(settings.fixtures_path)
    lines = prerender_tts.collect_lines(fx)
    assert len(lines) == len(set(lines)) > 60
    assert {r for r, _ in lines} == {"kamla", "scammer"}
    assert not any("{" in t for _, t in lines)
    texts = {t for _, t in lines}
    for sc in fx["scenarios"].values():
        assert all(b["text"] in texts for b in sc["beats"])
