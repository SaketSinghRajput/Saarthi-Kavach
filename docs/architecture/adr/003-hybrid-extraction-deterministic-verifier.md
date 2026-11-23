# ADR-003: Hybrid extraction with a deterministic Verifier, a planted-value check and code-rendered read-back

Status: Accepted by tech lead in v2 (2026-11-21) · Revised v2: valid-format synthetic phones, normaliser fixes, LLM made conditional, read-back rendered by code

## Context
- The DoD needs ≥ 9/10 planted details correct.
- C4 requires the gate to be code.
- Hinglish number words and browser STT output break plain regex.
- The verification review found three bugs:
  - "double X" did not count toward the joined run.
  - Stripping a leading 0 broke the `00000xxxxx` synthetic phones.
  - Read-back of non-planted values was undefined under the C2 filter.

## Options
1. LLM-only extraction.
2. Regex only.
3. **Hybrid**: normaliser + regex (sync), an LLM extractor only if measured recall is short, a deterministic Verifier, and a read-back by the decoy.

## Decision
**Option 3.**

**Normaliser:**
- Hindi, English and Devanagari number words, including `sifar`, `chhah` and `cheh`.
- `double`/`triple` expand to digit tokens **before** the 4-token join.
- Space-separated digit groups are joined.
- Spoken symbols (`at`, `at the rate`, `dot`, `underscore`, `dash`) are mapped only inside a candidate window.

**Intel LLM:** built only if run10 #1 regex recall is under 90%.

**Verifier rules:**
- Strip `+91`. Strip a single leading `0` only if 11 digits remain.
- Phone must match `^[6-9]\d{9}$`. The v1 synthetic-range regex exception is **removed**.
- UPI is lowercased before matching.
- Dedup.
- Planted check on **normalised** values.
- IFSC is looked up in a fictional bank table.

**Synthetic phones:** valid-format, visibly patterned numbers taken from the fixtures file (for example `9000000001`-`9000000009`). They are always shown with "(synthetic)" and never dialled (C1). This amends the C2 fixture format and needs security review acknowledgement.

**Read-back:**
- Issued only for goals that are `heard`, meaning valid format and planted. So it always passes C2.
- The line is rendered by code from a fixtures template; no LLM call.
- Non-planted or invalid values set the goal to `suspect`, which leads to a `REPEAT` directive, never a read-back.

**Only `status=verified` entities enter drafts.** This is enforced by the model validator plus a test.

## Consequences
+ The fast path takes milliseconds and is fully testable. Read-back can't mangle values and costs no LLM latency.
- In demo mode the planted check means the Verifier knows the answer set. Extraction must still produce the exact string. Explain this in the video and the README; production drops the check.
- Valid-format synthetic phones could in theory belong to someone real. This is mitigated because the system has no outbound channel, the value is labelled "(synthetic)", and every draft carries a watermark.
- Needs tests for false positives: "at the bank", "oh no", "do teen din", "ek minute".
