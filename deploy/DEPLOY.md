# Deploying the Saarthi public demo on Agent37

Agent37 is the mandatory hosting sponsor. Everything below is one command once the key exists. Nothing here has been run against the real Agent37 API (no account yet); see "Unverified" at the end.

## 5-step runbook (Saket)

1. **Create the Agent37 account** at https://www.agent37.com and claim the free $5 credit (a card is required; it is not charged until you top up). Create an API key (`sk_live_...`).
2. **Put the key in `.env`** (never commit it): `AGENT37_API_KEY=sk_live_...`. The script always sets `HOSTED_SCRIPTED_ONLY=true` (see Open access below). Any other app settings already in `.env` (Lyzr, TTS, Band...) are passed through by name.
3. **Preview, then deploy.**
   `py -3.12 deploy/agent37_deploy.py --dry-run` prints the planned API calls with secrets redacted and makes no network calls.
   `py -3.12 deploy/agent37_deploy.py` builds the template in Agent37's cloud (no local Docker needed), creates the instance, opens port 8000 publicly, polls `/api/health`, and prints `PUBLIC DEMO URL: https://<id>-...agent37.app`.
4. **Verify.** Open the URL (dashboard loads), `GET <url>/api/health` returns 200, `GET <url>/api/state` returns 200 (open demo). Run one scripted call end to end. Put the URL in the submission form before 2026-11-24 19:00 IST.
5. **Teardown after judging:** `py -3.12 deploy/agent37_deploy.py --teardown --delete-template` (reads the instance id saved in `deploy/.agent37_state.json`, or pass `--instance-id <id>`). Billing is per minute, so deleting stops cost; the disk is wiped on delete.

## Open access (no passcode)

The demo is open: no passcode on reads or writes (decision 2026-11-24, so judges can click straight in). What keeps a public URL safe: `HOSTED_SCRIPTED_ONLY=true` (the scammer is scripted, never the live LLM), `START_RATE_PER_MIN` (default 12), one call at a time, turn/time caps, synthetic data only (`DEMO_SYNTHETIC_ONLY`), and drafts that are never sent. `INTERNAL_TOKEN` still guards `/api/internal/*`.

## Image notes

- `Dockerfile` is `python:3.12-slim`, linux/amd64, non-root uid 10001, 322 MB. Runtime deps only (`deploy/requirements-runtime.txt`: fastapi, uvicorn, pydantic, httpx). No Kokoro/torch.
- It boots with **no env vars at all** (offline/stub mode). Verified with `docker run --network none`.
- App code lives in `/opt/saarthi` because Agent37 mounts the instance disk over the image user's home. The SQLite DB is at `/opt/saarthi/data` (writable; persists across restart, wiped on delete).
- `prompts/` is not copied: nothing in `app/` reads it at runtime.
- **Pre-rendered audio caveat:** the 112 cached `.wav` files are served at `/audio/<hash>.wav` as static files, but `TTS` with `TTS_PROVIDER=kokoro` returns the stub (no `audio_url`) whenever the Kokoro package/model is absent, even if the cached file exists (`app/integrations/tts.py`, `_synth_kokoro`). So the hosted demo plays no audio unless that function checks the cache before the `engine is None` early return (owner: app/integrations engineer), or you use `TTS_PROVIDER=elevenlabs` (spends money; needs approval).
- AdaL reporter CLI is not in the image; the app's `adal_unavailable` fallback applies.

## Cost

Entry sandbox (2 vCPU / 4 GB / 4 GB disk, default type) is about $4.76/month always-on (docs: $0.80/vCPU-mo, $0.70/GB RAM-mo, $0.09/GB disk-mo). For about 6 days of judging that is roughly **$1** (6/30 x $4.76 = $0.95), covered by the $5 free credit. Cloud builds are free on a funded wallet. Our total spend cap is $20 with about $10 already used, so this fits; no top-up should be needed. Auto-sleep is off, so there is no 504 wake delay; the 15-minute idle timeout applies to connections with no traffic.

## Unverified Agent37 API points (from llms-full.txt, not exercised live)

- Raw cloud-build endpoints (`/v1/template-builds`, upload via presigned PUT, `/start`, `/logs?offset`) are taken from the docs; the terminal status strings other than `succeeded` (we also treat `failed`/`cancelled`/`error` as terminal) are assumed.
- That `public_ports` in the create body returns `public_ports[].url` in the response, and the shape of `GET /v1/instances/{id}/public-ports` (the 409 fallback) are inferred from the docs examples.
- A public port's URL form (random slug vs `prefix-id.agent37.app`) is whatever the API returns; the script prints it.
- Whether the free $5 credit satisfies the "one day of running rate" balance gate at create (needs about $0.16), and whether the wallet must be topped up first.
- Outbound firewalling: docs say outbound is limited to the public internet; Lyzr/TTS/Band hosts should be reachable but this is untested.
- Build context upload size is about 24 MB (limit 1 GB); the built image is about 322 MB (limit 15 GB).
