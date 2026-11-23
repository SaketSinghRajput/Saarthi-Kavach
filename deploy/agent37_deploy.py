#!/usr/bin/env python
"""Deploy Saarthi to Agent37 (public demo URL). One command once AGENT37_API_KEY exists.

  py -3.12 deploy/agent37_deploy.py --dry-run     # print planned calls, secrets redacted, no network
  py -3.12 deploy/agent37_deploy.py               # build template, create instance, open port, poll health
  py -3.12 deploy/agent37_deploy.py --teardown    # delete instance (+ --delete-template to drop the template)

Reads AGENT37_API_KEY and optional pass-through vars from the process env; .env is loaded
(python-dotenv if installed, else a tiny parser) only here, at runtime, and never printed.
Raw REST flow from https://www.agent37.com/docs/llms-full.txt (template-builds -> upload -> start -> poll).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path

import httpx

API = "https://api.agent37.com"
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "deploy" / ".agent37_state.json"   # instance id only, no secrets; gitignored
DEFAULT_PORT = 8000
# App settings that make the demo live. Unset ones are skipped (the app falls back to offline stubs).
PASS_THROUGH = ["APP_MODE", "INPUT_MODE", "PACING_SPEED", "DEMO_SYNTHETIC_ONLY",
                "KILL_SWITCH", "MAX_TURNS", "MAX_CALL_SECONDS", "START_RATE_PER_MIN", "PTT_IDLE_S",
                "LYZR_API_KEY", "LYZR_USER_ID", "LYZR_CHAT_URL", "LYZR_AGENT_SCAMMER", "LYZR_AGENT_KAMLA",
                "LYZR_AGENT_INTEL", "KAMLA_TIMEOUT_S", "SCAMMER_TIMEOUT_S", "LYZR_TURN_BUDGET_S",
                "TTS_PROVIDER", "TTS_API_KEY", "TTS_VOICE_SCAMMER", "TTS_VOICE_KAMLA",
                "BAND_ENABLED", "BAND_API_URL", "BAND_ROOM_ID", "BAND_KEY_SAARTHI", "BAND_KEY_DETECTOR", "BAND_KEY_KAMLA",
                "BAND_KEY_INTEL", "BAND_KEY_VERIFIER", "BAND_KEY_REPORTER", "BAND_AGENT_ID_REPORTER",
                "REPORTER_FALLBACK_S",
                "ADAL_ENABLED", "ADAL_MODEL", "ADAL_TIMEOUT_S", "ADAL_ALLOWED_HOST",
                "FINCH_ENABLED", "FINCH_SEARCH_URL", "DETECTIFAI_ENABLED", "EGRESS_ALLOWLIST"]
EXCLUDE_DIRS = {".git", "real-test", "data", "recordings", "models", ".claude", "learnings", "marketing", "tests",
                "__pycache__", ".venv", "venv", ".pytest_cache", "design", "docs", "tools"}


def load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(p, override=False)
    except ImportError:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def redact(v: str) -> str:
    return "<redacted>" if v else "<empty>"


def pack_context() -> bytes:
    """Gzipped tar with Dockerfile at root; mirrors .dockerignore (never .env, tests, data, ...)."""
    buf = io.BytesIO()

    def keep(ti: tarfile.TarInfo):
        name = Path(ti.name)
        if any(p in EXCLUDE_DIRS for p in name.parts) or name.name.startswith(".env") or name.suffix == ".pyc":
            return None
        return ti

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in ("Dockerfile", ".dockerignore"):
            tar.add(ROOT / name, arcname=name)
        tar.add(ROOT / "deploy" / "requirements-runtime.txt", arcname="deploy/requirements-runtime.txt")
        for d in ("app", "web", "fixtures", "audio/cache"):
            tar.add(ROOT / d, arcname=d, filter=keep)
    return buf.getvalue()


def instance_body(args, env: dict) -> dict:
    return {"template": args.name, "name": "saarthi-demo", "env": env, "region": "us",
            "resources": {"cpu": 2, "memory": 4, "disk": 4}, "auto_sleep": False,
            "public_ports": [{"port": DEFAULT_PORT, "label": "dashboard"}]}


def die(step: str, msg: str, applied: list) -> None:
    sys.exit(f"FAILED at step '{step}': {msg}\n  applied: {applied or 'nothing'}\n"
             f"  not applied: the remaining steps; re-running is safe (rebuild publishes a new template revision)")


def retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except httpx.TransportError:   # includes timeouts
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def dry_run(args, env: dict, key: str, names: list) -> None:
    size = len(pack_context())
    safe_env = {k: redact(v) for k, v in env.items()}
    print("DRY RUN (no network calls). Authorization: Bearer", redact(key) if key else "<AGENT37_API_KEY not set>")
    steps = [
        ("POST", f"{API}/v1/template-builds", {"name": args.name, "size_bytes": size, "default_port": DEFAULT_PORT,
                                               "description": "Saarthi Kavach demo"}),
        ("PUT", "<upload_url from step 1; no Agent37 key sent>", f"<{size} bytes gzipped build context>"),
        ("POST", f"{API}/v1/template-builds/{{build_id}}/start", {}),
        ("GET", f"{API}/v1/template-builds/{{build_id}}/logs?offset=N  (poll until status=succeeded)", None),
        ("POST", f"{API}/v1/instances", {**instance_body(args, {}), "env": safe_env}),
        ("POST", f"{API}/v1/instances/{{id}}/public-ports  (only if not in the create response)",
         {"port": DEFAULT_PORT, "label": "dashboard"}),
        ("GET", "<public url>/api/health  (poll until 200)", None),
    ]
    for i, (m, p, b) in enumerate(steps, 1):
        print(f"{i}. {m} {p}")
        if b is not None:
            print("     body:", b if isinstance(b, str) else json.dumps(b))
    print("env passed through:", sorted(env) or "none", "| not set (skipped):", sorted(set(names) - set(env)))
    print("HOSTED_SCRIPTED_ONLY=true is always set: the scammer never calls the live LLM on a public host.")


def deploy(args, env: dict, key: str) -> None:
    applied: list = []
    h = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=60) as c:
        ctx = pack_context()
        print(f"[1/5] build context {len(ctx) / 1e6:.1f} MB")
        r = retry(lambda: c.post(f"{API}/v1/template-builds", headers=h, json={
            "name": args.name, "size_bytes": len(ctx), "default_port": DEFAULT_PORT, "description": "Saarthi Kavach demo"}))
        if r.status_code >= 400:
            die("create build", f"{r.status_code} {r.text[:300]}", applied)
        b = r.json()
        # presigned URL is a bearer credential: send NO Agent37 key to it
        up = retry(lambda: httpx.put(b["upload_url"], content=ctx, headers={"Expect": ""}, timeout=300))
        if up.status_code >= 400:
            die("upload context", str(up.status_code), applied)
        r = retry(lambda: c.post(f"{API}/v1/template-builds/{b['id']}/start", headers=h, json={}))
        if r.status_code >= 400:
            die("start build", f"{r.status_code} {r.text[:300]}", applied)
        print(f"[2/5] building template '{args.name}' ({b['id']}) ...")
        off, deadline = 0, time.time() + 45 * 60
        while time.time() < deadline:
            st = retry(lambda: c.get(f"{API}/v1/template-builds/{b['id']}/logs", headers=h, params={"offset": off})).json()
            if st.get("data"):
                print(st["data"], end="")
            off = st.get("offset", off)
            if st.get("status") == "succeeded":
                break
            if st.get("status") in ("failed", "cancelled", "error"):
                die("template build", f"status={st['status']}", applied)
            time.sleep(5)
        else:
            die("template build", "timed out after 45 min", applied)
        applied.append(f"template {args.name}")
        r = retry(lambda: c.post(f"{API}/v1/instances", headers=h, json=instance_body(args, env), timeout=180))
        if r.status_code >= 400:
            die("create instance", f"{r.status_code} {r.text[:300]}", applied)
        inst = r.json()
        applied.append(f"instance {inst['id']}")
        STATE.write_text(json.dumps({"instance_id": inst["id"], "template": args.name}))
        print(f"[3/5] instance {inst['id']} ({inst.get('status')})")
        url = next((p["url"] for p in inst.get("public_ports", []) if p.get("port") == DEFAULT_PORT), None)
        if not url:
            r = retry(lambda: c.post(f"{API}/v1/instances/{inst['id']}/public-ports", headers=h,
                                     json={"port": DEFAULT_PORT, "label": "dashboard"}))
            if r.status_code == 409:   # public_port_exists: look it up
                got = c.get(f"{API}/v1/instances/{inst['id']}/public-ports", headers=h).json()
                got = got.get("data", got) if isinstance(got, dict) else got
                url = next(p["url"] for p in got if p["port"] == DEFAULT_PORT)
            elif r.status_code >= 400:
                die("public port", f"{r.status_code} {r.text[:300]}", applied)
            else:
                url = r.json()["url"]
        applied.append(f"public port {DEFAULT_PORT}")
        print(f"[4/5] public port open: {url}")
        for _ in range(60):
            try:
                if httpx.get(f"{url}/api/health", timeout=10).status_code == 200:
                    print(f"[5/5] healthy.\nPUBLIC DEMO URL: {url}")
                    return
            except httpx.HTTPError:
                pass
            time.sleep(5)
        die("health poll", f"{url}/api/health not 200 after 5 min", applied)


def teardown(args, key: str) -> None:
    h = {"Authorization": f"Bearer {key}"}
    iid = args.instance_id or (json.loads(STATE.read_text())["instance_id"] if STATE.exists() else None)
    if not iid:
        sys.exit("no instance id: pass --instance-id (or run from the checkout that deployed)")
    with httpx.Client(timeout=60) as c:
        r = retry(lambda: c.delete(f"{API}/v1/instances/{iid}", headers=h))
        print(f"DELETE instance {iid}: {r.status_code}")
        if r.status_code < 400 and STATE.exists():
            STATE.unlink()
        if args.delete_template:
            r2 = retry(lambda: c.delete(f"{API}/v1/templates/{args.name}", headers=h))
            print(f"DELETE template {args.name}: {r2.status_code}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    ap.add_argument("--delete-template", action="store_true")
    ap.add_argument("--instance-id")
    ap.add_argument("--name", default="saarthi")
    ap.add_argument("--env-names", default=",".join(PASS_THROUGH), help="comma list of env var NAMES to pass through")
    args = ap.parse_args()
    load_env()
    names = [n.strip() for n in args.env_names.split(",") if n.strip()]
    env = {n: os.environ[n] for n in names if os.environ.get(n)}
    env["HOSTED_SCRIPTED_ONLY"] = "true"  # public host: never let visitors spend Lyzr credits
    key = os.environ.get("AGENT37_API_KEY", "")
    if args.dry_run:
        return dry_run(args, env, key, names)
    if not key:
        sys.exit("AGENT37_API_KEY missing (put it in .env or the process environment)")
    if args.teardown:
        return teardown(args, key)
    deploy(args, env, key)


if __name__ == "__main__":
    main()
