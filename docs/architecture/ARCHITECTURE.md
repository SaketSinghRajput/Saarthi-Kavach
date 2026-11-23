# Saarthi Kavach: Hackathon Architecture (v2.0)

| Field | Value |
|---|---|
| Owner | Team |
| Version / date | **v2.0**, 2026-11-21 (v1.0 the same day) |
| Status | v2 incorporates the red-team review and the verification review under tech lead decisions A, B and C. Awaiting team lead approval. |
| Inputs | an internal document (not shipped) · an internal document (not shipped) · an internal document (not shipped) · `docs/security/threat-model.md` (C1-C10) · an internal document (not shipped) · an internal document (not shipped) |
| Dates (confirmed by tech lead) | Submission: **2026-11-24 22:00 IST**, as a recorded video. Live finale for the top 10: **2026-11-28**, Bengaluru. |
| Sponsors | Lyzr, Band, Agent37, AdaL, Finch. DetectifAI is used, but it is **not a sponsor**. |
| ADRs | `adr/001` to `adr/008` |
| Build plan | `BUILD-PLAN.md` |

## CHANGELOG

**v2.0 (2026-11-21)**
- **Push-to-talk mode added** ("take the scammer's phone", ADR-007).
  - `INPUT_MODE=scripted|ptt`. The browser Web Speech API (hi-IN / en-IN) feeds the same orchestrator.
  - The normaliser now handles Devanagari number words, `sifar`, and "at the rate".
  - Kamla's voice stays synthetic.
  - Pending a team lead waiver for a human voice as input. If the waiver is denied, a synthetic clip is played into the mic instead.
- **Detection.**
  - The Detector is now rules only, and the Detector LLM is dropped.
  - DetectifAI cloned-voice detection is promoted: timeboxed at 2 h, with the PDF F7 fallback of a pre-recorded synthetic clip (ADR-008).
  - `stage` now has a single owner: the Detector rules.
- **One real Band handoff** (ADR-002).
  - The Verifier @mentions the Reporter with a `job_id` only.
  - The Reporter is a Band SDK agent. It pulls verified data from our API and runs AdaL.
  - AdaL's input is verified fields plus a summary built by code. It never sees raw transcript.
  - The AdaL subprocess is now under the egress policy, through a local allowlisting proxy (ADR-004).
- **Cuts.**
  - Replay mode is deferred to the finale.
  - The Detector LLM is removed.
  - The Intel LLM is built only if regex recall is below 90% in run10 #1.
  - Also gone: schema-export tool, ULIDs, circuit breaker, Band priority dropping, the separate fast-pacing path.
- **Steering fixed.**
  - State update now runs before directive selection, so the read-back is parsed before a new directive is chosen.
  - `suspect` is now actually set.
  - Each scenario has its own goal set, and a `given_up` status makes completion reachable.
  - METHOD_FAILED is used at most once per goal.
  - The read-back line is now rendered by code.
  - New vocabulary mapping table.
- **Extraction fixed.**
  - Synthetic phones now use a valid-format pattern listed in the fixtures file. The `00000` regex special case is removed.
  - Double/triple tokens now count toward the digit run.
  - A leading 0 is stripped only when 11 digits remain.
  - False-positive tests added.
  - New action: the IFSC is looked up in a fictional bank table.
- **Metrics.**
  - The DoD latency gate now measures **substantive reply start** (fillers excluded) and **compute latency**, both at p95 ≤ 3 s.
  - The filler rate is reported.
  - `minutes_wasted` is now defined.
- **Contracts.**
  - `ReportDraft.entities` enforces `status=verified`.
  - Timeouts are split: Kamla 6 s, Scammer 8 s.
  - The endpoint is `/api/events` everywhere.
- **Spikes hardened** (BUILD-PLAN §2):
  - Lyzr RAI/PII settings, refusal check, fresh session per turn.
  - TTS bake-off including Sarvam.
  - Band privacy, REST event shape and SDK mention receive.
  - Agent37 **outbound** network.
  - AdaL BYOK on Agent37, exit codes, proxy.
  - Lyzr voice cameo moved to day 1.
  - Finch-skill-into-AdaL test (45 min).
  - Browser STT test.
- **C10 deviation recorded:** the TTS uses a third-party catalog voice rather than Lyzr's stock voices (ADR-001).
- **New sections:** traceability matrix (§15) and finale readiness (§16).
- **Mermaid:** text escaped (no angle brackets or `<=` inside message text).
- **Key rotation and log deletion** now happen after the finale (2026-11-28), not at submission.

**Design rule:** safety comes from code paths, not prompts. Every guarantee ("never sends", "never leaks real data", "only verified identifiers in reports") still holds if every LLM is fully prompt-injected.

**Simplicity rule:**
- One Python service, one SQLite file, one static web page, one Docker image.
- Nothing on the 3-second path depends on Band, AdaL, Finch or DetectifAI.

---

## 1. Context

The hackathon voice track defines two kinds of agent: a "Voice Agent" that handles speech and intent, and "Action Agents" that look things up, verify and escalate. In our system:
- **Voice Agent:** Kamla ji, 68.
- **Action Agents:** Intel, Verifier and Reporter.

How a call runs:
1. A browser "phone" starts a simulated scam call.
2. The **Scammer** is one of:
   - a Lyzr agent (`INPUT_MODE=scripted`, which covers `APP_MODE=live` and `semi`), or
   - a person speaking into the browser microphone (`INPUT_MODE=ptt`).
3. **Kamla ji** (a Lyzr agent with a synthetic voice) answers.
4. The backend owns the floor, renders each turn to speech, and plays it in the dashboard.
5. **Detector** (rules, plus a DetectifAI voice flag), **Intel** and **Verifier** run on every turn.
6. After the call, the Verifier hands off to the **Reporter** through **Band**. The Reporter runs **AdaL** to write the narrative part of two draft reports.
7. **Finch** provides skill discovery (and possibly one Finch-sourced skill; see S9).
8. A human approves the drafts. Nothing is ever transmitted.

The whole service runs on **Agent37**.

```mermaid
flowchart LR
  P["Presenter or judge (browser)"] -- "HTTPS: page, SSE, REST" --> S
  M["Mic (PTT mode): browser Web Speech API"] -. "recognised text only" .-> P
  subgraph A37["Agent37 sandbox: one Docker container"]
    S["Saarthi service: FastAPI + SQLite"]
    R["Reporter Band agent (SDK task)"]
    X["AdaL CLI via allowlist proxy"]
  end
  S -- "v3 chat API" --> LZ["Lyzr: Scammer, Kamla (Intel-LLM only if needed)"]
  S -- "REST posts with mentions" --> BD["Band private room"]
  BD -- "mention: job_id only" --> R
  R -- "GET verified job data" --> S
  R --> X
  S -- "market search" --> FN["Finch marketplace (read-only)"]
  S -- "TTS API" --> TT["TTS provider (catalog voices)"]
  S -- "clip check" --> DF["DetectifAI (not a sponsor)"]
```

