# Event contract: `GET /api/events` (SSE) and REST

Read endpoints (`/api/state`, `/api/events`) need the passcode when `APP_PASSCODE` is set: header `X-Passcode`, or query param `pc` (EventSource cannot set headers). `pc` is scrubbed from access logs.

Owner: backend. Consumers: the dashboard (frontend) and `tools/`. All data is synthetic.

## Transport

- `GET /api/events` is a standard `text/event-stream`. It is public and read-only (C7).
- Each message is `id: <event_id>`, `event: <type>`, `data: <json>`. Use `EventSource.addEventListener(<type>, ...)`. A named event does not fire `onmessage`.
- Replay: `GET /api/events?since=<event_id>` (or the `Last-Event-ID` header that `EventSource` sends on reconnect) replays everything after that id, then continues live. With neither, only new events are streamed. For a page reload, call `GET /api/state` first, then connect with `?since=<state.last_event_id>`.
- Keep-alive comment `: keepalive` every 15 s. `retry: 2000` is sent first.
- Every `data` JSON has the envelope keys `event_id` (int, monotonic), `event` (type), `ts` (ISO-8601 UTC) and `call_id`, flattened together with the payload below. Payload keys never collide with the envelope keys. Note that `entity.id` and `entity.type` are payload fields, so use the SSE `event:` name (or `data.event`) as the event type.
- Render text with `textContent` only (C5). Phone numbers must be shown with the suffix "(synthetic)" (G1): render `display` (entity, and each goal in `goal_state`) and `text` / `gloss_en` / `body` as given, never the bare `value`.

## Event types

