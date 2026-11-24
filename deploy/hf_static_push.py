"""Publish the FREE static demo to a Hugging Face *static* Space (Docker Spaces need HF PRO since 2026).

    py -3.12 deploy/hf_static_push.py --dry-run
    py -3.12 deploy/hf_static_push.py

Serves web/ from the PUBLIC mirror. No server: the operator console runs the in-browser replay
(dashboard.html?mock=1, labelled MOCK) of a recorded synthetic call; the citizen page is fully static.
Needs HF_TOKEN (write) in env/.env; never printed. Optional HF_SPACE (default "<user>/saarthi-kavach").
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hf_space_push import MIRROR, ensure_hub, load_env  # noqa: E402

STAGING = Path(r"D:\hacthon\saarthi-hf-static")
FRONT = """---
title: Saarthi Kavach
emoji: 🛡️
colorFrom: indigo
colorTo: green
sdk: static
app_file: index.html
pinned: false
license: mit
short_description: AI voice decoy + fraud-intel console (in-browser replay)
---

# Saarthi Kavach — static demo

Open the Space and choose **citizen** or **operator**. The operator console replays a recorded,
synthetic digital-arrest call in your browser (badge: MOCK): no server, no live LLM, nothing sent.
Live multi-agent version (Lyzr, Band, AdaL, Finch, Kokoro voice): run the repo locally,
https://github.com/SaketSinghRajput/Saarthi-Kavach
"""
INDEX = ('<!doctype html><meta charset="utf-8"><title>Saarthi Kavach</title>'
         '<meta http-equiv="refresh" content="0; url=start.html"><a href="start.html">Open Saarthi Kavach</a>\n')


def stage(mirror: Path) -> list[str]:
    if STAGING.exists():
        shutil.rmtree(STAGING)
    shutil.copytree(mirror / "web", STAGING, ignore=shutil.ignore_patterns("app.js", "index.html"))
    start = STAGING / "start.html"
    t = start.read_text(encoding="utf-8")
    if 'href="dashboard.html"' not in t:
        raise SystemExit("start.html console link not found")
    start.write_text(t.replace('href="dashboard.html"', 'href="dashboard.html?mock=1&speed=2"'), encoding="utf-8")
    (STAGING / "index.html").write_text(INDEX, encoding="utf-8")
    (STAGING / "README.md").write_text(FRONT, encoding="utf-8")
    return sorted(p.relative_to(STAGING).as_posix() for p in STAGING.rglob("*") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    env = load_env()
    files = stage(MIRROR)
    print(f"staged {len(files)} files in {STAGING}: {', '.join(files[:8])} ...")
    if a.dry_run:
        print("HF_TOKEN:", "set (hidden)" if env.get("HF_TOKEN") else "NOT SET")
        return 0
    if not env.get("HF_TOKEN"):
        raise SystemExit("HF_TOKEN missing")
    hub = ensure_hub(install=True)
    api = hub.HfApi(token=env["HF_TOKEN"])
    user = api.whoami()["name"]
    space = env.get("HF_SPACE") or f"{user}/saarthi-kavach"
    api.create_repo(space, repo_type="space", space_sdk="static", exist_ok=True, private=False)
    api.upload_folder(folder_path=str(STAGING), repo_id=space, repo_type="space",
                      commit_message="Saarthi Kavach static demo")
    slug = space.replace("/", "-").replace("_", "-").replace(".", "-").lower()
    print(f"Space: https://huggingface.co/spaces/{space}")
    print(f"PUBLIC DEMO URL: https://{slug}.static.hf.space")
    return 0


if __name__ == "__main__":
    sys.exit(main())
