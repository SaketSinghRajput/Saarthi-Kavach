# Demo video: how it is built

an internal document (not shipped) rebuilds an internal document (not shipped) (1920x1080, 30 fps, H.264 + AAC, about 3:42) from local inputs. Nothing is uploaded and no paid API is called.

Run: an internal document (not shipped) (Kokoro and ffmpeg run one after the other; intermediates go to an internal document (not shipped), which is gitignored).

Inputs: the live call screen recording (an internal document (not shipped)), the run log `data/runs/c_b1accbdacb29.json`, the call's cached TTS clips in `audio/cache/`, and the persona reel an internal document (not shipped).

Sections: cold open (real call audio, labels only), title card, the live call with lower-third labels (dull stretches sped up 3x/4x with call audio muted and a "Sped up" tag), citizen page from the persona reel, four "problems we faced" cards, close (context card, then simulated-only and sponsor card).

Call audio is real: each clip from the run log is placed at its `t_start` plus a 6.5 s offset (when the dashboard showed LIVE and "scammer speaking" in the recording), RMS-normalised, then mixed. The run log holds no transcript text, so the video makes no quotes; labels only.

Voice-over (title, citizen, problem and close cards only, never over call audio) is Kokoro `af_heart`. Figures on cards come from `README.md`: dead air p95 1.2 s vs 1.5 s budget, held-out n=36 (scam type 19/22, alert precision 93%, recall 64%), Agent37 not deployed, impact figures are simulated proxies and no loss-prevented claim.
