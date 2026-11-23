# ADR-001: Orchestrator-owned half-duplex text relay with per-turn TTS

Status: Accepted by tech lead in v2 (2026-11-21); team lead approval pending · Revised v2: STT returns through the PTT mode (ADR-007), and the C10 deviation is recorded

## Context
Scammer and Kamla ji must talk in Hinglish with real-sounding audio. Replies must start within about 3 s, Intel needs clean text every turn, and 10 runs must pass in a row.

Lyzr voice agents exist, but three things are undocumented: live in-call transcripts, Hindi support, and two agents sharing one audio session. Community reports show live agent-to-agent audio deadlocking and echoing.

## Options
1. Lyzr voice agent talking to Lyzr voice agent in one LiveKit room. High risk.
2. A Lyzr voice Decoy over WebSocket, with the scammer audio streamed in. Medium risk: the message schema and Hindi support are unknown.
3. **Text relay through our backend.** Both agents run on the Lyzr v3 chat API, our TTS speaks each turn, and the backend owns the floor. The next reply is generated while the current clip is still playing.
4. Option 3, plus server-side STT run on our own scammer TTS audio.

## Decision
- **Option 3** is the primary agent-vs-agent path.
- **Option 2** is reduced to a 20-second Lyzr voice cameo, spiked on day 1 (S6).
- **Option 4 is not built.** Real speech input comes instead from the push-to-talk mode (ADR-007), where a human speaks as the scammer. That gives the system a real "listen" capability at lower cost and risk than server STT.

**C10 deviation, recorded here.** The threat model says to use "only Lyzr's stock or catalog synthetic voices". Because we don't use Lyzr voice for the call audio, we use a **third-party TTS provider's catalog synthetic voices** instead (chosen in S2: Sarvam, ElevenLabs or similar).
- Still no cloning and no uploaded samples.
- Voice IDs are pinned in env and listed in the README.
- Needs security review acknowledgement.

## Consequences
+ Deterministic floor control, a full transcript, directive injection, and repeatable runs.
+ Worst-case compute latency is about 2.6 s.
- Call audio is our TTS, not Lyzr voice. The video labels it, and the Lyzr cameo shows real Lyzr voice.
- In scripted modes the overlap hides compute time. So the DoD gate uses `substantive_reply_start` (fillers excluded) **and** `compute_latency`, both at p95 ≤ 3 s.
