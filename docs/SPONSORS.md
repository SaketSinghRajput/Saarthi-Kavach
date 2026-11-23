# Sponsor usage notes

Four of the five mandatory sponsors are live in the product. Agent37 is packaged and deploy-ready but **not deployed** (card gate, see its section). Each section: how we use it, where in the code, evidence, fallback, and what we would do with more time. Numbers come from an internal document (not shipped) (live runs, 2026-11-23) unless a command is given. Line numbers are as of commit `8990e6f` plus working tree and may drift; function names are stable.

## Lyzr

**How.** Three live Lyzr agents (gpt-4o-mini) play Kamla ji (the decoy) and the Scammer. Each turn the app sends a window of the call plus a steering directive. Scammer speech is wrapped as untrusted text and capped at 500 characters.

**Code.**
- `app/agents/lyzr_client.py`: `LyzrClient._chat` (:85), `kamla` (:97), `scammer` (:126), `_canned` offline path (:111).
- `app/orchestrator.py`: filler line and timeout around the Kamla task (~:288-304).
- `app/config.py`: `lyzr_turn_budget_s = 3.5` (:75), `kamla_timeout_s` (:73).

**Evidence.** Response contract parses. Reply p95 2.9-3.7 s in the preflight spike (S1), 2.9-9.9 s across live calls on 2026-11-23 (4.2-6.8 s in the last five, which covered all three scenarios); dead air stays at p95 1.20-1.21 s because cached fillers cover the wait (HUD, an internal document (not shipped)). Spend is from the Lyzr account credits and is unconfirmed.

**Fallback.** Canned Kamla lines and scripted scammer beats from fixtures.

**Known limit.** The delay is Lyzr-side overhead. No model choice fixed it. A filler line ("haan beta, ek minute...") covers the gap, and the dashboard latency HUD shows it.

**With more time.** Try streaming replies to start TTS before the full text arrives. Measure p95 over more than a handful of calls.

## Band

**How.** One shared agent room with 6 identities (saarthi, detector, kamla, intel, verifier, reporter). The only handoff is the Verifier telling the Reporter `@reporter report job rj_<12hex> ready`. No transcript text goes into Band (gate G7). The Reporter pulls verified data from our API by job id.

**Code.**
- `app/contracts.py`: `HANDOFF_RE` (:17) accepts only that exact sentence.
- `app/orchestrator.py`: handoff text built at ~:414.
- `app/integrations/band_mirror.py`: `BandMirror.post_ex` (:27), `live_for` (:20).
- `app/agents/reporter_band.py`: Reporter side of the handoff.
- Event shape: `docs/architecture/EVENTS.md` (`band` event, `draft.trigger`).

**Evidence (live, 2026-11-23; post shape `d42825e`, listener `4080c8b`).** The app posts to the Band room with participant-object mentions, body `{"message":{"content","mentions":[{id,handle,name}]}}`. In a real live call (scripted scammer, live Lyzr Kamla, Kokoro voice, Finch live, AdaL) the Verifier posted the handoff and the Reporter, polling the room with its own Band key, woke from the stored mention and produced both drafts with `trigger=band_mention`. Band message id `a317c0ce-13cd-4821-b576-6d27e3833955`. Screenshot an internal document (not shipped); recording an internal document (not shipped) (local, gitignored). An earlier post was also accepted (`218b50f8-eb8d-41bf-80b1-0a353ece9c24`). Every `band` event carries `mirrored:true/false`, so the stream never overstates it.

**Fallback.** If no mention arrives within `REPORTER_FALLBACK_S`, the Reporter wakes in-process through the same strict regex and the draft carries `trigger=direct_fallback`.

**With more time.** Let more than one step decide through Band (for example Intel asking the Verifier to recheck). Today it carries one decision.

## AdaL

**How.** The Reporter calls the AdaL CLI headless to write the 4-6 sentence narrative for the two drafts. It runs off the call path, so the call never waits. The template draft shows first and the AdaL text replaces it.

