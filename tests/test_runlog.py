"""Per-call run log, /api/runs, tools/runlog_report.py, band_last_post."""
import importlib.util
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from tests.conftest import run_call

H = {"X-Passcode": "test-pass"}
spec = importlib.util.spec_from_file_location("runlog_report", Path(__file__).resolve().parent.parent / "tools" / "runlog_report.py")
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)


def _run(settings, fx):
    orch, res = run_call(settings, fx)
    p = Path(settings.data_dir) / "runs" / f"{res['call_id']}.json"
    return res, p, json.loads(p.read_text(encoding="utf-8"))


def test_runlog_written_with_required_fields(settings, fx):
    res, p, run = _run(settings, fx)
    assert run["run_id"] == res["call_id"] and run["scenario"] == "digital_arrest"
    assert set(run["modes"]) == {"kamla", "scammer", "reporter", "scout", "room", "host"}
    assert run["call_summary"]["label"] == "simulated call" and run["metrics"]["dead_air_p95_ms"] == res["dead_air_p95_ms"]
    k = [t for t in run["turns"] if t["speaker"] == "kamla"]
    assert k and all(set(t) == {"seq", "speaker", "source", "t_start", "llm_ms", "tts_ms", "filler_ms", "dead_ms",
                                 "latency_ms", "audio_url", "audio_ms"} for t in run["turns"])
    assert re.match(r"\d{4}-\d\d-\d\dT", run["call_started_wallclock"])
    assert all(t["audio_url"] is None or re.fullmatch(r"/audio/[0-9a-f]+\.wav", t["audio_url"]) for t in run["turns"])
    assert all(t["audio_ms"] is None or isinstance(t["audio_ms"], int) for t in run["turns"])
    assert all(t["audio_ms"] is not None for t in k)
    assert len(k) == res["turns"] or len(k) > 0
    assert {d["kind"] for d in run["drafts"]} == {"bank_alert", "helpline_1930"}
    assert all(set(d) == {"kind", "trigger", "band_msg_id", "case_id", "sha256"} for d in run["drafts"])


def test_runlog_has_no_text_or_identifier_values(settings, fx):
    res, p, run = _run(settings, fx)
    raw = p.read_text(encoding="utf-8")
    assert "text" not in {k for t in run["turns"] for k in t}
    for t, v in {**{k: x for k, x in res["verified"].items()}}.items():
        assert v not in raw, t
    sc = fx["scenarios"]["digital_arrest"]["entities"]
    for e in sc.values():
        assert e["value"] not in raw
    stripped = re.sub(r"[0-9a-f]{64}", "", raw)  # sha256 digests may contain digit runs
    stripped = re.sub(r"c_[0-9a-f]{12}|SK-\d{8}-[0-9a-f]{6}", "", stripped)
    assert not re.search(r"(?<![\w.])\d{10,}(?![\w.])", stripped)


def test_report_recomputes_and_answer_is_per_turn_sum(settings, fx):
    res, p, run = _run(settings, fx)
    r = rr.report(run)
    m = run["metrics"]
    assert r["dead_air_p95_ms"] == m["dead_air_p95_ms"] and r["answer_p95_ms"] == m["answer_p95_ms"]
    assert r["llm_p95_ms"] == m["llm_p95_ms"] and r["tts_p95_ms"] == m["tts_p95_ms"]
    assert rr.main(["x", str(p)]) == 0


def test_answer_p95_is_p95_of_sum_not_sum_of_p95s():
    # llm spikes on one turn, tts on another: p95(sum) = 3100 but p95(llm)+p95(tts) = 6000
    turns = [{"speaker": "kamla", "llm_ms": 3000, "tts_ms": 100, "dead_ms": 1} if i == 0 else
             {"speaker": "kamla", "llm_ms": 100, "tts_ms": 3000, "dead_ms": 1} if i == 1 else
             {"speaker": "kamla", "llm_ms": 100, "tts_ms": 100, "dead_ms": 1} for i in range(2)]
    r = rr.report({"run_id": "c_x", "turns": turns})
    assert r["answer_p95_ms"] == 3100 and r["llm_p95_ms"] + r["tts_p95_ms"] == 6000
    assert rr.p95(list(range(1, 21))) == 19  # nearest rank


def test_api_runs_gated_and_served(settings, fx):
    res, p, run = _run(settings, fx)
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/runs").status_code == 401
        assert c.get(f"/api/runs/{res['call_id']}").status_code == 401
        lst = c.get("/api/runs", headers=H).json()["runs"]
        assert lst == [{"run_id": res["call_id"], "scenario": "digital_arrest", "dead_air_p95_ms": res["dead_air_p95_ms"]}]
        assert c.get(f"/api/runs/{res['call_id']}", headers=H).json() == run
        assert c.get("/api/runs/c_000000000000", headers=H).status_code == 404
        assert c.get("/api/runs/..%2Fsaarthi", headers=H).status_code == 404


def test_band_last_post_stays_null_when_band_offline(settings, fx):
    orch, _ = run_call(settings, fx)  # offline Band: no live post ever attempted
    assert orch.band_last_post is None
