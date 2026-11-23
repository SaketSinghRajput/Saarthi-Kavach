# ADR-005: One FastAPI service, SQLite, and a static HTML/JS dashboard over SSE, in one Docker image on Agent37

Status: Accepted by tech lead in v2 (2026-11-21) · Revised v2: SSE path is `/api/events`; Agent37 outbound access must pass spike S4; the Reporter Band agent runs as an in-process task

## Context
- The team is 2 people with about 2.5 days.
- Agent37 runs any amd64 image and exposes public ports with WebSocket/SSE passthrough and a 15-minute idle timeout.
- Agent37 has no managed database.
- Agent37 claims outbound traffic is firewalled to the public internet. This is unverified for our hosts.

## Options
1. Microservices plus Redis plus a React app.
2. **One FastAPI process, agents as modules, SQLite, and a static dashboard on the same origin.**
3. Option 2 with a React/Vite frontend.

## Decision
**Option 2.**
- Server to browser uses SSE on `/api/events`, with a 15 s heartbeat and `X-Accel-Buffering: no`.
- Browser to server uses REST for: start call, PTT turn, approve.
- The Band SDK Reporter runs as an asyncio task in the same process. If S3 shows this doesn't work, it becomes a second process in the same container.
- AdaL and its proxy run inside the same container.

Spike S4 must confirm, from **inside** the container:
- inbound SSE works, and
- outbound HTTPS reaches Lyzr, Band, Finch, the TTS provider, DetectifAI and the AdaL model host.

If outbound is blocked: run locally and escalate to the tech lead on day 1.

## Consequences
+ One thing to build, deploy, debug and record.
+ Local and hosted runs are identical.
- A plain JS UI is less polished than React; one person owns it.
- One active call at a time (also a C8 control).
