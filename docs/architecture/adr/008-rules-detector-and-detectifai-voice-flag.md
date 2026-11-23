# ADR-008: A rules-based intent Detector as the single owner of stage, plus DetectifAI as a cloned-voice flag

Status: Accepted by tech lead (2026-11-21)

## Context
- The team lead chose to trigger on conversation intent and scam patterns.
- v1 combined rules with a Lyzr classifier.
- Verification found that `stage` had two owners: the Detector and the Intel LLM.
- The PDF's headline claim is cloned-voice detection (F7, Should; fallback: "run detection on a pre-recorded clip").
- DetectifAI is **not a sponsor**.

## Options
1. Rules plus a Lyzr LLM classifier, with an optional DetectifAI check (v1).
2. **Rules only for intent/stage, plus DetectifAI on audio (2 h timebox, pre-recorded-clip fallback).**
3. An LLM-only detector.

## Decision
**Option 2.**

**Intent Detector:**
- `detector.py` uses a weighted lexicon from the fixtures, covering authority, urgency, payment_ask and pressure cues per scam type.
- It is the **sole owner** of `scam_type`, `stage` and `risk`.
- Stage never goes backwards within a call.
- Tests: for each scenario, the correct `scam_type` with `risk ≥ 0.6` by scammer turn 2.

**Voice flag (DetectifAI, off the critical path):**
- In scripted mode: the scammer's first TTS clip goes to `POST /v1/deepfake/detect`.
- The result is shown as a chip: "caller voice: synthetic X, flag not verdict" (FPR 8.4%).
- Fallback, as the PDF describes: show the stored result of a run on an internal document (not shipped), labelled "pre-recorded clip".
- In PTT mode it is not run.
- On screen it is labelled "partner API", never "sponsor".

## Consequences
+ Deterministic, fast, testable detection with one owner per field.
+ Real audio analysis backs the PDF's headline claim.
- One fewer Lyzr agent, so Lyzr visibility rests on the Scammer, Kamla and the voice cameo.
- The rules can miss novel scripts. That is acceptable for 3 fixture scenarios plus PTT, where the cue cards follow the scenarios.