**Out of scope** (PDF §6):
- Real phone numbers or PSTN.
- Real scammers.
- Sending reports.
- Languages beyond Hindi-English.
- Voice cloning.
- Live bank integrations.

**Deferred:**
- Replay mode, to the finale (§16).
- F8, the second persona, unless everything is green at 09:00 on day 3.

---

## 2. Components (modules inside one service)

```mermaid
flowchart TB
  subgraph WEB["web/ static page: index.html + app.js"]
    UI1["Phone simulator: scenario, input mode, Call, PTT mic button"]
    UI2["Transcript + English subtitle line + audio player"]
    UI3["Intel panel: chips missing / suspect / heard / confirmed + IFSC lookup"]
    UI4["Agent room panel: Band mirror with send ticks"]
    UI5["Drafts + Approve"]
    UI6["HUD: minutes wasted, substantive reply p95, compute p95, risk, voice flag"]
  end
  subgraph SVC["app/ FastAPI service"]
    API["api.py: REST + SSE at /api/events"]
    ORC["orchestrator.py: turn loop, pacing clock, guards"]
    BUS["bus.py: pub/sub + SQLite event log"]
    SCM["agents/scammer.py: Lyzr live or scripted beats"]
    PTT["api.py PTT endpoint: human_stt turns"]
    DEC["agents/decoy.py: prompt build + C2 filter + read-back renderer"]
    DET["agents/detector.py: rules, sole owner of stage"]
    INT["agents/intel: normalise + regex"]
    VER["agents/verifier.py: deterministic C4 + IFSC lookup"]
    STR["agents/steering.py: update state then pick one directive"]
    REP["agents/reporter.py: job store, template, AdaL runner"]
    RBA["agents/reporter_band.py: Band SDK agent"]
    TTS["integrations/tts.py: hash cache"]
    BAND["integrations/band_mirror.py: REST queue"]
    FIN["integrations/finch_scout.py"]
    DFI["integrations/detectifai.py"]
    EGR["safety/egress.py + safety/adal_proxy.py"]
    AUD["safety/audit.py: JSONL approvals"]
  end
  UI1 --> API
  API <--> ORC
  PTT --> ORC
  ORC --> SCM & DEC & DET & INT & STR & TTS
  INT --> VER --> STR
  ORC --> BUS
  BUS --> API
  BUS --> BAND
  REP --> RBA
  RBA --> REP
  REP --> AUD
  SCM & DEC & TTS & BAND & FIN & DFI & RBA --> EGR
```

Design points:
- **The event bus is authoritative.** Every state change is an event:
  - written to SQLite (an append-only `events` table),
  - pushed over SSE,
  - offered to the Band mirror queue.
- **Band never changes state.** The one Band-routed handoff carries only a `job_id`. The Reporter fetches everything it needs from our API (C4, D6).
- **Egress.** All outbound HTTP goes through `safety/egress.py`, a host allowlist of about 20 lines. The AdaL subprocess is forced through `safety/adal_proxy.py`, a local CONNECT proxy that only allows the model-provider host (ADR-004).
- **Dashboard.** Plain HTML and JS with no build step, served from the same origin. Text is set only through `textContent` (C5).

---

## 3. Agent roster

| Agent | Track role | Platform | Inputs | Outputs | On the 3 s path? |
|---|---|---|---|---|---|
| **Scammer** | (adversary) | **Lyzr** text agent (`live`); scripted beat machine (`semi`); **human via browser STT** (`ptt`) | Scenario outline, planted entity sheet (or a cue card in PTT), last 6 turns | `TranscriptTurn` (speaker=scammer) | Yes |
| **Kamla ji** | **Voice Agent** | **Lyzr** text agent. The directive goes in `system_prompt_variables`, with a fresh `session_id` per turn. Synthetic TTS voice. Read-back lines are rendered by code. | Persona prompt, last 6 turns, scammer line in an untrusted-speech block, directive | `TranscriptTurn` after the C2 filter | **Yes** |
| **Detector** | Action (screening) | Python rules, sync, under 10 ms; the **only owner** of `scam_type`, `stage` and `risk` | Scammer turns | `DetectorResult` | Yes (ms) |
| **Voice check** | Action (screening) | **DetectifAI**, not a sponsor: first scammer TTS clip (scripted mode) or a pre-recorded synthetic clip | Audio clip | `DetectorResult.deepfake` (flag, not a verdict) | No |
| **Intel** | Action (extract) | Python normaliser + regex, sync. A Lyzr extractor is added only if recall is below 90% (conditional). | Each scammer turn | `Entity` candidates | Yes (ms) |
| **Verifier** | Action (verify + lookup) | Deterministic Python (C4). The IFSC is looked up in a fictional bank table in the fixtures. | Candidates, read-back results | `VerifiedEntity`; Band handoff to the Reporter | Yes (ms) |
| **Steering** | Orchestration | Deterministic Python | Goal state, detector result, verified entities | `Directive` | Yes (ms) |
| **Reporter** | Action (escalate, as drafts) | **Band SDK agent** woken by an @mention, plus **AdaL** headless CLI for the narrative. The template fills all identifier fields. | `job_id`, then verified job data from our API | `ReportDraft` x 2 | No (after the call) |
| **Skill Scout** | Support | **Finch** read-only search, at boot and in-call when the scam type is first detected; optionally a Finch-sourced SKILL.md fed to AdaL (S9) | Scam type, skill keywords | Skill registry panel + Band post | No |
| **Agent room** | Coordination | **Band** private room with 6 agent identities and 1 human | Bus events | `BandMessage` | No |
| **Hosting** | - | **Agent37** sandbox, custom Docker image | - | `https://<id>.agent37.app` | Yes for hosted runs |

The Scammer is not a member of the Band room.

---

## 4. One turn: sequence and latency budget

**Metrics** (logged per turn; the DoD gate uses the first two):
- `substantive_reply_start`: from the end of the scammer's audio (scripted modes) or the STT final result (PTT) to the start of Kamla's **actual reply** audio. **Fillers are excluded.**
- `compute_latency`: from the scammer text being final to Kamla's clip being ready on the server. Excludes delivery and playback.
- `filler_rate`: the share of turns where a filler played.
- `delivery_ms`: from clip ready to browser playback start.

