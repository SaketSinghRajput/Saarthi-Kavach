# Demo URL on a Hugging Face Docker Space

## Founder path (3 steps, one command)

1. Sign up at https://huggingface.co (free, no card).
2. Settings > Access Tokens > create a token with **Write** permission.
3. Put `HF_TOKEN=hf_...` in `.env` (never commit it; optional `HF_SPACE=<user>/<name>`, default `<user>/saarthi-kavach`), then run:
   `py -3.12 deploy/hf_space_push.py`

`py -3.12 deploy/hf_space_push.py --dry-run` first prints the plan with secrets hidden and sends nothing. The script rebuilds the public mirror, stages only what the image needs (`Dockerfile`, `app/`, `web/`, `fixtures/`, runtime requirements), adds the Space front matter (`sdk: docker`, `app_port: 7860`), creates a public Space, sets variables `PORT=7860`, `HOSTED_SCRIPTED_ONLY=true`, `FINCH_ENABLED=true` and secret `APP_PASSCODE` (from `.env`, else generated and printed ONCE: save it), and uploads. It handles the missing `audio/` by staging an empty `audio/cache/`, so the image builds; the Space plays no call audio, and `/` redirects to `/start.html`. No sponsor keys are sent unless you add `--with-lyzr` (spends Lyzr credits; ask first). `huggingface_hub` is installed on demand into a scratch venv by `uv`; `requirements.txt` is untouched. The first real run has not happened yet (no token), so the manual steps below are the fallback.

No Hugging Face account either? Use the laptop-only fallback `powershell -ExecutionPolicy Bypass -File deploy	unnel.ps1` (Cloudflare quick tunnel to the running local app on :8000; downloads `cloudflared` to `toolsin` once, prints a random `https://....trycloudflare.com` URL). The link dies when the laptop sleeps or the window closes; use it for backup or testing, not as the submission URL.

---

## Manual path (what the script automates)

Fallback for the public demo URL because Agent37 could not be funded (`docs/PROBLEMS.md` #13). Nothing here has been run on Hugging Face yet: it needs Saket's HF account. Facts about HF come from https://huggingface.co/docs/hub/spaces-sdks-docker (checked 2026-11-23 in an internal document (not shipped)); free hardware size and sleep policy are NOT verified.

The hosted demo runs the **scripted scammer and cached audio only**. No paid key is needed.

## What the repo's Dockerfile does (read from `Dockerfile`)

- `ENV PORT=8000`, `CMD ... --port ${PORT:-8000}`. It does not hardcode the port, so **no Dockerfile edit is needed**. Set a Space variable `PORT=7860` (step 4) and it listens on 7860, matching `app_port: 7860`.
- It runs as non-root uid 10001 and writes its SQLite DB to `/opt/saarthi/data`. HF's docs suggest uid 1000; we have not tested whether HF runs the image's own `USER`. If the Space logs show a permission error on `/opt/saarthi/data`, the fix is to change `10001` to `1000` in the `useradd`/`chown` lines of the Dockerfile (a CTO decision; not done here).
- It does `COPY audio/cache/ audio/cache/` and `COPY fixtures/ fixtures/`.

## Two traps in the public mirror

The mirror (`D:\hacthon\saarthi-public`, built by an internal document (not shipped)) excludes `audio/` and `fixtures/synthetic.sample.json`.

1. **`audio/` is missing, so `docker build` fails at `COPY audio/cache/`.** Before pushing to the Space, in the Space repo run: `mkdir audio\cache` and add an empty file `audio\cache\.keep`. The build then passes and the Space plays **no call audio**.
2. **To get audio**, copy the 112 `.wav` files from the private repo's `audio/cache/` into the Space repo's `audio/cache/` instead. They are synthetic TTS clips, but the mirror withholds them on purpose, so Saket decides. Anyone who can open a public Space can fetch them, so the choice is: no audio (safe default), or audio on a **private** Space (judges then need access). Also, the app needs the cache check in `_synth_kokoro` to serve them without Kokoro (`docs/PROBLEMS.md` #7).

`fixtures/synthetic.sample.json` is not needed: `app/config.py` falls back to `fixtures/synthetic.sample.json`.

## Steps (Saket)

1. **Create the Space.** huggingface.co, New Space. Name e.g. `saarthi-kavach`. SDK: **Docker** (Blank template). Visibility: public unless you copy audio (see above). Hardware: the free CPU option.
2. **Clone the Space repo** and copy the mirror into it:
   ```
   git clone https://huggingface.co/spaces/<user>/saarthi-kavach hf-space-repo
   ```
   Copy the contents of `D:\hacthon\saarthi-public` into `hf-space-repo` (leave out `.git`). Re-run tests and gitleaks on the mirror first, as in an internal document (not shipped). Never copy `.env`.
3. **Add the Space front matter** to the very top of the Space repo's `README.md` (Spaces read config from README.md only; do this in the Space repo, not in the GitHub repo):
   ```
   ---
   title: Saarthi Kavach
   sdk: docker
   app_port: 7860
   pinned: false
   ---
   ```
   Then handle the audio trap above. Commit and `git push` to the Space (this is the HF push, not the GitHub push; it needs your HF login or token).
4. **Settings > Variables and secrets.**
   - Secret `APP_PASSCODE`: 12+ characters. Required: without it the app leaves read endpoints open.
   - Variable `PORT` = `7860`.
   - Nothing else for the default demo. Do **not** set `INPUT_MODE=ptt`, Lyzr keys or Band keys unless you want live behaviour.
5. **Wait for the build** (Logs tab). Then verify:
   - `GET https://<user>-saarthi-kavach.hf.space/api/health` returns 200.
   - `GET .../api/state` returns 401 without the passcode and 200 with header `X-Passcode: <APP_PASSCODE>`.
   - Open `/dashboard.html` and run one scripted call.
6. **Put the URL and passcode** into the README top table and the submission form (before 2026-11-24 19:00 IST).
7. **After judging:** pause or delete the Space.

## Optional: live Kamla (costs money)

Set secrets `LYZR_API_KEY`, `LYZR_USER_ID` and the `LYZR_AGENT_*` ids (names in README "Live mode"). Each call then spends Lyzr credits; the spend cap is $20 with about $10 used (an internal document (not shipped)), so get approval first. Keep the scammer scripted on a public URL: a public endpoint driving a live LLM scammer is an abuse and cost risk. The rate limit and turn caps still apply (`START_RATE_PER_MIN`, `MAX_TURNS`, `MAX_CALL_SECONDS`).

## Known limits on a Space

- Disk is lost on restart (SQLite DB resets). Fine for a demo.
- Free hardware may sleep when idle and may be slow to wake. Open the URL shortly before judging.
- No AdaL CLI in the image: drafts use the template narrative. No Kokoro: no new audio.
- Backup during live judging: `cloudflared tunnel --url http://localhost:8000` from a running local app (testing only, no SSE, random hostname; see the research doc).
