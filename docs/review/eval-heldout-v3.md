# Held-out evaluation v3 (pre-registered protocol, then results)

Date: 2026-11-23. Public-safe: numbers and method only, no transcript text. Data and per-item results stay in the gitignored `real-test/` folder.

## Pre-registration (written BEFORE any tuning or v3 collection)
Goal: raise alert recall (risk >= 0.6) without hurting precision. Baseline on v2 (frozen detector at commit 3e7a45f): scam-type 19/22, alert precision 14/15, recall 14/22, FP 1/14.

1. v2 becomes a DEV set. I analyse its 8 under-alerted scams and its 1 alert FP, and change only `fixtures/synthetic.sample.json` -> `detector_lexicon` and `app/agents/detector.py` (risk weighting / rules). Changes must be general phrase classes of each scam type (or general scoring logic), not item-specific strings. Existing tests (192+) and `tools/run10.py` offline 10/10 must stay green.
2. v3 TEST set: >= 30 new items (>= 18 scam across digital_arrest / fake_kyc / fake_investment, >= 12 benign incl. hard negatives such as genuine bank, courier, OTP advisories) from public sources not used in v1 or v2, redacted, each with source URL and date. v3 is collected before any detector output on it is seen. Labels are assigned from the source description only.
3. The detector is frozen at a commit hash, then evaluated on v3 exactly once (`real-test/evaluate_v3.py`, in-process, sockets disabled, no env, no `.env`). No edits after seeing v3 results; if v3 reveals problems they are reported, not fixed in this round.
4. Report v2 (dev, after tuning) and v3 (test) with 95% Wilson intervals: scam-type accuracy, alert precision / recall / false-positive rate. Whatever the numbers are. The v2 post-tuning figure is a training-set figure and must not be quoted as generalisation.
5. Success criterion set in advance: v3 alert precision not materially worse than 90% point estimate and recall above the v2 baseline of 63.6%. Missing it will be reported as a miss.

## What changed in the detector (commit ae5f971, frozen before v3 was scored)
- Corroboration bonus: when a scam type is selected, risk gets +0.04 per type-evidence point above 2 (cap +0.2).
- Generic words (account, pay, payment, link, download, group, bill, refund ...) now count 0.4x in the keyword risk.
- Advisory guard: awareness phrasing ("never share", "will never ask", "beware of", "hang up and call" ...) forces scam_type unknown, no alert, risk capped at 0.45. Known limit: a real scammer who recites such a line in a live call would be suppressed.
- Wider lexicon of scam-class phrases (investigation-agency / custody / imprisonment, freeze / passcode / liquidate / download, IPO / stock tips / trading app / withdrawal).
- Tests 192 -> 195; run10 offline 10/10.

## Results (frozen detector ae5f971, 95% Wilson)
v3 sets: 22 scam (8 digital_arrest, 7 fake_kyc, 7 fake_investment) and 14 benign (6 official advisories / hard negatives, 4 routine bank/telecom/utility texts, 4 consumer-commission or bank-side news). 18 distinct outlets/pages, none from v1 or v2. Evaluated once.

| Metric | v2 DEV (after tuning; not a generalisation figure) | v3 TEST (unseen) |
|---|---|---|
| Scam-type accuracy | 22/22 = 100% [85.1, 100] | 21/22 = 95.5% [78.2, 99.2] |
| Alert recall (risk >= 0.6) | 22/22 = 100% [85.1, 100] (was 14/22 = 63.6%) | 20/22 = 90.9% [72.2, 97.5] |
| Alert precision | 22/22 = 100% [85.1, 100] (was 14/15) | 20/20 = 100% [83.9, 100] |
| Alert FP rate | 0/14 = 0% [0, 21.5] (was 1/14) | 0/14 = 0% [0, 21.5] |
| Any-type flag FP rate | 3/14 = 21.4% | 2/14 = 14.3% [4.0, 39.9] |

v3 confusion: digital_arrest 8/0/0/0, fake_kyc 0/7/0/0, fake_investment 0/0/6/1 (unknown), benign: 1 typed digital_arrest, 1 typed fake_kyc, 12 unknown. The pre-registered criterion (v3 precision point estimate >= 90%, recall > 63.6%) is met.

## Caveats
- Same limits as v2: scam items are third-person press descriptions of what callers said, not live ASR speech; benign items are written advisories, help texts and news, not recorded genuine calls. Collected by sub-agents from fetched page text (paraphrase allowed, redacted); single labeller per item, labels from source description.
- v3 and v2 were drawn the same way (news-heavy), so the lexicon may have fitted the "press-report" register. Real call transcripts could behave differently; this is not a production accuracy claim.
- Intervals are wide (n=22 / 14). The upper bound on false-positive rate is ~21% on benign.
- Six benign items are undated web pages; their date is the retrieval date.
- v3 is now consumed: any further tuning needs a fresh set (v4).
