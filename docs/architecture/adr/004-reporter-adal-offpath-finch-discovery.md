# ADR-004: Reporter is a template plus an AdaL narrative, run off-path under an egress proxy; Finch handles discovery and may source one skill

Status: Accepted by tech lead in v2 (2026-11-21) · Revised v2: sanitised AdaL input, egress proxy, corrected exit codes, Finch-skill test, Finch call moved into the call

## Context
- **AdaL** is a headless CLI that is also an agent harness with its own tools. It needs credits or BYOK.
- **Finch** has no execute endpoint, and purchases need a wallet.
- The verification review raised three issues:
  - AdaL could reach the network unconstrained (C1).
  - The transcript text sent to AdaL (C3/S-4).
  - Exit code 2 was mislabelled as an auth failure. It actually means "approval needed".

## Options
- **AdaL:** (a) run it per turn; (b) **post-call narrative only**; (c) not at all.
- **Finch:** (a) buy or execute; (b) publish on-chain; (c) **read-only discovery, plus a 45-min test of loading a free Finch skill into AdaL**; (d) not at all.

## Decision
**AdaL, option (b).**

Input:
- The input file is built **only** from `ReportJob`: verified entities plus facts built by code (scenario label, stage sequence, duration, counts).
- **No transcript text ever goes in.**

Run:
- `adal --prompt-file ... -o stream-json -m $ADAL_MODEL`
- Never with `--yolo`.
- The environment holds only the model key.
- `HTTPS_PROXY` points at `safety/adal_proxy.py`, a local CONNECT proxy that allows only `ADAL_ALLOWED_HOST`.
- 90 s timeout.

Exit handling:

| Result | Meaning | Action |
|---|---|---|
| `0` and `success=true` | Success | Use the narrative |
| `2` | AdaL wanted to use a tool and needed approval | Abort, log a policy event, use the template |
| Any other non-zero, or `success=false` | Error; auth failures land here (S5 records the exact signature) | Use the template |
| Timeout | - | Kill the process, use the template |

After a successful run, the narrative is post-filtered: unknown numbers, URLs, links, and the words APPROVED and VERIFIED are stripped.

`stream-json` event types are logged in S5 and mirrored generically to Band.

**Test:** a prompt asking AdaL to fetch a URL must fail.

Residual risk: if S5 shows AdaL ignores the proxy, we accept the risk (no `--yolo`, synthetic data only), with security review acknowledgement.

**Finch, option (c).**
- **S9 (45 min):** look for a free, non-wallet skill delivery that is relevant to complaint drafting. If one exists:
  - read it by eye,
  - pin its sha256 under `skills/finch/`,
  - load it into the AdaL Reporter, which sets `narrative_source=adal_finch_skill`.

  Downloaded skill content is untrusted (T15). It goes through the same narrative post-filter.
- **Either way:** when the Detector first flags a scam type, the Skill Scout queries the Finch catalogue during the call and posts the result to Band. If Finch is down, a dated snapshot is used.
- We never claim Finch executes skills. No purchase.

## Consequences
+ AdaL can't leak transcript content or contact third parties through our code paths.
+ Finch becomes visible at runtime, and may honestly supply a skill.
- The proxy is one more small component (about 40 lines). Whether AdaL honours the proxy is unverified until S5.
- Finch's role stays modest if S9 fails.