**Code.**
- `app/agents/reporter.py`: `Reporter._adal_narrative` (:202), `build_adal_task` (:39), `parse_adal_output` (:107, reads the stream-json `{"type":"answer"}` event), `template_narrative` (:51), `adal_unavailable` policy event (~:234).
- `app/safety/adal_proxy.py`: `AdalProxy`, a CONNECT proxy that refuses any host or port but the allowed model host (gate G3).
- `app/config.py`: `ADAL_*` settings. AdaL is refused when `ADAL_ALLOWED_HOST` is empty.

**Evidence.** Live through the CLI app path (gemini flash), tools disabled, behind the proxy. 4-6 sentences in about 23 s. No identifiers leaked into the narrative. 3 paid AdaL calls used so far (an internal document (not shipped)).

**Fallback.** Template narrative; an `adal_unavailable` policy event is emitted. The hosted image has no AdaL CLI, so it uses the template.

**With more time.** Ship the CLI in the hosted image. Cut the 23 s with a smaller prompt.

## Finch

**How.** The Scout asks Finch's public catalogue which skills exist for the detected scam type. It is discovery only. Every result carries `role: "discovery_only"`. We never claim Finch executes anything or that anything was bought.

**Code.** `app/integrations/finch_scout.py`: `FinchScout.scout` (:36). Keywords per scam type come from the fixture (`finch_keywords`) and are tried in order, inside a 4 s total budget (`BUDGET_S`). Up to 3 skills are returned with name, slug, category, free flag and a 100-character summary. Endpoint: `https://www.finchtech.ai/api/market/search`, read-only.

**Evidence.** Live: for example keyword "scam" returned 13 skills. Account identity was verified through the Finch MCP.

**Fallback.** A dated snapshot of real catalogue results from the fixture (`finch_snapshot`), flagged `live: false`.

**With more time.** Let the Reporter cite a found skill in the narrative. Today the skills show in the Scout panel only.

## Agent37

**Status (2026-11-23): not deployed.** Saket's cards were all declined at Agent37's Stripe gate, and Agent37 has no card-free tier: the $5 starter credit needs a card, API signup gives $0 and instance create returns `402 insufficient_balance` (sources and what we tried: an internal document (not shipped), `docs/PROBLEMS.md` #13). What exists: an Agent37-ready image and a one-command deploy script, both built and verified locally. We do not claim it ran on Agent37. The demo URL fallback is a Hugging Face Docker Space (`deploy/hf-space/README.md`). If Agent37 credits arrive, the deploy script is ready to run.

**How (intended).** Agent37 would host the whole service as one Docker image: FastAPI backend, dashboard and pre-rendered audio.

**Code and files.**
- `Dockerfile`: `python:3.12-slim`, linux/amd64, non-root uid 10001, 322 MB.
- `deploy/agent37_deploy.py`: builds the template in Agent37's cloud, creates the instance, opens port 8000, polls `/api/health`, prints the demo URL. Has `--dry-run` and `--teardown`.
- `deploy/DEPLOY.md`: runbook, cost, unverified API points.
- `app/integrations/tts.py`: `_synth_kokoro` (:171) serves cached clips when the engine is absent, so the hosted image can play audio.

**Evidence.** Image boots with no env vars and no network (`docker run --network none`). Read endpoints need a passcode (401 without, 200 with `X-Passcode`). Expected cost about $1 for six days (`deploy/DEPLOY.md`, estimate from Agent37 docs prices). Live deploy on Agent37: none (see Status).

**Fallback.** Hugging Face Docker Space, or run locally with uvicorn.

**With more time.** Include Kokoro and the AdaL CLI in the image. Verify the API points marked unverified in `deploy/DEPLOY.md`.

## Not a sponsor

DetectifAI gives an optional deepfake flag on one clip. It is a flag, not a verdict, and is not part of any sponsor claim. Kokoro TTS is local and Apache-2.0.
