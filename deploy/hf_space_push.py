"""Publish the PUBLIC demo to a Hugging Face Docker Space (one command).

    py -3.12 deploy/hf_space_push.py --dry-run     # plan only: secrets redacted, no network, no token needed
    py -3.12 deploy/hf_space_push.py               # real push (needs HF_TOKEN, a write token)
    py -3.12 deploy/hf_space_push.py --with-lyzr   # also pass Lyzr keys (spends Lyzr credits per call)

Env / .env (read at runtime, never printed): HF_TOKEN, optional HF_SPACE (default "<user>/saarthi-kavach"),
optional APP_PASSCODE (generated and printed ONCE if absent). The staging dir is built from the PUBLIC mirror
(D:\\hacthon\\saarthi-public, rebuilt first by tools/make_public_mirror.py), never from the private repo.
No sponsor keys are sent by default: the Space runs the scripted scammer + mock replay with no keys at all.
huggingface_hub is installed into a scratch venv via uv when missing (requirements.txt is untouched).
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = Path(r"D:\hacthon\saarthi-public")
STAGING = Path(r"D:\hacthon\saarthi-hf-staging")
HUB_VENV = Path.home() / ".cache" / "saarthi-hf-venv"
DEFAULT_NAME = "saarthi-kavach"
VARIABLES = {"PORT": "7860", "HOSTED_SCRIPTED_ONLY": "true", "FINCH_ENABLED": "true"}
LYZR_KEYS = ("LYZR_API_KEY", "LYZR_USER_ID", "LYZR_AGENT_SCAMMER", "LYZR_AGENT_KAMLA", "LYZR_AGENT_INTEL")
FRONT_MATTER = """---
title: Saarthi Kavach
emoji: 🛡️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

