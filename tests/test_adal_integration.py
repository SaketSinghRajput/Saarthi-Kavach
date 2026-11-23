"""AdaL CLI integration: output parsing, env allow-list, bin path, out-of-credits fallback, multi-host proxy."""
import asyncio
import json
import os

from app.agents.reporter import ADAL_ENV_ALLOW, adal_env, parse_adal_output, resolve_adal_bin
from app.safety.adal_proxy import AdalProxy
from tests.conftest import run_call
from tests.test_gates import drafts_of
from app.agents.reporter import Reporter

CREDITS = "You're out of credits. Add credits or upgrade at https://adal.sylph.ai/settings/billing."


def test_parse_json_answer_key():
    raw = json.dumps({"success": True, "answer": "Neutral summary.", "error": None, "exit_code": 0})
    assert parse_adal_output(raw) == ("Neutral summary.", None)
    assert parse_adal_output(json.dumps(json.loads(raw), indent=2)) == ("Neutral summary.", None)  # pretty-printed


def test_parse_json_out_of_credits():
    one = json.dumps({"success": False, "answer": None, "error": CREDITS})
    assert parse_adal_output(one) == (None, CREDITS)


def test_parse_stream_json_error_and_final():
    err_stream = '{"type":"error","message":"%s"}\n{"type":"complete","exit_code":1}\n' % CREDITS
    assert parse_adal_output(err_stream) == (None, CREDITS)
    ok_stream = ('{"type":"assistant","text":"partial"}\n{"type":"result","success":true,"answer":"Final text."}\n'
                 '{"type":"complete","exit_code":0}\n')
    assert parse_adal_output(ok_stream) == ("Final text.", None)


def test_env_allow_list_has_no_other_secrets(monkeypatch):
    monkeypatch.setenv("LYZR_API_KEY", "secret-lyzr")
    monkeypatch.setenv("TTS_API_KEY", "secret-tts")
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    env = adal_env("pk", "http://127.0.0.1:9999")
    assert set(env) <= set(ADAL_ENV_ALLOW) | {"ADAL_PROVIDER_KEY", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"}
    assert env["SYSTEMROOT"] == r"C:\Windows" and env["ADAL_PROVIDER_KEY"] == "pk"
    assert "secret-lyzr" not in env.values() and "secret-tts" not in env.values()
    assert env["NO_PROXY"] == "localhost,127.0.0.1"


def test_resolve_bin_accepts_full_path(tmp_path):
    f = tmp_path / "adal.cmd"
    f.write_text("@echo off")
    assert resolve_adal_bin(str(f)) == str(f)
    assert resolve_adal_bin(str(tmp_path / "missing.cmd")) is None


def _job(settings, fx):
    orch, _ = run_call(settings, fx, "digital_arrest")
    jid, _ = drafts_of(orch)
    settings.adal_enabled, settings.adal_allowed_host = True, "adal.sylph.ai,clerk.adal.sylph.ai"
    return orch, orch.reporter.get_job(jid)


def test_answer_key_and_cmd_flags_through_reporter(settings, fx):
    orch, job = _job(settings, fx)
    seen = {}

    async def runner(cmd, env, cwd, timeout):
        seen["cmd"] = cmd
        return 0, json.dumps({"success": True, "answer": "A neutral narrative."}).encode()

    rep = Reporter(orch.bus, settings, adal_runner=runner)
    assert asyncio.run(rep._adal_narrative(job)) == "A neutral narrative."
    c = seen["cmd"]
    assert c[c.index("--disabled-default-tools") + 1] == "Bash,Edit,Web,Image,Video,Consult" and "--yolo" not in c


def test_out_of_credits_falls_back_to_template_with_policy_event(settings, fx):
    orch, job = _job(settings, fx)

    async def runner(cmd, env, cwd, timeout):
        return 1, json.dumps({"success": False, "answer": None, "error": CREDITS * 5}).encode()

    rep = Reporter(orch.bus, settings, adal_runner=runner)
    assert asyncio.run(rep._adal_narrative(job)) is None
    ev = [e for e in orch.bus.since(0) if e["event"] == "policy" and e["kind"] == "adal_unavailable"]
    assert ev and "out of credits" in ev[0]["detail"] and len(ev[0]["detail"]) <= 200
    # run_job falls back to the template narrative
    rep2 = Reporter(orch.bus, settings, adal_runner=runner)
    drafts = asyncio.run(rep2.run_job(job.job_id, "test")) if not rep2.drafts_for(job.job_id) else rep2.drafts_for(job.job_id)
    assert all(d.narrative_source == "template" for d in drafts)


def test_proxy_multi_host_allow_list():
    async def go():
        p = AdalProxy("adal.sylph.ai, Clerk.adal.sylph.ai")
        assert p.hosts == {"adal.sylph.ai", "clerk.adal.sylph.ai"}
        await p.start()
        for tgt in ("evil.example:443", "d35qg8ac0yw4p7.cloudfront.net:443", "adal.sylph.ai:8080"):
            r, w = await asyncio.open_connection("127.0.0.1", p.port)
            w.write(f"CONNECT {tgt} HTTP/1.1\r\n\r\n".encode())
            await w.drain()
            assert b"403" in await r.readline()
            w.close()
        await p.stop()
        return p.denied

    assert len(asyncio.run(go())) == 3


def test_parse_real_stream_json_answer_event():
    """Shape captured from the live AdaL CLI 1.11.15 on 2026-11-23."""
    from app.agents.reporter import parse_adal_output
    raw = ('{"type":"answer","content":"A neutral narrative."}\n'
           '{"type":"complete","exit_code":0,"session_id":"s","model":"google-gemini-3.8-flash"}\n')
    assert parse_adal_output(raw) == ("A neutral narrative.", None)
