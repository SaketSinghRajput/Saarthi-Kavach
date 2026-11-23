"""Pre-render every scripted line of the 3 scenarios with local Kokoro into audio/cache/ (key = hash(voice+text)).

Run with an interpreter that has kokoro + torch (e.g. tools/tts_bakeoff/.venv):
  tools/tts_bakeoff/.venv/Scripts/python.exe -I tools/prerender_tts.py [--dry-run] [--cpu] [--fixtures PATH]
Kamla lines use hf_beta, scammer lines hm_psi (G2 allow-list). Already-cached lines are skipped.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.integrations.tts import TTS  # noqa: E402


def collect_lines(fx: dict) -> list[tuple[str, str]]:
    """All distinct (role, text) pairs the scripted agents can speak, placeholders expanded like the agents do."""
    out: dict[tuple[str, str], None] = {}
    labels = fx["target_labels"]

    def add(role: str, text: str) -> None:
        out[(role, text)] = None

    for sc in fx["scenarios"].values():
        ents = sc["entities"]
        spokens = {t: [e["spoken"]] + ([e["variant"]["spoken"]] if "variant" in e else []) for t, e in ents.items()}
        all_spoken = [s for v in spokens.values() for s in v]
        for lines in fx["canned"].values():
            for ln in lines:
                if "{target_label}" in ln["text"]:
                    for t in ents:
                        add("kamla", ln["text"].replace("{target_label}", labels[t]["hi"]))
                else:
                    add("kamla", ln["text"])
        for f in fx["fillers"]:
            add("kamla", f["text"])
        for tpl in fx["readback_templates"]:
            for sp in all_spoken:
                add("kamla", tpl["text"].format(spoken=sp))
        for key in ("beats", "pressure_lines"):
            for b in sc.get(key, []):
                add("scammer", b["text"])
        for ev in sc.get("evasions", {}).values():
            add("scammer", ev["text"])
        sl = fx["scammer_lines"]
        for t, tpl in sl["entity"].items():
            for sp in spokens.get(t, []):
                add("scammer", tpl["text"].format(spoken=sp))
        for t in ([sc["correction_for"]] if sc.get("correction_for") in ents else []):
            for sp in spokens[t]:
                add("scammer", sl["correction"]["text"].format(spoken=sp, target_label=labels[t]["hi"]))
        for sp in all_spoken:
            add("scammer", sl["method_failed"]["text"].format(spoken=sp))
        for k in ("affirm", "wrap_up", "unknown"):
            add("scammer", sl[k]["text"])
    return list(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixtures")
    ap.add_argument("--dry-run", action="store_true", help="list lines, render nothing")
    ap.add_argument("--cpu", action="store_true", help="force CPU (default: cuda when available)")
    a = ap.parse_args(argv)
    s = load_settings()
    s.tts_provider = "kokoro"
    if a.cpu:
        s.kokoro_device = "cpu"
    fx = json.loads(Path(a.fixtures or s.fixtures_path).read_text(encoding="utf-8"))
    lines = collect_lines(fx)
    if a.dry_run:
        for role, text in lines:
            print(f"{role}\t{text}")
        print(f"{len(lines)} lines", file=sys.stderr)
        return 0
    tts = TTS(s)
    if not tts.live:
        print("kokoro unavailable (package or models missing); nothing rendered", file=sys.stderr)
        return 2

    async def run() -> tuple[int, int, int]:
        new = hit = bad = 0
        for i, (role, text) in enumerate(lines, 1):
            c = await tts.synth(text, role)
            if c.url is None:
                bad += 1
            elif c.cache_hit:
                hit += 1
            else:
                new += 1
            print(f"[{i}/{len(lines)}] {role} {'FAIL' if c.url is None else ('cached' if c.cache_hit else 'rendered')} "
                  f"{c.duration_ms}ms", flush=True)
        return new, hit, bad

    new, hit, bad = asyncio.run(run())
    print(f"rendered {new}, already cached {hit}, failed {bad}; cache: {tts.cache}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
