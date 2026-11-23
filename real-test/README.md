# real-test — sandbox for real-world scam-call language

Purpose: check that the Detector and Intel hold up on REAL scammer language, not just our synthetic fixtures.

## Rules (non-negotiable)
- Text transcripts only, from public sources (news, government/bank advisories, published scam-baiting transcripts). No audio, no voices.
- Every identifier is redacted before saving: phone, UPI, account, IFSC, names, addresses, case numbers → placeholders like `<PHONE>`, `<UPI>`, `<ACCOUNT>`, `<NAME>`.
- Every sample cites its source URL.
- `data/` and `results/` are gitignored. Never used in the demo or video, never sent to Lyzr/Band/AdaL/any API.
- Evaluation runs only in Docker with `--network none` (see run_sandbox.sh).

## Format: data/<id>.json
{"id", "source_url", "source_type": "news|advisory|scambait|other", "published", "scam_type": "digital_arrest|fake_kyc|fake_investment|other",
 "language": "hi|en|hinglish", "turns": [{"speaker": "scammer|victim|unknown", "text": "..."}], "redactions": <int>, "notes"}
