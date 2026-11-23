"""One-shot held-out v2 evaluation. Frozen detector = git HEAD export (no tuning). Offline: sockets disabled.

Usage: python -I -B evaluate_v2.py <frozen_root>   (frozen_root contains app/ and fixtures/ from `git archive HEAD`)
Reads real-test/data/v2/*.json, writes real-test/results/heldout-v2-2026-11-23.md. No env, no .env, no network.
"""
import json, math, socket, sys
from collections import Counter, defaultdict
from pathlib import Path

def _blocked(*a, **k):
    raise RuntimeError("network disabled")
socket.socket = _blocked  # type: ignore
socket.create_connection = _blocked  # type: ignore

FROZEN = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(FROZEN))
from app.agents.detector import Detector  # noqa: E402
import app.agents.detector as D  # noqa: E402
assert str(FROZEN) in D.__file__, D.__file__

HERE = Path(__file__).resolve().parent
fx = json.loads((FROZEN / "fixtures" / "synthetic.json").read_text(encoding="utf-8"))
TYPES = ["digital_arrest", "fake_kyc", "fake_investment"]

def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)

def fmt(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} [95% Wilson {lo:.1%} - {hi:.1%}]" if n else "n/a (n=0)"

rows = []
for p in sorted((HERE / "data" / "v2").glob("v2-*.json")):
    s = json.loads(p.read_text(encoding="utf-8"))
    det = Detector(fx, s["id"])
    r = None
    for i, t in enumerate(x["text"] for x in s["turns"] if x["speaker"] in ("scammer", "unknown")):
        r = det.update(t, i)
    rows.append(dict(id=s["id"], label=s["scam_type"], st=s["source_type"], det=r.scam_type, risk=r.risk,
                     stage=r.stage, flag_risk=r.is_scam_likely, flag_type=r.scam_type != "unknown"))

scam = [r for r in rows if r["label"] != "other"]
ben = [r for r in rows if r["label"] == "other"]
out = ["# Held-out v2 evaluation (frozen detector, evaluated once)", "",
       f"n total={len(rows)}; scam={len(scam)}; benign={len(ben)}. Detector = git HEAD export of app/ + fixtures/ (no edits, no tuning).", ""]
acc = sum(r["det"] == r["label"] for r in scam)
out += [f"## Scam-type accuracy (scam items only): {fmt(acc, len(scam))}", ""]
for t in TYPES:
    g = [r for r in scam if r["label"] == t]
    out.append(f"- {t}: {fmt(sum(r['det'] == t for r in g), len(g))}")
out += ["", "## Confusion (rows = label, cols = detected scam_type)", "",
        "| label \\ detected | digital_arrest | fake_kyc | fake_investment | unknown |", "|---|---|---|---|---|"]
for lab in TYPES + ["other"]:
    g = [r for r in rows if r["label"] == lab]
    c = Counter(r["det"] for r in g)
    out.append(f"| {lab if lab != 'other' else 'benign'} (n={len(g)}) | " + " | ".join(str(c.get(k, 0)) for k in TYPES + ["unknown"]) + " |")
for name, key in (("PRIMARY: flagged = risk >= 0.6 (is_scam_likely, the app's alert rule)", "flag_risk"),
                  ("SECONDARY: flagged = scam_type != unknown", "flag_type")):
    tp = sum(r[key] for r in scam); fn = len(scam) - tp
    fp = sum(r[key] for r in ben); tn = len(ben) - fp
    out += ["", f"## Scam-vs-benign, {name}", "",
            f"- TP={tp} FN={fn} FP={fp} TN={tn}",
            f"- recall: {fmt(tp, tp + fn)}",
            f"- precision: {fmt(tp, tp + fp)}",
            f"- FP rate (benign flagged): {fmt(fp, fp + tn)}"]
sub = defaultdict(list)
for r in ben:
    sub[r["st"]].append(r)
out += ["", "## Benign by source type (secondary flag / primary flag counts)", ""]
for k, g in sorted(sub.items()):
    out.append(f"- {k}: n={len(g)}, flagged(type)={sum(r['flag_type'] for r in g)}, flagged(risk)={sum(r['flag_risk'] for r in g)}")
out += ["", "## Scam by source type", ""]
sc = defaultdict(list)
for r in scam:
    sc[r["st"]].append(r)
for k, g in sorted(sc.items()):
    out.append(f"- {k}: n={len(g)}, type-correct={sum(r['det'] == r['label'] for r in g)}, flagged(risk)={sum(r['flag_risk'] for r in g)}")
out += ["", "## Per item", "", "| id | label | detected | risk | stage | flag(risk) |", "|---|---|---|---|---|---|"]
out += [f"| {r['id']} | {r['label']} | {r['det']} | {r['risk']:.2f} | {r['stage']} | {r['flag_risk']} |" for r in rows]
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results" / "heldout-v2-2026-11-23.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out[:40]))