**Overlap** (scripted modes only): Kamla's reply is generated while the scammer clip is still playing, which emulates streaming STT. In PTT mode there is no overlap, so `substantive_reply_start` ≈ STT finalisation + `compute_latency` + `delivery_ms`. PTT is reported separately and is not the DoD gate.

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant O as Orchestrator
  participant L as Lyzr
  participant I as Detector, Intel, Verifier, Steering
  participant T as TTS
  participant Q as Band mirror
  alt scripted input
    O->>L: Scammer chat with 6-turn window
    L-->>O: scammer text, max 500 chars
    O->>T: synthesise scammer line, cached by hash
    T-->>O: clip S
    O-->>B: SSE play clip S now
  else PTT input
    B->>O: POST scammer turn text from Web Speech API
  end
  O->>I: update state then select directive, sync
  I-->>O: entities, goal state, directive
  O-)Q: handoff posts, non-blocking
  alt directive is READ_BACK
    O->>O: render read-back line from fixtures template
  else other directives
    O->>L: Kamla chat with window, untrusted scammer block, directive
    L-->>O: Kamla text
    O->>O: C2 output filter
  end
  O->>T: synthesise Kamla line
  T-->>O: clip K
  alt clip K ready within 1.5 s of scammer end
    O-->>B: SSE play clip K after 0.4 s pause
  else late
    O-->>B: SSE play filler at 1.5 s, then clip K
  end
