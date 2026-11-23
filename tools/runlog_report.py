"""Recompute the HUD latency numbers from a run log: py -3.12 tools/runlog_report.py data/runs/<call_id>.json

p95 is nearest-rank, same as app.orchestrator.p95. Answer p95 is the p95 of the per-turn (llm + tts) sum,
never p95(llm) + p95(tts)."""
from __future__ import annotations

import json
import sys


def p95(xs: list) -> int:
    if not xs:
        return 0
    s = sorted(xs)
    return int(s[min(len(s) - 1, int((0.95 * len(s) + 0.9999)) - 1)])


def report(run: dict) -> dict:
    k = [t for t in run["turns"] if t.get("speaker") == "kamla"]
    llm = [t["llm_ms"] for t in k]
    tts = [t["tts_ms"] for t in k]
    ans = [t["llm_ms"] + t["tts_ms"] for t in k]
    dead = [t["dead_ms"] for t in k]
    return {"run_id": run["run_id"], "n": len(k), "dead_air_p95_ms": p95(dead), "answer_p95_ms": p95(ans),
            "llm_p95_ms": p95(llm), "tts_p95_ms": p95(tts)}


def main(argv: list) -> int:
    if len(argv) != 2:
        print("usage: runlog_report.py <run.json>")
        return 2
    run = json.load(open(argv[1], encoding="utf-8"))
    r = report(run)
    m = run.get("metrics") or {}
    print(f"run {r['run_id']}  scenario={run.get('scenario')}  n={r['n']}")
    ok = True
    for key, label in (("dead_air_p95_ms", "dead air p95"), ("answer_p95_ms", "answer p95 (p95 of per-turn llm+tts)"),
                       ("llm_p95_ms", "llm p95"), ("tts_p95_ms", "tts p95")):
        logged = m.get(key)
        match = logged is None or int(logged) == r[key]
        ok &= match
        print(f"  {label:40s} {r[key]:>7} ms   logged {logged}   {'OK' if match else 'MISMATCH'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
