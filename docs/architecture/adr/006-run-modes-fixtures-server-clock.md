# ADR-006: Run-mode flags, one fixtures file, server-owned pacing, and a 10-in-a-row runner

Status: Accepted by tech lead in v2 (2026-11-21) · Revised v2: replay deferred to the finale, `INPUT_MODE` added, `PACING` simplified to a speed multiplier, live pass reduced to 3 calls

## Context
The DoD needs:
- 10 unaided runs,
- ≥ 9/10 planted details,
- ~3 s replies,
- a recorded video by 2026-11-24 22:00 IST.

The red team noted that for a *recorded* video, the fallback is simply the best screen-recorded take. Replay through the dashboard only matters for the live finale on 2026-11-28.

## Options
1. Live only, re-recording until a good take.
2. Mode flags, fixtures, and run10 (v1, including replay).
3. **Option 2 without replay until after submission.**

## Decision
**Option 3.**

**Flags:**

| Flag | Values |
|---|---|
| `INPUT_MODE` | `scripted`, `ptt` (ADR-007) |
| `APP_MODE` | `live` (Lyzr Scammer), `semi` (scripted beats; entity beats released when Kamla asks) |
| `PACING_SPEED` | `1.0` (real time) or `0` (no waits) |

**`fixtures/synthetic.sample.json`** holds:
- the ground truth,
- the C2 allowlist,
- the per-scenario goal sets,
- the PTT cue cards,
- the glosses for subtitles.

It is written first, tonight.

**`run10.py`:**
- 10 `semi` runs at speed 0, rotating the 3 scenarios, with correction variants.
- Then 3 `live` calls at speed 1.0 for latency, n ≥ 45 turns.
- Output: per-run JSON plus a summary labelled by mode, covering:
  - entities hit,
  - substantive reply p50/p95,
  - compute p50/p95,
  - filler rate,
  - guard trips,
  - drafts produced.

**Replay mode** (about 2.5 h) is built 25-27 Nov, and only if we are shortlisted.

## Consequences
+ A cheap, deterministic regression signal, and about 2.5 h saved before submission.
- No replay safety net on recording day. The mitigation is the Monday-night safety take plus several takes on Tuesday.
- The video must show at least one `live` take and label any `semi` take.
