# Held-out evaluation v2 (n=36), frozen detector, evaluated once

Date: 2026-11-23. Public-safe summary: numbers and method only, no transcript text. The data and per-item results stay in the gitignored `real-test/` folder.

## Method
- Detector frozen at git HEAD (`app/agents/detector.py`, `fixtures/synthetic.sample.json` unchanged across the last three commits). Run once on the new set; no lexicon edits, no threshold changes, no re-run after seeing results.
- Run in-process on text with sockets disabled (no Docker, no network, no `.env`, no environment read). The exported HEAD copy was imported, not the working tree.
- Text only, from public pages: news articles, bank/police advisories, the National Consumer Helpline portal and a consumer-commission report. Each item stores source URL and date. Names, numbers, app names and links are replaced with tokens. No audio. Data never committed, never used in the demo.
- Labels were assigned by the evaluator from the source's own description (3 scam types + benign). Intervals are 95% Wilson.

## Set composition
- 22 scam: 9 digital_arrest, 6 fake_kyc (incl. bank-impersonation OTP), 7 fake_investment. Source types: 20 news, 2 advisory.
- 14 benign: 10 consumer-helpline / company or bank replies, 2 news (genuine bank-side narration), 2 official advisory texts that contain scam vocabulary (hard negatives).

## Results
| Metric | Value |
|---|---|
| Scam-type accuracy (22 scam items) | 19/22 = 86.4% [66.7, 95.3] |
| digital_arrest | 9/9 = 100% [70.1, 100] |
| fake_kyc | 5/6 = 83.3% [43.6, 97.0] |
| fake_investment | 5/7 = 71.4% [35.9, 91.8] |
| Primary alert rule (risk >= 0.6): recall | 14/22 = 63.6% [43.0, 80.3] |
| Primary: precision | 14/15 = 93.3% [70.2, 98.8] |
| Primary: false-positive rate on benign | 1/14 = 7.1% [1.3, 31.5] |
| Secondary rule (any scam_type output): recall | 19/22 = 86.4% [66.7, 95.3] |
| Secondary: precision | 19/23 = 82.6% [62.9, 93.0] |
| Secondary: false-positive rate | 4/14 = 28.6% [11.7, 54.6] |

Confusion (label rows, detected columns: digital_arrest / fake_kyc / fake_investment / unknown): digital_arrest 9/0/0/0; fake_kyc 0/5/0/1; fake_investment 0/0/5/2; benign 0/4/0/10.

Failure modes: 3 scam items typed `unknown` (1 SMS-link KYC, 2 investment-group stories with no payment cue); 8 scam items below the 0.6 alert threshold (typed correctly but low risk); the 4 benign items given a scam type were bank-side narrations or advisories that mention OTP, card or blocked. The one benign item over the alert threshold was an official advisory text, not a call.

## Caveats (read before quoting)
- Public sources almost never print verbatim call speech. Most scam items are third-person press paraphrases of what the caller said ("Caller said ..."), not spoken scripts, so this tests the lexicon on reported scam narratives, not on live ASR output.
- Most benign items are written company/bank replies or reported bank-side actions, not genuine voice calls; none is a real recorded genuine call. The benign false-positive rate is therefore likely optimistic for real speech, and the 2 advisory items are an adversarial lexical stress test, not typical traffic.
- n=36 (22/14): the intervals are wide (FP rate upper bound 31.5% primary, 54.6% secondary). Per-type n is 6 to 9, so per-type figures are indicative only.
- Single evaluator, single selection pass; sources were chosen for availability of reported text, which biases toward well-covered stories. Earlier set rt-001..016 (n=16) is separate and not pooled here.
- Not a production accuracy claim. Do not use these numbers to tune the lexicon; a new unseen set is needed for any post-tuning claim.
