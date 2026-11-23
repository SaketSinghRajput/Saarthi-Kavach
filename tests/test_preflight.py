import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import preflight  # noqa: E402


def test_spikes_skip_cleanly_without_keys(settings):
    for fn in (preflight.s1_lyzr_latency, preflight.s2_tts, preflight.s3_band_post):
        r = fn(settings)
        assert r["status"] == "skip" and r["key_present"] is False


def test_run_default_has_no_failures_and_no_network(settings):
    res = preflight.run(set(), online=False)
    assert {r["status"] for r in res} <= {"skip"}
