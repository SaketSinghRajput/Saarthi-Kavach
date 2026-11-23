"""10 consecutive offline runs at PACING_SPEED=0, rotating scenarios. DoD: >= 9/10 extraction."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SAARTHI_NO_DOTENV"] = "1"
os.environ["PACING_SPEED"] = "0"
os.environ["APP_MODE"] = "semi"
for k in ("LYZR_API_KEY", "TTS_API_KEY", "DETECTIFAI_API_KEY", "ADAL_ENABLED", "FINCH_ENABLED"):
    os.environ.pop(k, None)  # run10 is the offline, deterministic extraction check
for k in [k for k in os.environ if k.startswith("BAND_KEY_")]:
    os.environ.pop(k)
os.environ["BAND_ROOM_ID"] = ""

from app.bus import EventBus  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.fixtures import load_fixtures  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402

SCENARIOS = ["digital_arrest", "fake_kyc", "fake_investment"]


async def one(i: int, tmp: str) -> dict:
    s = load_settings()
    s.data_dir, s.db_path = tmp, str(Path(tmp) / f"run{i}.db")
    fx = load_fixtures(s.fixtures_path)
    orch = Orchestrator(s, fx, EventBus(s.db_path))
    key = SCENARIOS[i % 3]
    orch.start(key, "scripted")
    res = await orch.wait()
    planted = {t: e["value"] for t, e in fx["scenarios"][key]["entities"].items()}
    got = res.get("verified", {})
    hit = sum(1 for t, v in planted.items() if got.get(t) == v)
    drafts = orch.reporter.drafts_for(next(iter(_jobs(orch)), ""))
    return {"i": i + 1, "scenario": key, "score": f"{hit}/{len(planted)}", "turns": res.get("turns"),
            "minutes": res.get("minutes_wasted"), "end": res.get("end_reason"), "drafts": len(drafts),
            "c2": res.get("c2_redactions"), "ok": hit == len(planted) and len(drafts) == 2 and res.get("c2_redactions") == 0}


def _jobs(orch):
    with orch.bus.lock:
        return [r[0] for r in orch.bus.db.execute("SELECT job_id FROM report_jobs")]


async def main() -> int:
    ok = 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        print(f"{'#':>2} {'scenario':<16} {'extract':<8} {'turns':<6} {'min':<5} {'end':<13} drafts  result")
        for i in range(10):
            r = await one(i, tmp)
            ok += r["ok"]
            print(f"{r['i']:>2} {r['scenario']:<16} {r['score']:<8} {r['turns']!s:<6} {r['minutes']!s:<5} "
                  f"{r['end']!s:<13} {r['drafts']:<7} {'PASS' if r['ok'] else 'FAIL'}")
    print(f"\nrun10: {ok}/10 passed (DoD >= 9/10): {'PASS' if ok >= 9 else 'FAIL'}  [offline, semi, PACING_SPEED=0]")
    return 0 if ok >= 9 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