"""
# What the Dockerfile needs from the mirror, plus the README. Everything else (tests, docs, tools, design) stays out.
COPY_ITEMS = ["Dockerfile", "app", "web", "fixtures", "deploy/requirements-runtime.txt"]
SECRET_RE = re.compile(r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|hf_[A-Za-z0-9]{30,}|"
                       r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def load_env() -> dict:
    """os.environ over .env (parsed here, never echoed)."""
    env = {}
    f = ROOT / ".env"
    if f.is_file():
        for ln in f.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    env.update({k: v for k, v in os.environ.items() if v})
    return env


def retry(fn, what: str, tries: int = 3):
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as exc:  # network drops: back off and retry; auth errors fail fast below
            if i == tries or "401" in str(exc) or "403" in str(exc):
                raise
            print(f"  retry {i}/{tries - 1} after {type(exc).__name__} ({what})")
            time.sleep(2 * i)


# ------------------------------------------------------------------ staging
def build_mirror() -> None:
    print("step 1: rebuild public mirror (tools/make_public_mirror.py --force)")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "make_public_mirror.py"), "--force"], cwd=ROOT)
    if r.returncode:
        raise SystemExit(f"failed at step 1 (mirror, exit {r.returncode}); nothing applied to Hugging Face")


def build_staging(mirror: Path, staging: Path) -> list[str]:
    if not (mirror / "app").is_dir():
        raise SystemExit(f"failed at step 2: {mirror} is not a mirror (run without --skip-mirror)")
    if staging.exists():
        shutil.rmtree(staging, onerror=lambda fn, p, _e: (os.chmod(p, 0o700), fn(p)))
    staging.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".env", ".env.*")
    for item in COPY_ITEMS:
        src, dst = mirror / item, staging / item
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=ignore)
        elif src.is_file():
            shutil.copy2(src, dst)
        else:
            raise SystemExit(f"failed at step 2: mirror lacks {item}")
    # The mirror withholds audio/, but the Dockerfile does `COPY audio/cache/ audio/cache/`: give it an empty dir.
    keep = staging / "audio" / "cache" / ".keep"
    keep.parent.mkdir(parents=True)
    keep.write_text("", encoding="utf-8")
    readme = mirror / "README.md"
    body = readme.read_text(encoding="utf-8") if readme.is_file() else "# Saarthi Kavach\n"
    (staging / "README.md").write_text(FRONT_MATTER + body, encoding="utf-8")
    return sorted(p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file())


def validate_staging(staging: Path) -> list[str]:
    """Static checks (no docker build). Returns problems; empty list = OK."""
    bad = []
    df = (staging / "Dockerfile").read_text(encoding="utf-8")
    for m in re.finditer(r"^COPY\s+(?!--)(\S+)\s+\S+", df, re.M):
        src = m.group(1)
        if not (staging / src.rstrip("/")).exists():
            bad.append(f"Dockerfile COPY source missing: {src}")
    if "audio/cache" in df and not (staging / "audio" / "cache" / ".keep").is_file():
        bad.append("audio/cache placeholder missing")
    for need in ("web/start.html", "web/mock.js", "web/dashboard.html", "fixtures/synthetic.sample.json",
                 "deploy/requirements-runtime.txt", "app/main.py"):
        if not (staging / need).is_file():
            bad.append(f"missing {need}")
    if (staging / "fixtures" / "synthetic.json").exists():
        bad.append("private fixtures/synthetic.json present")
    if list((staging / "audio").rglob("*.wav")) or (staging / "prompts").exists() or (staging / "data").exists():
        bad.append("audio wav / prompts / data present (must be withheld)")
    rd = (staging / "README.md").read_text(encoding="utf-8")
    fm = re.match(r"---\n(.*?)\n---\n", rd, re.S)
    if not fm or not {"sdk: docker", "app_port: 7860"} <= set(fm.group(1).splitlines()):
        bad.append("README front matter missing sdk: docker / app_port: 7860")
    if "EXPOSE" in df and "ENV PORT=" not in df:
        bad.append("Dockerfile has no PORT env (needed for PORT=7860)")
    for p in staging.rglob("*"):
        if p.is_file():
            if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
                bad.append(f"env file in staging: {p.name}")
            elif p.stat().st_size < 2_000_000 and p.suffix in {".py", ".js", ".json", ".md", ".html", ".txt", ".example", ""}:
                try:
                    if SECRET_RE.search(p.read_text(encoding="utf-8")):
                        bad.append(f"secret-looking value in {p.relative_to(staging).as_posix()}")
                except (UnicodeDecodeError, OSError):
                    pass
    return bad


# ------------------------------------------------------------------ hub
def ensure_hub(install: bool):
    """Import huggingface_hub, installing into a scratch venv via uv if missing (re-execs under that venv)."""
    try:
        import huggingface_hub  # noqa: F401
        return huggingface_hub
    except ImportError:
        pass
    if not install:
        return None
    py = HUB_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        uv = shutil.which("uv")
        if not uv:
            raise SystemExit("failed at step 3: huggingface_hub missing and uv not found (install uv or `pip install huggingface_hub`)")
        print(f"step 3: installing huggingface_hub into scratch venv {HUB_VENV}")
        retry(lambda: subprocess.run([uv, "venv", str(HUB_VENV), "--python", "3.12"], check=True), "uv venv")
        retry(lambda: subprocess.run([uv, "pip", "install", "--python", str(py), "huggingface_hub"], check=True), "uv pip")
    if Path(sys.executable).resolve() != py.resolve():
        raise SystemExit(subprocess.run([str(py), *sys.argv]).returncode)  # re-run this script under the venv
    raise SystemExit("huggingface_hub still not importable in scratch venv")


def push(a, env: dict, files: list[str], passcode: str, generated: bool) -> None:
    hub = ensure_hub(install=True)
    token = env.get("HF_TOKEN")
    api = hub.HfApi(token=token)
    done, todo = [], ["identify user", "create Space", "set variables", "set secrets", "upload files"]

    def step(name, fn):
        try:
            out = retry(fn, name)
        except Exception as exc:
            msg = re.sub(r"hf_[A-Za-z0-9]+", "hf_***", str(exc))
            raise SystemExit(f"failed at step '{name}': {type(exc).__name__}: {msg}\n  applied: {done or 'nothing'}\n  not applied: {todo}")
        done.append(name)
        todo.remove(name)
        return out

    user = step("identify user", lambda: api.whoami()["name"])
    space = env.get("HF_SPACE") or f"{user}/{DEFAULT_NAME}"
    step("create Space", lambda: api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True, private=False))
    step("set variables", lambda: [api.add_space_variable(space, k, v) for k, v in VARIABLES.items()])
    secrets_ = {"APP_PASSCODE": passcode}
    if a.with_lyzr:
        secrets_.update({k: env[k] for k in LYZR_KEYS if env.get(k)})
    step("set secrets", lambda: [api.add_space_secret(space, k, v) for k, v in secrets_.items()])
    step("upload files", lambda: api.upload_folder(folder_path=str(a.staging), repo_id=space, repo_type="space",
                                                   commit_message="Saarthi Kavach public demo"))
    slug = space.replace("/", "-").replace("_", "-").lower()
    print(f"\nPushed {len(files)} files to https://huggingface.co/spaces/{space} (build starts now; watch the Logs tab)")
    print(f"PUBLIC DEMO URL: https://{slug}.hf.space")
    if generated:
        print(f"APP_PASSCODE (shown ONCE, save it now): {passcode}")
    else:
        print("APP_PASSCODE: taken from your env/.env (unchanged)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the plan, redact secrets, no network")
    ap.add_argument("--with-lyzr", action="store_true", help="also set LYZR_* secrets (spends Lyzr credits)")
    ap.add_argument("--skip-mirror", action="store_true", help="do not rebuild the public mirror first")
    ap.add_argument("--mirror", type=Path, default=MIRROR)
    ap.add_argument("--staging", type=Path, default=STAGING)
    ap.add_argument("--check-deps", action="store_true", help="only install/import huggingface_hub in the scratch venv")
    a = ap.parse_args(argv)
    if a.check_deps:
        hub = ensure_hub(install=True)
        print("huggingface_hub", hub.__version__, "OK")
        return 0
    env = load_env()
    if not a.dry_run and not env.get("HF_TOKEN"):
        raise SystemExit("HF_TOKEN missing: create a WRITE token at huggingface.co/settings/tokens and add HF_TOKEN=... to .env")
    if not a.dry_run:
        ensure_hub(install=True)  # install/re-exec first so nothing below runs twice
    if a.with_lyzr:
        print("WARNING: --with-lyzr makes every hosted call spend Lyzr credits (cap $20, about $10 used). Get approval first.")
    if not a.skip_mirror:
        build_mirror()
    files = build_staging(a.mirror, a.staging)
    problems = validate_staging(a.staging)
    print(f"step 2: staging {a.staging}: {len(files)} files; static validation: " + ("OK" if not problems else "FAILED"))
    if problems:
        raise SystemExit("\n".join("  - " + p for p in problems))
    passcode = env.get("APP_PASSCODE") or ""
    generated = not passcode
    if generated:
        passcode = secrets.token_urlsafe(12)
    if len(passcode) < 12:
        raise SystemExit("APP_PASSCODE must be 12+ characters")
    if a.dry_run:
        have_hub = ensure_hub(install=False) is not None
        print("\nDRY RUN plan (nothing sent):")
        print(f"  Space:      {env.get('HF_SPACE') or '<user>/' + DEFAULT_NAME} (docker, public)")
        print(f"  HF_TOKEN:   {'set (hidden)' if env.get('HF_TOKEN') else 'NOT SET'}")
        print(f"  variables:  {VARIABLES}")
        sec = {"APP_PASSCODE": "***" + (" (generated at run time, shown once)" if generated else " (from env)")}
        if a.with_lyzr:
            sec.update({k: "***" for k in LYZR_KEYS if env.get(k)})
        print(f"  secrets:    {sec}")
        print("  sponsor keys: " + ("Lyzr only (flag)" if a.with_lyzr else "none (scripted scammer + cached/mock replay)"))
        print(f"  huggingface_hub: {'installed' if have_hub else 'will be installed into ' + str(HUB_VENV) + ' via uv'}")
        print("  upload:     " + ", ".join(files[:6]) + f", ... ({len(files)} files)")
        return 0
    push(a, env, files, passcode, generated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
