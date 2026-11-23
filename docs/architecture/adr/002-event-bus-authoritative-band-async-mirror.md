# ADR-002: The backend event bus is authoritative. Band is an async mirror plus one real, data-free handoff

Status: Accepted by tech lead in v2 (2026-11-21) · Revised v2: one real Band-routed handoff (Verifier to Reporter)

## Context
The PDF promises that every handoff is visible in a shared Band room. Band has constraints:
- Every message must @mention someone.
- Each agent ID gets one live connection.
- Rate limits are undocumented.

Threat model C4/D6: Band messages must never carry authority or data that the system acts on.

The red team pointed out that a pure mirror leaves "is this really agent-to-agent?" unanswered.

## Options
1. Band as the transport for every step. That puts a third party on the 3-second path.
2. A synchronous mirror. A Band outage would stall the call.
3. An async mirror only (v1).
4. **An async mirror, plus one real handoff after the call, carrying only a job ID.**

## Decision
**Option 4.**

**Mirror** (unchanged from v1):
- Posts go over REST, at 1 message per second, with 3 retries. A post never blocks the call.
- Posted: call start, Detector verdict, new/confirmed entities, directive changes, Finch result, call end.

**Real handoff**, at call end:
1. The Verifier creates a `ReportJob` in SQLite and posts `@reporter report job rj_<12 hex> ready`.
2. The Reporter is a **Band SDK agent**. It runs as an asyncio task in our process, using its own single connection. It wakes on the mention, extracts the job ID with a strict regex, and ignores everything else.
3. It fetches the job from `GET /api/internal/report-jobs/{id}` (`INTERNAL_TOKEN`) and runs AdaL (ADR-004).
4. It posts its progress and `@human drafts ready`.

**Safety:**
- No identifiers or instructions travel through Band.
- A forged mention can only re-run an existing job, and jobs are idempotent.

**Fallback:** if the mention has not been processed after 20 s, the backend triggers the Reporter directly. The draft shows `trigger=direct_fallback`.

**Spike-verified (S3):**
- the room privacy setting,
- the REST mention payload,
- whether `thought`/`task` events can be posted over REST (fallback: text with a prefix),
- SDK mention delivery inside our event loop (fallback: a separate process).

## Consequences
+ Band does real coordination work, off the critical path, and C4 still holds.
+ A clear story for Band and AdaL.
- Adds a Band SDK dependency (Python 3.11+, SDK churn) and one more failure mode. It is covered by the direct fallback, and it is item 5 in the cut order.
- 6 agent keys + `INTERNAL_TOKEN` to manage (C6).