| `event` | Fields | Notes |
|---|---|---|
| `call_status` | `call_id`, `state` idle\|ringing\|active\|ended, `scenario`, `input_mode`; on ended also `end_reason` (all_resolved, max_turns, max_duration, no_progress, kill_switch, ptt_idle, error) | `ringing` resets the client view of the previous call. |
| `turn` | `seq`, `speaker` scammer\|kamla\|filler, `text`, `gloss_en` (English subtitle, null for live lines and PTT), `audio_url` (null when no TTS key), `t_start` (ms since call start, simulated clock so it is identical at any PACING_SPEED), `latency_ms` (Kamla compute latency, 0 otherwise), `source` (scripted, human_stt, lyzr_live, canned, readback, filler); Kamla turns also `directive`, `filler_played`, `llm_ms` (Lyzr/LLM part of `latency_ms`), `tts_ms` (voice render part; `latency_ms` = `llm_ms` + `tts_ms`) | `seq` increases across all speakers. A filler turn precedes the Kamla reply it covers. |
| `detector` | `scam_type`, `stage` (hook, authority, urgency, payment_ask, pressure, unknown), `risk` 0-1, `signals[]`, `is_scam_likely`, `turn_seq`, `deepfake` `{flag, source}` | `deepfake.source` is `stub:not_checked` offline. It is a flag, not a verdict. |
| `entity` | `id` (stable per type+value), `type` upi\|bank_account\|ifsc\|phone, `value` (bare, never carries the suffix), `display` (phones carry " (synthetic)": render this, G1), `status` heard\|suspect\|confirmed\|given_up\|superseded, `ifsc_bank` (IFSC only, fictional bank from the lookup), `resolved_by` (`action_agent:ifsc_lookup` on ifsc with ifsc_bank, `action_agent:upi_psp_lookup` on upi), `upi_psp` (upi only: offline PSP label from the handle suffix, e.g. "Axis (PSP)", else null) | Emitted on every status change. A value replaced by a correction goes to `suspect`, then `superseded` once the corrected value is confirmed. Superseded values never appear in drafts. Goals still `missing` have no entity (the UI derives grey chips from `goal_state`). |
| `goal_state` | `goals` `{type: {status missing\|suspect\|heard\|confirmed\|given_up, value, ask_attempts, readback_attempts, method_failed_used}}`, `minutes_wasted`, `pending_readback`, `turn_seq`, `turns_without_progress`, `end_reason`, `directive` `{kind, target, tactic_id}` | After each steering decision and after each Kamla turn. |
| `band` | `from_agent`, `to_agent` (or null), `text`, `kind` post\|handoff\|thought, `mirrored` bool, `t_ms` (ms since call start, same simulated clock as `turn.t_start`), `band_msg_id` (string id from the Band POST response when `mirrored:true` and the response has id/message_id/messageId, else null) | Emitted whether or not Band is configured. `mirrored:false` means the message did not reach Band (no key, or the post failed). Text is built by code, never raw transcript (G7). The single `handoff` is exactly `@reporter report job rj_<12 hex> ready`. |
| `metrics` | `minutes_wasted`, `substantive_p95_ms`, `compute_p95_ms`, `llm_p95_ms`, `tts_p95_ms`, `dead_air_p95_ms`, `filler_rate`, `turns` | After each Kamla turn. `compute_p95_ms` is p95 of real Kamla compute (LLM + TTS) per turn, the same number as each Kamla `turn.latency_ms`. `substantive_p95_ms` is the user-perceived gap = real compute + the 400 ms human pause (fillers excluded); it is never below `compute_p95_ms` (compute is no longer hidden behind the scammer clip, since a live caller cannot be answered before they finish speaking). The HUD reply p95 vs the 3.5 s budget uses `substantive_p95_ms`. `llm_p95_ms` / `tts_p95_ms` are the p95 of the LLM and voice-render parts of that compute. `dead_air_p95_ms` is p95 of the silence between the scammer clip ending and the first Kamla audio (a cached filler or the real reply): with a filler it is the filler wait (1.2 s) plus filler render (about 0); without one it is max(0, compute minus the part hidden behind the playing scammer clip) plus the 400 ms pause; a PTT caller has already finished speaking so nothing is hidden. The HUD primary row is `dead_air_p95_ms` vs a 1.5 s budget; the secondary row is `compute_p95_ms` as 'Kamla answer p95' with its `llm_p95_ms` + `tts_p95_ms` split. Replies from live Kamla are hard-trimmed to 2 sentences / 22 words (read-backs and anything with an identifier are never trimmed). Offline stub latencies are near 0, so these are only meaningful with live adapters. |
| `draft` | `draft_id`, `kind` bank_alert\|helpline_1930, `case_id` (SK-<IST date>-<6 hex>, identical on both drafts of a call), `body` (plain text, watermarked), `status` pending\|approved, `job_id`, `sha256`, `narrative_source` adal\|template, `trigger` band_mention\|direct_fallback, `band_msg_id` (Band message id that woke the Reporter when `trigger=band_mention`, else null), `watermark` | Emitted as `pending` when created and again as `approved`. Approve only flips a status (C1). |
| `skill` (extra) | `scam_type`, `skills[] {name, slug, category, free, summary, source}`, `total` (catalogue hits), `role` always `discovery_only`, `live`, `query` | Finch scout result. `live:false` is the local snapshot. Never claim Finch executes skills. |
| `agent_status` (extra) | `agents` `{kamla, scammer, reporter, scout, room, host}`, each `{platform, mode live\|stub}` (`scammer.mode` is `scripted` when HOSTED_SCRIPTED_ONLY is on: default on with a real APP_PASSCODE, off with the dev passcode, override with HOSTED_SCRIPTED_ONLY=true/false) (Lyzr, Lyzr, AdaL, Finch, Band, Agent37\|local) | Emitted after `ringing` and again when the scout result is known. Live only if the adapter is enabled and has its key (host: AGENT37_URL or AGENT37_INSTANCE set). Same object at `GET /api/state` `agent_status`. |
| `call_summary` (extra) | `label` always `simulated call`, `engaged_s` (scammer time engaged, seconds), `identifiers_verified` (confirmed by read-back), `identifiers_corrected` (values superseded by a correction), `drafts`, `fillers`, `turns`, `session` (running tally, same shape as `session_impact`) | Once per call after the handoff. Impact proxies only, never a losses-prevented claim. `GET /api/state` also returns `call_summary` and `session_impact` `{label, calls_n, engaged_s, identifiers_verified, identifiers_corrected, drafts, fillers, turns}` (in-memory running tally since process start). |
| `policy` (extra) | `kind` c2_filter\|adal_tool_attempt_aborted, `detail` | Safety controls firing. |

