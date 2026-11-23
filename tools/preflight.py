"""Sponsor preflight / day-1 spike harness.

For each sponsor: is the key present? is it reachable? Spikes S1 (Lyzr 10-turn latency), S2 (TTS) and
S3 (Band post) run only when their keys exist and otherwise SKIP cleanly (exit code 0).
Usage:  py tools/preflight.py [--online] [--only s1,s2,s3,adal,finch,detectifai]

Request shapes for Lyzr / TTS / Band / DetectifAI are UNVERIFIED until this has run with real keys;
fix app/ adapters from what this prints. No secrets are printed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.safety import egress  # noqa: E402


def _r(name: str, key: bool, status: str, detail: str = "") -> dict:
    return {"name": name, "key_present": key, "status": status, "detail": detail}


def _post(url: str, s, **kw) -> httpx.Response:
    egress.check(url, s)
    return httpx.post(url, timeout=kw.pop("timeout", 15.0), follow_redirects=False, **kw)


def _p95(xs: list) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.95 * len(xs) + 0.9999) - 1)]


# ---- S1: Lyzr 10-turn latency --------------------------------------------------------------
def s1_lyzr_latency(s, turns: int = 10, online: bool = False) -> dict:
    key = bool(s.lyzr_api_key and s.lyzr_user_id and s.lyzr_agent_kamla)
    if not key:
        return _r("S1 lyzr latency", False, "skip", "LYZR_API_KEY / LYZR_USER_ID / LYZR_AGENT_KAMLA not all set")
    if not online:
        return _r("S1 lyzr latency", True, "skip", f"fires {turns} paid Lyzr calls; pass --online to run it")
    budget_ms = s.lyzr_turn_budget_s * 1000
    lat, errs = [], 0
    for i in range(turns):
        t0 = time.perf_counter()
        try:
            r = _post(s.lyzr_chat_url, s,
                      headers={"x-api-key": s.lyzr_api_key, "Content-Type": "application/json"},
                      json={"user_id": s.lyzr_user_id, "agent_id": s.lyzr_agent_kamla,
                            "session_id": f"pf-{uuid.uuid4().hex[:10]}",
                            "message": "Caller says: hello, I am calling about your parcel. Reply in 2 short sentences.",
                            "system_prompt_variables": {"directive": "Ask who is calling and why."}})
            ok = r.status_code == 200 and bool((r.json().get("response") or "").strip())
            errs += 0 if ok else 1
        except Exception as e:
            errs += 1
            print(f"  turn {i + 1}: {type(e).__name__}")
        lat.append((time.perf_counter() - t0) * 1000)
    p95 = _p95(lat)
    verdict = "ok" if errs == 0 and p95 <= budget_ms else "fail"
    return _r("S1 lyzr latency", True, verdict,
              f"n={turns} errors={errs} p50={statistics.median(lat):.0f}ms p95={p95:.0f}ms (budget {budget_ms:.0f}ms)")


# ---- S2: TTS ----------------------------------------------------------------------------------
def s2_tts(s) -> dict:
    if s.tts_provider == "kokoro":  # local engine: no key, no network, no cost
        from app.integrations.tts import KokoroEngine
        if KokoroEngine.available(s.kokoro_model_dir):
            return _r("S2 tts", True, "ok", "local Kokoro: package and model files present (no key needed)")
        return _r("S2 tts", True, "skip", "TTS_PROVIDER=kokoro but kokoro package or model files missing here; app would use the stub")
    key = bool(s.tts_provider and s.tts_api_key and s.tts_voice_kamla)
    if not key:
        return _r("S2 tts", False, "skip", "TTS_PROVIDER / TTS_API_KEY / TTS_VOICE_KAMLA not all set")
    from app.integrations.tts import TTS
    import asyncio
    t0 = time.perf_counter()
    clip = asyncio.run(TTS(s).synth("Haan beta, ruko zara, main likh rahi hoon.", "kamla"))
    ms = (time.perf_counter() - t0) * 1000
    return _r("S2 tts", True, "ok" if clip.live else "fail", f"live={clip.live} {ms:.0f}ms (budget 700ms) duration~{clip.duration_ms}ms")


# ---- S3: Band post ------------------------------------------------------------------------------
def s3_band_post(s) -> dict:
    """One harmless code-built ping (GET participants + 1 POST), mentioning the room's human. Never transcript text (G7)."""
    key = bool(s.band_enabled and s.band_room_id and s.band_keys.get("saarthi"))
    if not key:
        return _r("S3 band post", False, "skip", "BAND_ROOM_ID / BAND_KEY_SAARTHI not set")
    hdr = {"X-API-Key": s.band_keys["saarthi"]}
    base = f"{s.band_api_url}/chats/{s.band_room_id}"
    egress.check(base, s)
    pr = httpx.get(f"{base}/participants", headers=hdr, timeout=8.0, follow_redirects=False)
    human = next((p for p in (pr.json().get("data") or []) if str(p.get("type", "")).lower() != "agent"), None)         if pr.status_code < 300 else None
    if not human:
        return _r("S3 band post", True, "fail", f"participants HTTP {pr.status_code}, no human to mention")
    ment = {"id": human["id"], "handle": human["handle"], "name": human.get("name") or human["handle"]}
    r = _post(f"{base}/messages", s, headers=hdr, timeout=8.0,
              json={"message": {"content": f"Saarthi preflight ping {int(time.time())}", "mentions": [ment]}})
    detail = ""
    if r.status_code >= 300:
        try:
            detail = " " + json.dumps(r.json())[:300]
        except Exception:
            detail = " " + r.text[:300]
    return _r("S3 band post", True, "ok" if r.status_code < 300 else "fail", f"HTTP {r.status_code}{detail}")