```

| Step | Budget (p95) | Notes |
|---|---|---|
| State update + directive selection (Detector, Intel, Verifier, Steering) | 30 ms | Pure Python |
| Kamla Lyzr chat, reply of 2 sentences or fewer | 1,800 ms | Measured in S1. Read-back turns skip the LLM (~0 ms). |
| C2 filter | 10 ms | |
| TTS for a short line | 700 ms | Measured in S2; cache hits ~0 ms |
| **compute_latency** | **≤ 2.6 s** | |
| delivery (SSE + browser audio start) | 200 ms | Reported separately |
| Natural pause (scripted modes) | 400 ms | On purpose |
| **DoD gate** | **substantive_reply_start p95 ≤ 3.0 s AND compute_latency p95 ≤ 3.0 s**, scripted `live`, n ≥ 45 turns over 3 calls; filler rate reported alongside | |
| PTT target (not a gate) | substantive_reply_start p95 ≤ 3.5 s | |

**Timeouts:**

| Agent | Filler at | Canned in-character line at | Hard timeout | After that |
|---|---|---|---|---|
| Kamla (`KAMLA_TIMEOUT_S`) | 1.5 s | 6 s | 6 s | - |
| Scammer (`SCAMMER_TIMEOUT_S`) | - | - | 8 s | Next scripted beat is used |

---

## 5. Data contracts

`app/contracts.py` (Pydantic) is the source of truth. The schemas below are the reviewed spec, and a unit test compares them against `Model.model_json_schema()`.
- IDs are uuid4.
- Times are ISO-8601 UTC.
- All text is untrusted and length-capped.

### 5.1 TranscriptTurn
```json
{
  "$id": "TranscriptTurn", "type": "object",
  "required": ["call_id", "turn_id", "seq", "speaker", "text", "source", "created_at"],
  "properties": {
    "call_id": {"type": "string"}, "turn_id": {"type": "string"},
    "seq": {"type": "integer", "minimum": 0},
    "speaker": {"enum": ["scammer", "decoy", "system"]},
    "text": {"type": "string", "maxLength": 500},
    "gloss_en": {"type": ["string", "null"], "maxLength": 300},
    "source": {"enum": ["lyzr_live", "scripted", "human_stt", "canned", "readback", "filler"]},
    "stt": {"type": ["object", "null"], "properties": {"lang": {"enum": ["hi-IN", "en-IN"]}, "confidence": {"type": "number"}}},
    "directive_id": {"type": ["string", "null"]},
    "redactions": {"type": "integer", "minimum": 0},
    "audio": {"type": ["object", "null"], "properties": {
      "url": {"type": "string"}, "duration_ms": {"type": "integer"},
      "voice": {"type": "string"}, "cache_hit": {"type": "boolean"}}},
    "timings_ms": {"type": "object", "properties": {
      "llm": {"type": "integer"}, "tts": {"type": "integer"}, "compute_latency": {"type": "integer"},
      "delivery": {"type": "integer"}, "substantive_reply_start": {"type": "integer"}, "filler_played": {"type": "boolean"}}},
    "created_at": {"type": "string", "format": "date-time"}
  }
}
```
`gloss_en` is the English subtitle line.
- For scripted, canned and read-back lines it comes from the fixtures.
- For live lines it is null; the video adds captions in the edit.

### 5.2 DetectorResult
```json
{
  "$id": "DetectorResult", "type": "object",
  "required": ["call_id", "turn_seq", "risk", "scam_type", "stage", "is_scam_likely"],
  "properties": {
    "call_id": {"type": "string"}, "turn_seq": {"type": "integer"},
    "risk": {"type": "number", "minimum": 0, "maximum": 1},
    "scam_type": {"enum": ["digital_arrest", "fake_kyc", "fake_investment", "unknown"]},
    "stage": {"enum": ["hook", "authority", "urgency", "payment_ask", "pressure", "unknown"]},
    "signals": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 10},
    "is_scam_likely": {"type": "boolean"},
    "deepfake": {"type": ["object", "null"], "properties": {
      "provider": {"const": "detectifai"},
      "clip": {"enum": ["first_scammer_clip", "prerecorded_synthetic_clip"]},
      "label": {"enum": ["synthetic", "human", "unknown"]}, "score": {"type": "number"},
      "note": {"const": "flag, not verdict"}}}
  }
}
```
The rules lexicon (in the fixtures) weights keywords per scam type and stage:
- **authority:** CBI, police, RBI, officer, customs.
- **urgency:** abhi, turant, warrant, arrest, 2 ghante.
- **payment_ask:** UPI, account, IFSC, transfer, bhejo, pay.
- **pressure:** a payment ask after a stall.

`risk` is the weighted sum clipped to [0, 1]. `is_scam_likely` means `risk ≥ 0.6`. `stage` never goes backwards within a call.

### 5.3 Entity (candidate)
```json
{
  "$id": "Entity", "type": "object",
  "required": ["entity_id", "call_id", "type", "normalized", "source", "turn_seq"],
  "properties": {
    "entity_id": {"type": "string"}, "call_id": {"type": "string"},
    "type": {"enum": ["upi", "bank_account", "ifsc", "phone"]},
    "raw_span": {"type": "string", "maxLength": 120},
    "normalized": {"type": "string", "maxLength": 64},
    "source": {"enum": ["regex", "llm"]},
    "turn_seq": {"type": "integer"}
  }
}
```

### 5.4 VerifiedEntity
```json
{
  "$id": "VerifiedEntity", "type": "object",
  "required": ["call_id", "type", "value", "status", "confidence", "heard_count", "readback_confirmed"],
  "properties": {
    "call_id": {"type": "string"},
    "type": {"enum": ["upi", "bank_account", "ifsc", "phone"]},
    "value": {"type": "string", "maxLength": 64},
    "status": {"enum": ["verified", "unverified", "invalid"]},
    "confidence": {"enum": ["high", "medium", "low"]},
    "lookup": {"type": ["object", "null"], "properties": {"bank": {"type": "string"}, "branch": {"type": "string"}, "fictional": {"const": true}}},
    "checks": {"type": "object", "properties": {
      "format": {"type": "boolean"}, "planted_match": {"type": "boolean"},
      "handle_allowlisted": {"type": ["boolean", "null"]}, "dedup_of": {"type": ["string", "null"]}}},
    "heard_count": {"type": "integer"}, "readback_confirmed": {"type": "boolean"},
    "reasons": {"type": "array", "items": {"type": "string", "maxLength": 80}},
    "first_turn": {"type": "integer"}, "last_turn": {"type": "integer"}
  }
}
```

### 5.5 GoalState and Directive
```json
{
  "$id": "GoalState", "type": "object",
  "required": ["call_id", "turn_seq", "goal_set", "goals", "turns_without_progress", "minutes_wasted"],
  "properties": {
    "call_id": {"type": "string"}, "turn_seq": {"type": "integer"},
    "goal_set": {"type": "array", "items": {"enum": ["upi", "bank_account", "ifsc", "phone"]}},
    "goals": {"type": "object", "additionalProperties": {"$ref": "#/$defs/goal"}},
    "pending_readback": {"enum": [null, "upi", "bank_account", "ifsc", "phone"]},
    "active_directive": {"$ref": "#/$defs/directive"},
    "wrapup_stalls_left": {"type": "integer"},
    "turns_without_progress": {"type": "integer"},
    "minutes_wasted": {"type": "number"},
    "end_reason": {"enum": [null, "all_resolved", "max_turns", "max_duration", "no_progress", "kill_switch", "error"]}
  },
  "$defs": {
    "goal": {"type": "object", "properties": {
      "status": {"enum": ["missing", "suspect", "heard", "confirmed", "given_up"]},
      "value": {"type": ["string", "null"]}, "ask_attempts": {"type": "integer"},
      "readback_attempts": {"type": "integer"}, "method_failed_used": {"type": "boolean"}}},
    "directive": {"type": "object", "properties": {
      "directive_id": {"type": "string"},
      "kind": {"enum": ["NEUTRAL", "STALL", "ASK", "REPEAT", "READ_BACK", "METHOD_FAILED", "WRAP_UP"]},
      "target": {"enum": [null, "upi", "bank_account", "ifsc", "phone"]},
      "tactic_id": {"type": "string"}, "text": {"type": "string", "maxLength": 240}}}
  }
}
```
`risk`, `scam_type` and `stage` are read from the latest `DetectorResult` and are not copied into GoalState. This gives them a single owner.

`minutes_wasted` is the sum of the durations of all played clips: scammer, Kamla and filler. In PTT mode it is the wall-clock call time.

### 5.6 ReportDraft
```json
{
  "$id": "ReportDraft", "type": "object",
  "required": ["draft_id", "job_id", "call_id", "kind", "watermark", "entities", "body_text", "sha256", "narrative_source", "status"],
  "properties": {
    "draft_id": {"type": "string"}, "job_id": {"type": "string"}, "call_id": {"type": "string"},
    "kind": {"enum": ["bank_alert", "helpline_1930"]},
    "watermark": {"const": "DRAFT - SIMULATED DEMO DATA - NOT SENT TO ANY BANK OR 1930"},
    "scam_type": {"enum": ["digital_arrest", "fake_kyc", "fake_investment", "unknown"]},
    "entities": {"type": "array", "items": {"allOf": [
      {"$ref": "#/$defs/VerifiedEntity"},
      {"properties": {"status": {"const": "verified"}}}]}},
    "unclear_count": {"type": "integer"},
    "narrative": {"type": "string", "maxLength": 1200},
    "narrative_source": {"enum": ["adal", "adal_finch_skill", "template"]},
    "trigger": {"enum": ["band_mention", "direct_fallback"]},
    "body_text": {"type": "string", "maxLength": 6000},
    "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "status": {"enum": ["draft", "approved", "rejected"]},
    "approved_by": {"type": ["string", "null"]}, "approved_at": {"type": ["string", "null"]}
  }
}
```
The `verified` constraint is enforced in two places:
- the `ReportDraft` model validator, which rejects the draft otherwise;
- a unit test that tries to build a draft containing an `unverified` entity and expects failure.

The narrative is post-filtered before use. These are replaced with `[redacted]`:
- digit runs of 6 or more,
- any UPI or IFSC shape that is not in `entities`,
- URLs, markdown links, and the words APPROVED or VERIFIED.

### 5.7 ReportJob (what the Reporter pulls; never in Band)
```json
{
  "$id": "ReportJob", "type": "object",
  "required": ["job_id", "call_id", "verified_entities", "scam_type", "facts"],
  "properties": {
    "job_id": {"type": "string", "pattern": "^rj_[a-f0-9]{12}$"},
    "call_id": {"type": "string"},
    "verified_entities": {"type": "array", "items": {"$ref": "#/$defs/VerifiedEntity"}},
    "scam_type": {"type": "string"},
    "facts": {"type": "object", "description": "built by code from fixtures and metrics: scenario label, stage sequence, duration, counts; no transcript text"},
    "state": {"enum": ["pending", "running", "done", "failed"]}
  }
}
```

### 5.8 BandMessage
```json
{
  "$id": "BandMessage", "type": "object",
  "required": ["msg_id", "event_id", "from_agent", "mentions", "kind", "text", "state"],
  "properties": {
    "msg_id": {"type": "string"}, "event_id": {"type": "string"},
    "from_agent": {"enum": ["saarthi", "detector", "kamla", "intel", "verifier", "reporter"]},
    "mentions": {"type": "array", "minItems": 1, "items": {"enum": ["saarthi", "detector", "kamla", "intel", "verifier", "reporter", "human"]}},
    "kind": {"enum": ["text", "thought", "task", "tool_call", "error"]},
    "text": {"type": "string", "maxLength": 400},
    "state": {"enum": ["queued", "sent", "failed"]},
    "attempts": {"type": "integer"}
  }
}
```
If S3 shows that events cannot be posted over REST, `kind` falls back to `text` with a `[thought]` or `[task]` prefix.

---

## 6. Steering loop (deterministic, unit-tested)

**Goal set:** set per scenario in the fixtures. For example, digital arrest = `upi, bank_account, ifsc`, and fake KYC = `upi, phone`. Priority order: `upi → bank_account → ifsc → phone`.

**Goal status vs VerifiedEntity status**

| Goal status | Meaning | VerifiedEntity (best candidate) | Chip colour |
|---|---|---|---|
| `missing` | Nothing heard yet | - | grey |
| `suspect` | Something heard, but the format fails or the value is not planted | `invalid` or `unverified (not planted)` | amber |
| `heard` | Valid format and planted; not yet confirmed by read-back | `unverified` if heard once; `verified/medium` if heard twice | blue |
| `confirmed` | Read back and the scammer agreed | `verified/high` | green |
| `given_up` | Attempts exhausted; goal closed | Whatever its best candidate is (`verified/medium`, or unclear) | grey, struck through |

### Phase 1: state update (every scammer turn, before selection)

1. **Read-back result.** If `pending_readback = X`, look at the scammer's turn:
   - **Affirmation** (`haan, haa, ji, sahi, correct, yes, bilkul, theek`) and no conflicting candidate for X → X becomes `confirmed`.
   - **Negation** (`nahi, galat, no, wrong`) or a different candidate for X → `readback_attempts += 1`. Use the new value if there is one.
   - **Neither** → `readback_attempts += 1`.
   - Then clear `pending_readback`.
2. **Merge candidates.** Each candidate goes through the Verifier, then:
   - Valid and planted → goal `heard` (unless already `confirmed`), and `heard_count += 1`.
   - Otherwise → goal `suspect` (if it was `missing`).
3. **Close exhausted goals:**
   - `heard` with `readback_attempts ≥ 2` → `given_up`.
   - `missing` or `suspect` with `ask_attempts ≥ 3` and `method_failed_used` → `given_up`.
4. **Progress counter.** `turns_without_progress` is reset by any status change and incremented otherwise.

### Phase 2: select one directive (first match wins)

1. **Guards** → `WRAP_UP`. Any of: kill switch, `turn_seq ≥ 30`, elapsed ≥ 300 s, `turns_without_progress ≥ 8`.
2. **`risk < 0.6`** → `NEUTRAL` ("who is calling and why").
3. **A goal is `heard`** (in priority order) → `READ_BACK target`, and set `pending_readback`. The line is **rendered by code** from a fixtures template ("ruko beta, likh rahi hoon... nau aath saat... sahi hai na?"). There is no LLM call, so the value cannot be mangled. The value is planted, so it passes C2.
4. **A goal is `suspect`** with `ask_attempts < 3` → `REPEAT target` ("speak slowly, I'm writing"), and `ask_attempts += 1`.
5. **`stage` is hook, authority or urgency** → `STALL`, with a tactic that pulls towards payment ("what do I have to do, beta?").
6. **A goal is `missing`** with `ask_attempts < 3` → `ASK target` with the next tactic, and `ask_attempts += 1`.
7. **A goal is `missing`** with `ask_attempts = 3` and `method_failed_used = false` → `METHOD_FAILED` (used once per goal).
8. **All goals are `confirmed` or `given_up`** → 2 more `STALL` turns (minutes wasted), then `WRAP_UP`. `end_reason = all_resolved`.
9. **Otherwise** → `STALL`.

**Directive injection:** the directive goes into the Lyzr `system_prompt_variables` `{{directive}}` slot. If S1 shows that does not work, it goes into a directive block after the untrusted-speech block. Directive text comes only from the tactic table and never contains transcript text.

**Canned fallback:** each directive kind has 2 pre-rendered in-character lines in the fixtures. With these plus code-rendered read-backs, the loop keeps working even if Lyzr is down.

**Loop guards:**
- Repetition detector: if the scammer's last 3 lines have similarity above 0.9, escalate the tactic.
- Only one active call at a time.

**Tests** (`tests/test_steering.py`):
- One test per rule.
- Read-back, then "haan" → confirmed.
- Read-back, then "nahi" → second read-back, then given_up.
- A scenario without `phone` completes.
- METHOD_FAILED fires once.

---

## 7. Extraction (Intel → Verifier)

### 7.1 Normalise each scammer turn

**Text cleanup:**
- Unicode NFC.
- Devanagari digits → ASCII.
- Lowercase a working copy.

**Spoken symbols:**

| Spoken | Becomes |
|---|---|
| `at`, `at the rate` | `@` |
| `dot` | `.` |
| `underscore` | `_` |
| `dash`, `hyphen` | `-` |

These map only inside a candidate window: the 8 tokens around a digit run or a known UPI handle.

**Number words** (Hindi, English and Devanagari), each mapped to one digit:

| Digit | Words |
|---|---|
| 0 | shunya, sifar, zero, oh, शून्य, सिफ़र |
| 1 | ek, one, एक |
| 2 | do, two, दो |
| 3 | teen, three, तीन |
| 4 | char, chaar, four, चार |
| 5 | paanch, panch, five, पांच, पाँच |
| 6 | chhe, chhah, cheh, six, छह, छः |
| 7 | saat, seven, सात |
| 8 | aath, eight, आठ |
| 9 | nau, nine, नौ |

**Tokenisation and joining:**
- `double X` and `triple X` expand into 2 or 3 digit tokens **before** joining, and those tokens count toward the run. So `nau aath double saat` → `9877`.
- A run of **4 or more** digit tokens joins into one string. So `do teen din` stays as words.
- Numeric groups separated by single spaces or hyphens also join (`98765 43210`), because browser STT often emits digits directly.
- No tens or hundreds composition.

### 7.2 Regex candidates

Run on both the raw and the normalised text: phone, IFSC, 9-18 digit account, UPI shape. All matching is done on the lowercased copy; IFSC is uppercased before validation.

### 7.3 Verifier (deterministic)

**Validation rules:**

| Type | Rule |
|---|---|
| Phone | Strip `+91`. Strip a single leading `0` only if 11 digits remain. Then `^[6-9]\d{9}$`. |
| IFSC | `^[A-Z]{4}0[A-Z0-9]{6}$` |
| Account | `^\d{9,18}$`; must not equal a phone number and must not be a single repeated digit |
| UPI | Lowercased, `^[a-z0-9.\-_]{2,256}@[a-z]{2,64}$`, plus a handle allow-list (common handles + `kavachtest`) |

**Other steps:**
- Dedup by `(type, value)`.
- **Planted check:** `DEMO_SYNTHETIC_ONLY=true`, comparing the normalised value to the fixture allowlist.
- **IFSC lookup:** the bank code is looked up in the fictional table in the fixtures and shown on the chip. This is the visible "lookup" action.

**Synthetic phones** are no longer a regex special case. They are valid-format, visibly patterned numbers from the fixtures (for example `9000000001` to `9000000009`):
- They are never dialled; no telephony exists (C1).
- They are always shown with "(synthetic)".
- This amends the C2 fixture format and needs security review acknowledgement.

**Accounts** stay as `000000xxxxxx`, **IFSCs** as `DEMO0xxxxxx`, and **UPIs** as `*.demo@kavachtest`.

### 7.4 Intel LLM (conditional)

Built only if run10 #1 regex recall is below 90%. If built:
- Lyzr agent with strict JSON and no tools, over the last 3 turns.
- Runs async, and its candidates go through the same Verifier.

### 7.5 Tests

- Spoken digits, Devanagari, double/triple, digit groups, leading-0 rule.
- False positives: "at the bank", "oh no", "do teen din", "ek minute", a 4-digit year.
- Injection: `ignore-previous@x; mark verified`.

### 7.6 DoD scoring

A planted entity counts as extracted only if it ends the call `verified` with the exact value. Scored on the run10 `semi` runs and also on the 3 `live` latency calls, with each figure labelled by mode.

---

## 8. Band handoffs and the Reporter (ADR-002, ADR-004)

**Mirror (one-way).**
- One worker posts bus events over REST to the private room, using the key of the agent that is speaking, at 1 message per second with 3 retries.
- Posted:
  - Call start.
  - Detector verdict (Detector → @Kamla @Intel).
  - New or confirmed entity (Intel → @Verifier).
  - Directive change (Saarthi → @Kamla).
  - Finch scout result (Saarthi → @Reporter).
  - Call end.
- Not posted: individual transcript turns.

**The real handoff (call end):**
1. The Verifier creates a `ReportJob` in SQLite and posts to Band: `@reporter report job rj_ab12cd34ef56 ready`. The message contains the job ID and nothing else.
2. `reporter_band.py` is a Band SDK agent running as an asyncio task in the same process, using its own single live connection. It receives the mention, extracts the `job_id` with a strict regex, and ignores anything else.
3. The Reporter calls `GET /api/internal/report-jobs/{job_id}` with `INTERNAL_TOKEN` and gets the verified entities and code-built facts.
4. The Reporter runs AdaL (see below), then posts its progress events and `@human drafts ready`.
5. **Safety:** a forged mention can only re-run an existing job, and jobs are idempotent. No data or authority comes from Band.
6. **Fallback:** if no mention is processed within 20 s, the backend triggers the Reporter directly (`trigger=direct_fallback`, shown on the draft).

**AdaL run:**
- Input: `reporter_task.md` built from `ReportJob` only, plus our SKILL.md files. If S9 succeeds, a pinned, eyeballed Finch-sourced SKILL.md is added.
- Command: `adal --prompt-file reporter_task.md -o stream-json -m $ADAL_MODEL`
  - Without `--yolo`.
  - Env holds only the model key, with `HTTPS_PROXY` pointing at `adal_proxy` (allowlist = model host).
  - 90 s timeout.

**AdaL exit handling:**

| Result | Handling |
|---|---|
| 0 and `success=true` | Use the narrative |
| **2** (approval needed: AdaL tried to use a tool) | Abort, log a policy event, use the template |
| Other non-zero, or `success=false` (includes auth failure; S5 records its exact signature) | Use the template |
| Timeout | Kill the process, use the template |

`stream-json` event types are logged in S5 and mirrored generically as Band `task` events ("AdaL: <type>").

---

## 9. Failure modes and fallbacks

| Dependency | Failure | Fallback | Visible effect |
|---|---|---|---|
| **Lyzr** (Kamla) | Late by more than 1.5 s | Filler, then the reply | Filler counted in `filler_rate` |
| Lyzr (Kamla) | Error, or more than 6 s | Canned line for the directive kind | Turn tagged `canned` |
| Lyzr (Scammer) | Error, more than 8 s, or a refusal | Next scripted beat | Turn tagged `scripted` |
| Lyzr | Out of credits | `APP_MODE=semi` + canned Kamla | Team lead approval needed to top up |
| Lyzr RAI/PII | Masks planted values or refuses role-play | Turn off PII redaction on the Scammer agent (S1). Use "bank staff training simulator" framing. Use `semi` for the hero take. | - |
| TTS | Error or more than 3 s | Cache; then browser `speechSynthesis` hi-IN; then subtitles only | Quality drop |
| Browser STT (PTT) | Wrong or no recognition | Read-back and the Verifier handle unclear values (F4). Typed fallback box with the same endpoint. | Amber chips |
| **Band** mirror | Down or 4xx | 3 retries, then `failed` tick; never blocks | Ticks show failure |
| Band handoff | Mention not delivered | Direct trigger after 20 s | Draft shows `direct_fallback` |
| **AdaL** | See §8 | Template narrative | `narrative_source=template` |
| **Finch** | Down or empty | Dated snapshot | "snapshot from <date>" |
| **Agent37** | Card, inbound SSE or outbound blocked | Run the same image locally; escalate to the tech lead on day 1 | Hosting shot at risk |
| DetectifAI | Any failure | Pre-recorded synthetic clip result (PDF F7). If the API is unreachable: "voice check unavailable". | Not a sponsor |
| Live recording take | Anything | Re-take, or use the best earlier take (replay mode is built only for the finale) | - |

`tools/preflight.py` (about 30 s) checks:
- Key presence.
- Lyzr ping per agent, and the credit balance.
- One TTS line.
- A Band post, and the Reporter agent connected.
- `adal --version` through the proxy.
- Finch search.
- DetectifAI.
- SQLite writable.
- Kill switch off.

---

## 10. Threat-model controls: implementation

| # | How it is implemented | Verification |
|---|---|---|
| **C1** | `egress.py` host allowlist: Lyzr, `app.band.ai`, `www.finchtech.ai`, TTS host, `platform.detectif.ai`. AdaL is forced through `adal_proxy.py`, which only allows the model host, with no `--yolo` (exit 2 = abort). No SMTP, SMS or telephony libraries. Lyzr tool lists are empty and no phone number is provisioned. "Approve" only flips a status. | `rg` grep. Test: AdaL prompt asking to fetch a URL fails (exit 2 or proxy deny). Screenshots. If S5 shows AdaL ignores the proxy, the residual risk is accepted via security review ack (no `--yolo`, synthetic data). |
| **C2** | One fixtures file with fake formats (§7.3; phone format amended). Kamla's filter redacts digit runs of 6 or more, spoken digit runs of 6 or more, and UPI/IFSC/PAN/Aadhaar/PIN/OTP shapes, unless in the allowlist. Allowlist matching is on **normalised digits**. It runs before TTS. Read-backs are code-rendered and only for planted values. | Tests: PIN/account sentence; its spoken version; read-back of planted (spoken) vs non-planted (never reaches read-back; goal `suspect`). Repo grep for 10+ digit numbers not in the fixtures. |
| **C3** | Scammer text in an untrusted-speech block, capped at 500 characters. System prompts contain no secrets. The Intel LLM (if built) has no tools and strict JSON. **AdaL input is `ReportJob` only** (verified fields + code-built facts, no transcript). Narrative post-filter (§5.6). | Rehearsal injection cases 1-3. AdaL input file unit test (no transcript substrings). |
| **C4** | Code-only Verifier. Drafts accept only `status=verified` (model validator). Band carries only `job_id`. Never-from-Band rule. | Cases 2 and 5. Unverified-draft test. Forged-mention test. |
| **C5** | `textContent` only. CSP `default-src 'self'; script-src 'self'; media-src 'self' blob:`. `.txt` exports. | Case 4. `rg innerHTML web/` returns nothing. |
| **C6** | Keys only in env. `gitleaks` before each push. **Repo is private.** Terminals hidden when recording. **Keys rotated after the finale (2026-11-28)**, not at submission. | gitleaks clean. Devtools shows no keys. |
| **C7** | ~~Passcode on start, PTT turn, approve and admin endpoints.~~ Superseded 2026-11-24: open demo; cost guarded by HOSTED_SCRIPTED_ONLY + start rate limit. `INTERNAL_TOKEN` on `/api/internal/*`. Public read-only SSE. Band room private (**verified in S3**). | `curl` returns 401. Band settings screenshot. |
| **C8** | 30 turns, 300 s, one call at a time, start rate limit, kill switch checked every turn. run10 uses `semi`. | Loop test; kill switch test. |
| **C9** | Append-only `approvals.jsonl` with sha256. Watermark on every draft and export. | Hash test. |
| **C10** | Catalog synthetic voices only, pinned. **Deviation:** a third-party TTS catalog voice instead of Lyzr stock voices (ADR-001; security review ack). Fictional names. Persistent banner. Scam prompts only in the private repo. **PTT:** a human voice as *input* only, browser STT, no audio stored or sent to us. **Pending team lead waiver** (threat model §5); otherwise a synthetic clip is played into the mic. | Banner visible in the video. Voice IDs in the README. Waiver recorded. |

**Notes for security review to update the threat model:**
- Retention dates: delete logs by **2026-12-05**, which is finale + 7 days.
- The C2 phone format change.
- The browser STT third party (Google, through Chrome) should be added to D3.

---

## 11. Sponsor-visibility map

| Sponsor | Runtime role | On screen (labelled inside the split screen) | Honesty note |
|---|---|---|---|
| **Lyzr** | Scammer and Kamla agents (plus the Intel LLM if built) | "Kamla ji, Voice Agent, on Lyzr" label; Lyzr Studio cut; **Lyzr voice cameo clip** (S6) | Call audio comes from our TTS. The cameo is Lyzr voice. |
| **Band** | Visible coordination plus **one real handoff** (Verifier → Reporter wake-up) | Band room live beside the dashboard; the `@reporter job rj_...` message followed by the Reporter waking up | The backend decides; Band carries the post-call handoff. |
| **Agent37** | Hosts the container | Console showing the instance, then the URL | - |
| **AdaL** | Reporter narrative (with a Finch skill if S9 passes) | Reporter panel streaming AdaL events; "narrative by AdaL" | Identifiers come from the template. |
| **Finch** | Skill discovery in-call (and possibly a skill source) | Skill registry chip appears when the scam type is detected; "Finch-sourced skill sha256..." if S9 passes | Never claim Finch executes skills. |
| DetectifAI (not a sponsor) | Cloned-voice flag | "Caller voice: synthetic 0.9x, flag not verdict" chip | Labelled as a partner API, not a sponsor |

---

## 12. Run modes

| Flag | Values | Meaning |
|---|---|---|
| `INPUT_MODE` | `scripted` | The Scammer is an agent; `APP_MODE` picks which kind |
| | `ptt` | The Scammer is a person on the browser mic (ADR-007) |
| `APP_MODE` | `live` | The Lyzr Scammer improvises around the scenario |
| | `semi` | Scripted beat machine; entity beats released when Kamla asks |
| `PACING_SPEED` | `1.0` (default) | Real-time audio waits |
| | `0` | No waits; used by run10 extraction checks |

Replay mode is **deferred** to 25-27 Nov, for the finale only (§16).

`fixtures/synthetic.sample.json` holds:
- the persona,
- 3 scenarios (outline, goal set, beats, planted entities with spoken renderings, a correction variant, English glosses),
- the PTT cue cards,
- the tactic table,
- canned lines (2 per kind),
- read-back templates,
- 6 filler texts,
- the Detector lexicon,
- the fictional IFSC bank table,
- the Finch keywords.

---

## 13. Repository layout

```
saarthi/                 # PRIVATE repo
  app/
    main.py  api.py  config.py  contracts.py  bus.py  orchestrator.py
    agents/  lyzr_client.py scammer.py decoy.py detector.py verifier.py steering.py
             reporter.py reporter_band.py  intel/normalise.py intel/regex.py (intel/llm.py only if needed)
    integrations/ tts.py band_mirror.py finch_scout.py detectifai.py
    safety/  egress.py adal_proxy.py redact.py audit.py
  web/       index.html app.js style.css
  prompts/   scammer.md kamla.md (intel.md)
  skills/    draft-bank-alert/SKILL.md  draft-1930-complaint/SKILL.md  finch/ (pinned, if S9)
  fixtures/  synthetic.json  finch_snapshot.json  audio/prerecorded_synthetic_clip.wav
  audio/     fillers/ canned/ cache/(gitignored)
  data/      (gitignored) saarthi.db approvals.jsonl runs/
  tools/     preflight.py run10.py render_audio.py finch_snapshot.py band_setup.py
  tests/
  Dockerfile  .env.example  requirements.txt  README.md
```

---

## 14. Environment variables

| Variable | Default / example | Purpose |
|---|---|---|
| `INPUT_MODE` | `scripted` / `ptt` | ADR-007 |
| `APP_MODE` | `live` / `semi` | ADR-006 |
| `PACING_SPEED` | `1.0` | 0 = no waits |
| `HOSTED_SCRIPTED_ONLY`, `INTERNAL_TOKEN` | setting, secret | C7 |
| `KILL_SWITCH`, `MAX_TURNS`, `MAX_CALL_SECONDS` | `false`, `30`, `300` | C8 |
| `DEMO_SYNTHETIC_ONLY` | `true` | Planted check |
| `FIXTURES_PATH`, `DB_PATH`, `AUDIO_CACHE_DIR` | paths | |
| `LYZR_API_KEY`, `LYZR_USER_ID`, `LYZR_CHAT_URL` | secret, id, `https://agent-prod.studio.lyzr.ai/v3/inference/chat/` | |
| `LYZR_AGENT_SCAMMER`, `LYZR_AGENT_KAMLA`, `LYZR_AGENT_INTEL` (optional) | agent IDs | |
| `KAMLA_TIMEOUT_S`, `SCAMMER_TIMEOUT_S` | `6`, `8` | |
| `TTS_PROVIDER`, `TTS_API_KEY`, `TTS_VOICE_SCAMMER`, `TTS_VOICE_KAMLA` | from S2 | Catalog voices only |
| `BAND_ENABLED`, `BAND_API_URL`, `BAND_ROOM_ID` | `true`, `https://app.band.ai/api/v1/agent`, id | |
| `BAND_KEY_SAARTHI` ... `BAND_KEY_REPORTER` (6), `BAND_AGENT_ID_REPORTER` | secrets | |
| `REPORTER_FALLBACK_S` | `20` | Direct trigger |
| `ADAL_ENABLED`, `ADAL_BIN`, `ADAL_MODEL`, `ADAL_TIMEOUT_S`, `ADAL_PROVIDER_KEY`, `ADAL_ALLOWED_HOST` | `true`, `adal`, from S5, `90`, secret, model host | AdaL BYOK + proxy |
| `FINCH_ENABLED`, `FINCH_SEARCH_URL` | `true`, `https://www.finchtech.ai/api/market/search` | |
| `DETECTIFAI_ENABLED`, `DETECTIFAI_API_KEY` | `true`, secret | |
| `EGRESS_ALLOWLIST` | host list | C1 |

Agent37 env vars are set when the instance is created, and changing them needs a restart.

---

## 15. Traceability matrix (requirement → component → test)

| Req | Component(s) | Test / evidence | Gate |
|---|---|---|---|
| F1 Scam call simulator | `scammer.py`, fixtures (3 scenarios), PTT endpoint | run10 rotates the 3 scenarios; S1 refusal check; PTT smoke test | M2 |
| F2 Decoy persona | `decoy.py`, `steering.py`, `tts.py`, canned and read-back lines | C2 filter tests; injection cases 1 and 3; S2 listen test; steering tests | M2 |
| F3 Live intel extraction | `intel/*`, `detector.py` (scam type, stage) | Normaliser/regex tests incl. false positives; **detector test per scenario: correct `scam_type` and risk ≥ 0.6 by scammer turn 2; stage monotonic**; run10 recall | M3 |
| F4 Verification | `verifier.py` | Validator tests; injection cases 2 and 5; unclear items shown as "not reported" | M3 |
| F5 Report drafting | `reporter.py`, `reporter_band.py`, AdaL, template, `audit.py` | Unverified-draft rejection test; narrative post-filter test; AdaL input test; forged-mention test; hash test | M3 |
| F6 Live dashboard | `web/`, `api.py` | Manual rehearsal checklist (no automated UI test); injection case 4; `minutes_wasted` unit test | M2 |
| F7 Deepfake voice detection | `detectifai.py` | S8; pre-recorded clip fallback | M3 (Should) |
| F8 Multiple personas | fixtures persona 2 | Only if green at 09:00 Tue | Could |
| DoD 1: 10 in a row unaided | `run10.py` | 10 consecutive `semi` runs reach drafts | M3 |
| DoD 2: ≥ 9/10 planted extracted | Verifier + run10 scoring | ≥ 90% exact `verified` across run10; live calls scored and labelled separately | M3 |
| DoD 3: reply in ~3 s | orchestrator metrics | substantive_reply_start p95 ≤ 3 s AND compute_latency p95 ≤ 3 s over 3 live calls (n ≥ 45); filler rate reported | M3 |
| DoD 4: no send, no real data | C1, C2, C9 | Egress grep + AdaL fetch test; fixture grep; hash test | M3 |
| DoD 5: sponsors visible | §11, shot list | Final video review against §11 | Submit |
| Track: "listen" | PTT (ADR-007) | S10 browser STT test; PTT segment in the video | M3 |

---

## 16. Finale readiness (2026-11-28; only if shortlisted on 25 Nov)

| When | Item |
|---|---|
| 25-27 Nov | Build replay mode (re-emit a recorded call's events and audio through the dashboard), about 2.5 h |
| 25-27 Nov | Rehearse the **live PTT demo** ("judge, take the scammer's phone") at least 5 times, including a noisy room and en-IN vs hi-IN |
| 25-27 Nov | Prepare a phone hotspot; run preflight on venue Wi-Fi; have a local Docker fallback on the laptop; keep the recorded video ready |
| 28 Nov | Run order: live scripted call → judge PTT → drafts → approve. Replay is the fallback for the scripted call. |
| After 28 Nov | Rotate all keys (C6). Delete logs and sponsor-platform history by **2026-12-05**, except the submission video. |

## 17. Open questions

1. **Team lead waiver** for a team member's voice as input only (PTT and the Lyzr cameo). If denied: play a synthetic clip into the mic, or use typed PTT.
2. Security review acknowledgement needed for:
   - the C2 phone-format amendment,
   - the C10 TTS deviation,
   - the AdaL proxy residual risk.
3. Unverified until the spikes run:
   - Lyzr directive substitution and RAI settings (S1).
   - Band privacy, REST event shape, and SDK mention delivery (S3).
   - Agent37 outbound access (S4).
   - AdaL BYOK on Agent37, proxy compliance, and the `stream-json` schema (S5).
   - Finch free skill delivery (S9).