Note on `draft.trigger`: after the Verifier posts the handoff to Band, the Reporter polls `GET {band}/chats/{room}/messages?sort_order=desc&limit=10` with its own key (about every 1 s, backing off on errors/429) for up to REPORTER_FALLBACK_S, parses the stored mention form (`@[[id]] report job rj_<12 hex> ready` or plain `@reporter ...`) with the strict regex, looks the job up in the store and runs it with `trigger=band_mention` + `band_msg_id`. If nothing arrives (Band off, no key, post failed, timeout) the in-process path runs and the draft says `direct_fallback`.

## REST

Mutating endpoints need the passcode (C7): header `X-Passcode: <APP_PASSCODE>` (start and approve also accept `{"passcode": ...}` in the body). Wrong or missing gives 401. If `APP_PASSCODE` is unset, an ephemeral dev passcode is printed at server start.

| Method and path | Body | Result |
|---|---|---|
| `POST /api/call/start` | `{scenario: digital_arrest\|fake_kyc\|fake_investment, input_mode: scripted\|ptt}` | 200 `{call_id,...}`; 409 if a call is running; 429 above `START_RATE_PER_MIN` |
| `POST /api/ptt` | `{text}` 1-500 chars (501 gives 422) | 200; 409 if there is no active ptt call. `human_stt` turn. |
| `POST /api/kill` | none | Kill switch: the call wraps up on the next turn (`end_reason: kill_switch`). |
| `POST /api/drafts/{id}/approve` | `{approver?: str}` | 200 `{status: approved, sha256}`; 404, 409 if already approved. Appends to `data/approvals.jsonl`. Nothing is sent anywhere. |
| `GET /api/state` | | Snapshot for reload: `call, turns[], detector, entities[], goal_state, band[], metrics, drafts[], skills[], last_event_id, active` |
| `GET /api/health` | | `{ok, active, mode, band_last_post, adapters{lyzr,tts,band,adal,finch,detectifai}}`: which adapters are configured. `band_last_post` is null until a live Band post happens this process, then true/false for the most recent one (`adapters.band` stays the configured flag). |
| `GET /api/runs`, `GET /api/runs/{id}` | passcode | Per-call run log (`data/runs/<call_id>.json`, gitignored): `{run_id, scenario, modes, turns[{seq,speaker,source,t_start,llm_ms,tts_ms,filler_ms,dead_ms,latency_ms}], metrics, call_summary, drafts[{kind,trigger,band_msg_id,case_id,sha256}]}`; no transcript text, no identifier values. List: `{runs:[{run_id,scenario,dead_air_p95_ms}]}`. `tools/runlog_report.py <run.json>` recomputes dead-air, answer (p95 of per-turn llm+tts), llm, tts p95 and n. `metrics.answer_p95_ms` is that per-turn answer p95. |
| `GET /api/internal/report-jobs/{job_id}` | | Needs `X-Internal-Token`. The Reporter's job data, with no transcript. |
| `GET /audio/<hash>.mp3` | | TTS cache, only when a TTS key is set. |
| `GET /` | | `web/` static (placeholder logger). CSP `default-src 'self'; script-src 'self'; media-src 'self' blob:`. |

## Typical order for one call

`call_status ringing, active` then (`band`, `turn scammer`, `detector`, `entity`*, `goal_state`, `turn kamla`, `metrics`, `goal_state`) repeated, then `call_status ended`, then `band handoff`, `draft pending` x2, `band drafts ready`.

`PACING_SPEED` is a speed multiplier (1 = real time, 2 = twice as fast, 0 = no waits); `t_start` is on a simulated clock and does not depend on it. `GET /favicon.ico` returns 204.

`skill` / `agent_status.scout`: Finch runs as a background task (budget 8 s) so a slow GET never stalls a turn; `skill` arrives when it finishes. `scout.mode` is `live` only if the last scout result was live (before the first scout of a call it reflects FINCH_ENABLED). `www.finchtech.ai` is always in the egress default hosts regardless of `EGRESS_ALLOWLIST` (read-only GET).
