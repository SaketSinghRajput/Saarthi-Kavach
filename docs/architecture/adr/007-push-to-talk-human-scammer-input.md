# ADR-007: "Take the scammer's phone" push-to-talk input through the browser Web Speech API

Status: Accepted by tech lead (2026-11-21) · **Pending team lead waiver** for a human voice as input

## Context
The voice track is defined as agents that "talk, **listen** and take action through natural voice conversations". In v1 nothing listened: both sides were LLM text read out by TTS (red team, failure #1, score 9).

The live finale on 2026-11-28 will invite "let me be the scammer".

Threat model §5 says no team members' voices anywhere, including test runs.

## Options
1. **Browser Web Speech API** (`webkitSpeechRecognition`, `hi-IN`/`en-IN`, interim results). The final text is POSTed as a scammer turn into the same orchestrator.
2. Server-side STT (Sarvam, Deepgram or Whisper) on uploaded audio. Adds a vendor, latency, audio handling, and an approval.
3. A full Lyzr voice Decoy over WebSocket. Unknown schema, 4-8 h of work.
4. No listening.

## Decision
**Option 1**, behind `INPUT_MODE=ptt`. In this mode:
- Chrome's built-in STT turns the speech into text.
- The mic button is disabled while Kamla speaks, so the conversation stays half-duplex.
- Interim text is shown live.
- The final text goes to `POST /api/calls/{id}/scammer-turn` (passcode) as `source=human_stt`.
- Kamla, Detector, Intel, Verifier, Steering and Reporter are unchanged. Kamla's voice stays synthetic.
- The speaker reads planted values from a **cue card** generated from the fixtures, so the planted check and C2 still hold. Anything else ends up `unverified` (shown as "unclear").
- A typed fallback box posts to the same endpoint.

The normaliser adds Devanagari number words, `sifar`, "at the rate", and joining of space-separated digit groups (browser STT often emits digits).

**If the team lead denies the waiver:** play a synthetic TTS scammer clip into the mic (speaker or virtual audio cable). The STT path still gets real audio.

**Privacy:**
- We never receive or store audio. Only text reaches our server.
- Chrome sends the audio to Google's speech service. Security review should add this third party to D3.
- In PTT mode no audio goes to DetectifAI. The chip shows "not run (live mic)".

## Consequences
+ Real listening in the loop, isolated from the DoD path.
+ Gives us the finale demo and a 30-second video segment.
- Chrome-only. Hinglish recognition is variable; S10 targets ≥ 7/10 exact on identifiers, and read-back plus the Verifier catch errors (F4).
- There is no overlap in PTT mode, so the substantive reply is about compute latency + STT finalisation. The target is p95 ≤ 3.5 s, reported separately and not a DoD gate.
- Costs about 2.5 h (B: UI; A: endpoint and normaliser additions).
