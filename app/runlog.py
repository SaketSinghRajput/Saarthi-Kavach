"""Per-call run log: data/runs/<call_id>.json. Timings, modes, metrics and draft hashes only.
No transcript text and no identifier values are ever written (counts / hashes / ids only)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

RUN_ID_RE = re.compile(r"^c_[0-9a-f]{12}$")
ROW_KEYS = ("seq", "speaker", "source", "t_start", "llm_ms", "tts_ms", "filler_ms", "dead_ms", "latency_ms",
            "audio_url", "audio_ms")


def runs_dir(data_dir: str) -> Path:
    return Path(data_dir) / "runs"


def build_run(call_id: str, scenario: str, agents: dict, rows: list, metrics: dict, summary: dict, drafts: list, started_iso: Optional[str] = None) -> dict:
    return {"run_id": call_id, "scenario": scenario, "call_started_wallclock": started_iso,
            "modes": {k: v.get("mode") for k, v in agents.items()},
            "turns": [{k: r.get(k) for k in ROW_KEYS} for r in rows],
            "metrics": metrics, "call_summary": summary,
            "drafts": [{k: d.get(k) for k in ("kind", "trigger", "band_msg_id", "case_id", "sha256")} for d in drafts]}


def write_run(data_dir: str, run: dict) -> Optional[Path]:
    if not RUN_ID_RE.match(run["run_id"]):
        return None
    d = runs_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{run['run_id']}.json"
    p.write_text(json.dumps(run, indent=1), encoding="utf-8")
    return p


def read_run(data_dir: str, run_id: str) -> Optional[dict]:
    if not RUN_ID_RE.match(run_id):
        return None
    p = runs_dir(data_dir) / f"{run_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def list_runs(data_dir: str) -> list:
    out = []
    d = runs_dir(data_dir)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("c_*.json"), key=lambda q: q.stat().st_mtime, reverse=True):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            out.append({"run_id": r["run_id"], "scenario": r.get("scenario"),
                        "dead_air_p95_ms": (r.get("metrics") or {}).get("dead_air_p95_ms")})
        except Exception:
            continue
    return out