# ---- others -----------------------------------------------------------------------------------------
def adal_check(s) -> dict:
    path = shutil.which(s.adal_bin)
    if not path:
        return _r("adal cli", bool(s.adal_provider_key), "skip", f"'{s.adal_bin}' not on PATH")
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
        return _r("adal cli", bool(s.adal_provider_key), "ok" if out.returncode == 0 else "fail",
                  (out.stdout or out.stderr).strip()[:80])
    except Exception as e:
        return _r("adal cli", bool(s.adal_provider_key), "fail", type(e).__name__)


def finch_check(s, online: bool) -> dict:
    if not online:
        return _r("finch search", True, "skip", "no key needed; pass --online to test reachability")
    try:
        import asyncio
        import dataclasses
        from app.fixtures import load_fixtures
        from app.integrations.finch_scout import FinchScout
        live = dataclasses.replace(s, finch_enabled=True)
        fx = load_fixtures(s.fixtures_path)
        scout = FinchScout(live, fx)
        parts, misses = [], 0
        for st in fx["finch_keywords"]:
            res = asyncio.run(scout.scout(st))
            if res["live"]:
                parts.append(f"{st}: q={res['query']!r} n={res['total']} top={res['skills'][0]['name'][:24]!r}")
            else:
                misses += 1
                parts.append(f"{st}: NO LIVE HIT (snapshot)")
        return _r("finch search", True, "ok" if misses == 0 else "fail", "; ".join(parts))
    except Exception as e:
        return _r("finch search", True, "fail", type(e).__name__)


def detectifai_check(s, online: bool) -> dict:
    if not s.detectifai_api_key:
        return _r("detectifai", False, "skip", "DETECTIFAI_API_KEY not set")
    if not online:
        return _r("detectifai", True, "skip", "pass --online to test reachability")
    try:
        r = httpx.get("https://platform.detectif.ai/", timeout=8.0)
        return _r("detectifai", True, "ok" if r.status_code < 500 else "fail", f"HTTP {r.status_code}")
    except Exception as e:
        return _r("detectifai", True, "fail", type(e).__name__)


def agent37_check(s, online: bool = False) -> dict:
    url = getattr(s, "agent37_url", "")
    if not url:
        return _r("agent37", False, "skip", "AGENT37_URL not set (hosting only)")
    if not online:
        return _r("agent37", True, "skip", "pass --online to GET {AGENT37_URL}/api/health")
    try:
        r = httpx.get(f"{url}/api/health", timeout=8.0, follow_redirects=False)
        return _r("agent37", True, "ok" if r.status_code == 200 else "fail", f"HTTP {r.status_code}")
    except Exception as e:
        return _r("agent37", True, "fail", type(e).__name__)


def run(only: set, online: bool) -> list:
    s = load_settings()
    table = {
        "s1": lambda: s1_lyzr_latency(s, online=online), "s2": lambda: s2_tts(s), "s3": lambda: s3_band_post(s),
        "adal": lambda: adal_check(s), "finch": lambda: finch_check(s, online),
        "detectifai": lambda: detectifai_check(s, online), "agent37": lambda: agent37_check(s, online)}
    return [fn() for k, fn in table.items() if not only or k in only]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true",
                    help="also run network checks, including the PAID Lyzr S1 latency spike (10 calls)")
    ap.add_argument("--only", default="", help="comma list: s1,s2,s3,adal,finch,detectifai,agent37")
    a = ap.parse_args()
    results = run({x.strip() for x in a.only.split(",") if x.strip()}, a.online)
    print(f"{'check':<18} {'key':<8} {'status':<6} detail")
    for r in results:
        print(f"{r['name']:<18} {'present' if r['key_present'] else 'missing':<8} {r['status']:<6} {r['detail']}")
    failed = [r for r in results if r["status"] == "fail"]
    print(f"\n{len(failed)} failed, {sum(r['status'] == 'skip' for r in results)} skipped (skips are fine without keys)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
