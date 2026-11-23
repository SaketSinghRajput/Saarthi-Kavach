"""Orchestrator: the turn loop, pacing clock and guards. Every step is an event on the bus."""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from .agents.decoy import Decoy
from .agents.detector import Detector
from .agents.intel.regex import extract
from .agents.lyzr_client import LyzrClient
from .agents.reporter import Reporter, UPI_PSP, build_facts, resolve_adal_bin, upi_psp  # noqa: F401
from .agents.reporter_band import ReporterBand
from .agents.scammer import SemiScammer
from .agents.steering import Steering, new_state
from .agents.verifier import Verifier
from .bus import EventBus
from .contracts import Entity, extract_job_id
from .fixtures import tag_phones
from .integrations.band_mirror import BandMirror
from .integrations.detectifai import DetectifAI
from .integrations import finch_scout
from .integrations.finch_scout import FinchScout
from .integrations.tts import TTS
from . import runlog

PAUSE_MS = 400
FILLER_AFTER_S = 1.2  # silence after the scammer clip ends before a cached filler line plays


class Busy(Exception):
    pass


def p95(xs: list) -> int:
    if not xs:
        return 0
    s = sorted(xs)
    return int(s[min(len(s) - 1, int((0.95 * len(s) + 0.9999)) - 1)])


def _eid(t: str, v: str) -> str:
    return "e_" + hashlib.sha1(f"{t}|{v}".encode()).hexdigest()[:10]


class Orchestrator:
    def __init__(self, settings, fx: dict, bus: EventBus):
        self.s, self.fx, self.bus = settings, fx, bus
        self.lyzr = LyzrClient(settings, fx)
        self.decoy = Decoy(fx, self.lyzr)
        self.tts = TTS(settings)
        self.band = BandMirror(settings)
        self.finch = FinchScout(settings, fx)
        self.dfai = DetectifAI(settings)
        self.reporter = Reporter(bus, settings, band_cb=self._band)
        self.reporter_band = ReporterBand(settings, self.reporter)
        self.task: Optional[asyncio.Task] = None
        self.call_id: Optional[str] = None
        self.kill_flag = False
        self.ptt_q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._bandq: Optional[asyncio.Queue] = None
        self._bandw: Optional[asyncio.Task] = None
        self.result: dict = {}
        self._mode = "scripted"
        self._sim_ms = 0
        self._scout_live: Optional[bool] = None
        self.session_impact = {"label": "simulated call", "calls_n": 0, "engaged_s": 0.0, "identifiers_verified": 0,
                               "identifiers_corrected": 0, "drafts": 0, "fillers": 0, "turns": 0}
        self.band_last_post: Optional[bool] = None  # None: no live Band post yet this process; else did the last one land

    def agent_status(self) -> dict:
        s = self.s
        m = lambda on: "live" if on else "stub"  # noqa: E731
        lyzr = self.lyzr.live
        adal = bool(s.adal_enabled and (s.adal_provider_key or resolve_adal_bin(s.adal_bin)))
        band = bool(s.band_enabled and s.band_room_id and any(s.band_keys.values()))
        finch = bool(s.finch_enabled) if self._scout_live is None else self._scout_live
        host = bool(s.agent37_url or s.agent37_instance)
        return {"agents": {
            "kamla": {"platform": "Lyzr", "mode": m(lyzr)},
            "scammer": {"platform": "Lyzr", "mode": "scripted" if s.hosted_scripted_only
                        else m(lyzr and s.app_mode == "live")},
            "reporter": {"platform": "AdaL", "mode": m(adal)},
            "scout": {"platform": "Finch", "mode": m(finch)},
            "room": {"platform": "Band", "mode": m(band)},
            "host": {"platform": "Agent37" if host else "local", "mode": m(host)}}}

    def _emit_agent_status(self) -> None:
        self.bus.publish("agent_status", self.call_id, self.agent_status())

    # ------------------------------------------------------------------ api
    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self, scenario: str, input_mode: str) -> str:
        if self.active:
            raise Busy("a call is already running")
        if scenario not in self.fx["scenarios"]:
            raise ValueError("unknown scenario")
        self.call_id = "c_" + uuid.uuid4().hex[:12]
        self.kill_flag = False
        self.ptt_q = asyncio.Queue(maxsize=8)
        self.result = {}
        self.task = asyncio.get_running_loop().create_task(self._run(self.call_id, scenario, input_mode))
        return self.call_id

    def kill(self) -> None:
        self.kill_flag = True

    async def wait(self) -> dict:
        if self.task:
            await self.task
        return self.result

    def submit_ptt(self, text: str) -> bool:
        if not self.active or self._mode != "ptt":
            return False
        try:
            self.ptt_q.put_nowait(text[:500])
            return True
        except asyncio.QueueFull:
            return False

    # --------------------------------------------------------------- helpers
    async def _band(self, from_agent: str, to_agent: Optional[str], text: str, kind: str) -> None:
        """Mirror to Band and emit the `band` event (mirrored=false when Band is not live). Text is code-built."""
        text = tag_phones(text)[:400]
        t_ms = int(self._sim_ms)
        if self._bandq is not None and self.band.live_for(from_agent):
            await self._bandq.put((from_agent, to_agent, text, kind, t_ms))
            return
        self.bus.publish("band", self.call_id, {"from_agent": from_agent, "to_agent": to_agent, "text": text,
                                                "kind": kind, "mirrored": False, "t_ms": t_ms,
                                                "band_msg_id": None})

    async def _band_worker(self) -> None:
        while True:
            f, t, text, kind, t_ms = await self._bandq.get()
            try:
                ok, mid = await self.band.post_ex(f, t, text, kind)
            except Exception:
                ok, mid = False, None
            self.band_last_post = bool(ok)
            self.bus.publish("band", self.call_id, {"from_agent": f, "to_agent": t, "text": text, "kind": kind,
                                                    "mirrored": bool(ok), "t_ms": t_ms,
                                                    "band_msg_id": mid if ok else None})
            self._bandq.task_done()

    def _status(self, state: str, scenario: str, **extra) -> None:
        self.bus.publish("call_status", self.call_id, {"call_id": self.call_id, "state": state,
                                                       "scenario": scenario, "input_mode": self._mode, **extra})

    def _pace(self, ms: float):
        return asyncio.sleep(ms / 1000 / self.s.pacing_speed) if self.s.pacing_speed > 0 else asyncio.sleep(0)

    # ------------------------------------------------------------------ run
    async def _run(self, call_id: str, scenario_key: str, input_mode: str) -> None:
        self._mode = input_mode
        sc = self.fx["scenarios"][scenario_key]
        verifier = Verifier(self.fx, self.s.demo_synthetic_only)
        steering = Steering(self.fx, verifier, self.s.max_turns, self.s.max_call_seconds)
        st = new_state(sc["goal_set"])
        det = Detector(self.fx, call_id)
        scammer = SemiScammer(self.fx, scenario_key)
        window: list = []
        emitted: dict = {}
        stages: list = []
        sim_ms = 0.0
        t_wall0 = time.monotonic()
        started_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        seq = 0
        durations_ms = 0.0
        compute_ms_list: list = []
        subst_ms_list: list = []
        llm_ms_list: list = []
        tts_ms_list: list = []
        dead_ms_list: list = []
        rows: list = []  # run log: timings only, never text
        fillers = kamla_turns = c2_total = 0
        filler_i = 0
        last_dir = None
        last_dir_key = None
        deepfake = {"flag": False, "source": "not_checked"}
        scout_done = False
        scout_task = None
        last_stage = None
        end_reason = None
        self._bandq = asyncio.Queue()
        self._bandw = asyncio.get_running_loop().create_task(self._band_worker())
        self._sim_ms, self._scout_live = 0, None
        try:
            self._status("ringing", scenario_key)
            self._emit_agent_status()
            await self._pace(600)
            self._status("active", scenario_key)
            await self._band("saarthi", "kamla", f"Call started: {sc['label']}", "post")
            await self._band("saarthi", "intel", f"Goal set: {', '.join(sc['goal_set'])}", "post")

            while True:
                # ---- scammer turn --------------------------------------------------
                if input_mode == "ptt":
                    try:
                        text = await asyncio.wait_for(self.ptt_q.get(), self.s.ptt_idle_s)
                    except asyncio.TimeoutError:
                        end_reason = "ptt_idle"
                        break
                    line = {"text": text, "gloss_en": None, "source": "human_stt"}
                else:
                    line = None
                    if self.s.app_mode == "live" and self.lyzr.live and not self.s.hosted_scripted_only:
                        outline = f"{sc['label']}. Planted details: " + "; ".join(
                            f"{t} {e['value']}" for t, e in sc["entities"].items())
                        txt = await self.lyzr.scammer(window, outline)
                        if txt:
                            line = {"text": txt, "gloss_en": None, "source": "lyzr_live"}
                    if line is None:
                        line = scammer.next(last_dir)
                stext = line["text"][:500]
                seq += 1
                sclip = await self.tts.synth(stext, "scammer")
                st_ms = sim_ms
                self._sim_ms = st_ms
                sim_ms += sclip.duration_ms
                durations_ms += sclip.duration_ms
                self.bus.publish("turn", call_id, {
                    "seq": seq, "speaker": "scammer", "text": stext, "gloss_en": line["gloss_en"],
                    "audio_url": sclip.url, "t_start": int(st_ms), "latency_ms": 0, "source": line["source"]})
                window.append({"speaker": "scammer", "text": stext})
                rows.append({"seq": seq, "speaker": "scammer", "source": line["source"], "t_start": int(st_ms),
                             "audio_url": sclip.url, "audio_ms": int(sclip.duration_ms)})

                # ---- detector / intel / verifier / steering (sync, ms) ---------------------
                res = det.update(stext, seq)
                if seq == 1 and self.s.detectifai_enabled:
                    deepfake = await self.dfai.check(None if sclip.url is None else
                                                     str(self.tts.cache / sclip.url.rsplit("/", 1)[-1]))
                self.bus.publish("detector", call_id, {
                    "scam_type": res.scam_type, "stage": res.stage, "risk": res.risk, "signals": res.signals,
                    "is_scam_likely": res.is_scam_likely, "turn_seq": seq, "deepfake": deepfake})
                if res.stage != last_stage and res.stage != "unknown":
                    stages.append(res.stage)
                    await self._band("detector", "kamla", f"Stage: {res.stage}, risk {res.risk:.2f}, "
                                     f"type {res.scam_type}", "post")
                    last_stage = res.stage
                if res.scam_type != "unknown" and not scout_done:
                    scout_done = True
                    # background: a live Finch GET can take seconds while TTS saturates the CPU; never stall the call
                    scout_task = asyncio.get_running_loop().create_task(self._scout(call_id, res.scam_type))

                cands = []
                for t, v, raw in extract(stext):
                    ve = verifier.check(Entity(entity_id=_eid(t, v), call_id=call_id, type=t, raw_span=raw,
                                               normalized=v, turn_seq=seq))
                    cands.append(ve)
                prev_status = {t: g.status for t, g in st.goals.items()}
                steering.update(st, stext, cands)
                self._emit_entities(call_id, st, cands, verifier, emitted)
                for t, g in st.goals.items():
                    if g.status != prev_status[t] and g.status in ("heard", "confirmed", "given_up") and g.value:
                        await self._band("intel", "verifier", f"{t} {g.status}: {g.value}", "post")
                elapsed = (time.monotonic() - t_wall0) if input_mode == "ptt" else (sim_ms / 1000)
                directive = steering.select(st, res.risk, res.stage, elapsed, self.kill_flag or self.s.kill_switch)
                last_dir = directive
                key = (directive.kind, directive.target)
                if key != last_dir_key:
                    last_dir_key = key
                    await self._band("saarthi", "kamla", f"Directive: {directive.kind}"
                                     + (f" {directive.target}" if directive.target else ""), "post")
                self._emit_goal_state(call_id, st, directive, durations_ms, input_mode, t_wall0)

                # ---- Kamla: compute overlaps with the scammer clip -------------------------
                g = st.goals.get(directive.target) if directive.target else None
                t_c0 = time.perf_counter()

                async def _kamla():
                    r, nred = await self.decoy.reply(call_id, kamla_turns, window, stext, directive,
                                                     g.value if g else None, g.readback_attempts if g else 0)
                    t_l = time.perf_counter()
                    clip = await self.tts.synth(r.text, "kamla")
                    t_e = time.perf_counter()
                    return r, nred, clip, (t_e - t_c0) * 1000, (t_l - t_c0) * 1000, (t_e - t_l) * 1000

                ktask = asyncio.get_running_loop().create_task(_kamla())
                if input_mode != "ptt":
                    await self._pace(sclip.duration_ms)  # scammer clip plays while Kamla computes
                filler_played, filler_ms = False, 0.0
                if self.s.pacing_speed > 0:
                    done, _ = await asyncio.wait({ktask}, timeout=FILLER_AFTER_S / self.s.pacing_speed)
                    if not done:
                        f = self.fx["fillers"][filler_i % len(self.fx["fillers"])]
                        filler_i += 1
                        t_f = time.perf_counter()
                        fclip = await self.tts.synth(f["text"], "kamla")  # cached (prerendered at startup): ~0 ms
                        filler_ms = (time.perf_counter() - t_f) * 1000
                        seq += 1
                        self.bus.publish("turn", call_id, {
                            "seq": seq, "speaker": "filler", "text": f["text"], "gloss_en": f["gloss_en"],
                            "audio_url": fclip.url, "t_start": int(sim_ms), "latency_ms": 0, "source": "filler"})
                        sim_ms += fclip.duration_ms
                        durations_ms += fclip.duration_ms
                        filler_played = True
                        rows.append({"seq": seq, "speaker": "filler", "source": "filler", "t_start": int(sim_ms - fclip.duration_ms),
                                     "filler_ms": filler_ms, "audio_url": fclip.url, "audio_ms": int(fclip.duration_ms)})
                        fillers += 1
                try:
                    r, nred, kclip, compute_ms, llm_ms, tts_ms = await asyncio.wait_for(ktask, self.s.kamla_timeout_s)
                except Exception:
                    r = self.decoy.fallback(directive, kamla_turns)
                    llm_ms = (time.perf_counter() - t_c0) * 1000
                    t_l = time.perf_counter()
                    kclip = await self.tts.synth(r.text, "kamla")
                    tts_ms = (time.perf_counter() - t_l) * 1000
                    nred, compute_ms = 0, llm_ms + tts_ms
                if nred:
                    c2_total += nred
                    self.bus.publish("policy", call_id, {"kind": "c2_filter", "detail": f"{nred} redaction(s)"})
                if self.s.pacing_speed > 0:
                    await self._pace(PAUSE_MS)
                    sim_ms += PAUSE_MS
                self._sim_ms = sim_ms
                # user-perceived gap = real Kamla compute (LLM + TTS) + the human pause. Compute is NOT hidden
                # behind the scammer clip: a live caller's reply cannot start before the caller finished speaking.
                subst_ms = compute_ms + (PAUSE_MS if self.s.pacing_speed > 0 else 0)
                # dead air = silence between the scammer clip ending and the first Kamla audio (filler or real).
                # The clip only overlaps compute when it really plays (scripted, real pacing); a live (PTT) caller
                # has finished speaking when compute starts, and with pacing off there is no overlap credit.
                sp = self.s.pacing_speed
                overlap_ms = sclip.duration_ms / sp if (input_mode != "ptt" and sp > 0) else 0.0
                if filler_played:
                    dead_ms = (FILLER_AFTER_S * 1000 / sp if sp > 0 else 0.0) + filler_ms
                else:
                    dead_ms = max(0.0, compute_ms - overlap_ms) + (PAUSE_MS / sp if sp > 0 else 0)
                seq += 1
                kamla_turns += 1
                llm_ms_list.append(llm_ms)
                tts_ms_list.append(tts_ms)
                dead_ms_list.append(dead_ms)
                compute_ms_list.append(compute_ms)
                subst_ms_list.append(subst_ms)
                rows.append({"seq": seq, "speaker": "kamla", "source": r.source, "t_start": int(sim_ms),
                             "llm_ms": llm_ms, "tts_ms": tts_ms, "filler_ms": filler_ms if filler_played else 0.0,
                             "dead_ms": dead_ms, "latency_ms": int(compute_ms),
                             "audio_url": kclip.url, "audio_ms": int(kclip.duration_ms)})
                self.bus.publish("turn", call_id, {
                    "seq": seq, "speaker": "kamla", "text": r.text, "gloss_en": r.gloss_en,
                    "audio_url": kclip.url, "t_start": int(sim_ms), "latency_ms": int(compute_ms),
                    "source": r.source, "directive": directive.kind, "filler_played": filler_played,
                    "llm_ms": int(llm_ms), "tts_ms": int(tts_ms)})
                window.append({"speaker": "kamla", "text": r.text})
                sim_ms += kclip.duration_ms
                self._sim_ms = sim_ms
                durations_ms += kclip.duration_ms
                minutes = self._minutes(durations_ms, input_mode, t_wall0)
                self.bus.publish("metrics", call_id, {
                    "minutes_wasted": round(minutes, 2), "substantive_p95_ms": p95(subst_ms_list),
                    "compute_p95_ms": p95(compute_ms_list), "llm_p95_ms": p95(llm_ms_list),
                    "tts_p95_ms": p95(tts_ms_list), "dead_air_p95_ms": p95(dead_ms_list),
                    "answer_p95_ms": p95([a + b for a, b in zip(llm_ms_list, tts_ms_list)]),
                    "filler_rate": round(fillers / max(1, kamla_turns), 3), "turns": kamla_turns})
                self._emit_goal_state(call_id, st, directive, durations_ms, input_mode, t_wall0)
                await self._pace(kclip.duration_ms)
                if directive.kind == "WRAP_UP":
                    end_reason = st.end_reason or "wrap_up"
                    break
                if self.kill_flag or self.s.kill_switch:
                    end_reason = "kill_switch"
                    break
                await asyncio.sleep(0)
            if scout_task is not None:
                await asyncio.wait({scout_task}, timeout=finch_scout.BUDGET_S + 1)
            # ---- end of call -----------------------------------------------------------
            minutes = self._minutes(durations_ms, input_mode, t_wall0)
            self._status("ended", scenario_key, end_reason=end_reason or st.end_reason)
            await self._band("saarthi", None, f"Call ended: {end_reason or st.end_reason}", "post")
            job_id = await self._handoff(call_id, sc, scenario_key, verifier, st, stages, seq, minutes)
            summ = self._call_summary(call_id, durations_ms / 1000 if input_mode != "ptt" else minutes * 60, verifier,
                                      emitted, len(self.reporter.drafts_for(job_id)), fillers, seq)
            self.result = {"call_id": call_id, "scenario": scenario_key, "end_reason": end_reason or st.end_reason,
                           "goals": st.snapshot(), "turns": seq, "minutes_wasted": round(minutes, 2),
                           "verified": {f"{e.type}": e.value for e in verifier.store.values()
                                        if e.status == "verified" and e.readback_confirmed},
                           "compute_p95_ms": p95(compute_ms_list), "substantive_p95_ms": p95(subst_ms_list),
                           "llm_p95_ms": p95(llm_ms_list), "tts_p95_ms": p95(tts_ms_list),
                           "dead_air_p95_ms": p95(dead_ms_list), "filler_rate": round(fillers / max(1, kamla_turns), 3), "c2_redactions": c2_total,
                           "answer_p95_ms": p95([a + b for a, b in zip(llm_ms_list, tts_ms_list)])}
            self._write_runlog(call_id, scenario_key, rows, summ, job_id, started_iso)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never crash the server; surface as an ended call
            self._status("ended", scenario_key, end_reason="error", error=type(exc).__name__)
            self.result = {"call_id": call_id, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                if self._bandq is not None:
                    await asyncio.wait_for(self._bandq.join(), 10)
            except Exception:
                pass
            if scout_task is not None and not scout_task.done():
                scout_task.cancel()
            if self._bandw:
                self._bandw.cancel()
            self._bandq = None

    # -------------------------------------------------------------- pieces
    async def _scout(self, call_id: str, scam_type: str) -> None:
        sc_res = await self.finch.scout(scam_type)
        names = ", ".join(s_["name"] for s_ in sc_res["skills"])
        self.bus.publish("skill", call_id, {"scam_type": scam_type, "skills": sc_res["skills"],
                                            "live": sc_res["live"], "query": sc_res["query"],
                                            "total": sc_res.get("total", len(sc_res["skills"])),
                                            "role": "discovery_only"})
        self._scout_live = bool(sc_res["live"])
        self._emit_agent_status()
        await self._band("saarthi", "reporter", f"Skill scout ({'live' if sc_res['live'] else 'snapshot'}): {names}", "post")

    def _call_summary(self, call_id, engaged_s, verifier, emitted, drafts, fillers, turns) -> None:
        """Simulated impact proxies for one call (never a losses-prevented claim); also tallied for the session."""
        summ = {"label": "simulated call", "engaged_s": round(engaged_s, 1),
                "identifiers_verified": sum(1 for e in verifier.store.values()
                                            if e.status == "verified" and e.readback_confirmed),
                "identifiers_corrected": sum(1 for v in emitted.values() if v == "superseded"),
                "drafts": drafts, "fillers": fillers, "turns": turns}
        t = self.session_impact
        t["calls_n"] += 1
        for k in ("engaged_s", "identifiers_verified", "identifiers_corrected", "drafts", "fillers", "turns"):
            t[k] = round(t[k] + summ[k], 1) if k == "engaged_s" else t[k] + summ[k]
        self.bus.publish("call_summary", call_id, {**summ, "session": dict(t)})
        return summ

    def _write_runlog(self, call_id, scenario, rows, summ, job_id, started_iso=None) -> None:
        try:
            keys = ("minutes_wasted", "turns", "substantive_p95_ms", "compute_p95_ms", "llm_p95_ms", "tts_p95_ms",
                    "dead_air_p95_ms", "answer_p95_ms", "filler_rate", "c2_redactions")
            metrics = {k: self.result[k] for k in keys if k in self.result}
            c = self.reporter.case_context(call_id)["case_id"]
            drafts = [{"kind": d.kind, "trigger": d.trigger, "band_msg_id": d.band_msg_id, "case_id": c,
                       "sha256": d.sha256} for d in self.reporter.drafts_for(job_id)]
            runlog.write_run(self.s.data_dir, runlog.build_run(
                call_id, scenario, self.agent_status()["agents"], rows, metrics, summ, drafts, started_iso))
        except Exception:
            pass  # the run log must never break a call

    def _minutes(self, durations_ms: float, mode: str, t0: float) -> float:
        return (time.monotonic() - t0) / 60 if mode == "ptt" else durations_ms / 60000

    def _emit_entities(self, call_id, st, cands, verifier, emitted) -> None:
        def emit(t: str, v: str, status: str) -> None:
            if emitted.get((t, v)) == status:
                return
            emitted[(t, v)] = status
            ve = verifier.get(t, v)
            payload = {"id": _eid(t, v), "type": t, "value": v, "display": tag_phones(v), "status": status}
            if t == "ifsc" and ve and ve.lookup:
                payload["ifsc_bank"] = ve.lookup["bank"]
                payload["resolved_by"] = "action_agent:ifsc_lookup"
            elif t == "upi":
                payload["upi_psp"] = upi_psp(v)
                payload["resolved_by"] = "action_agent:upi_psp_lookup"
            self.bus.publish("entity", call_id, payload)

        for c in cands:  # anything that is not a goal's current value is only a suspect
            g = st.goals.get(c.type)
            if g is None or g.value != c.value:
                if emitted.get((c.type, c.value)) is None:
                    emit(c.type, c.value, "suspect")
        for t, g in st.goals.items():
            for (et, ev_), s_ in list(emitted.items()):
                if et == t and g.value and ev_ != g.value and s_ in ("heard", "suspect", "superseded"):
                    # replaced by a correction: suspect until the new value is confirmed, then superseded
                    emit(et, ev_, "superseded" if g.status == "confirmed" else "suspect")
            if g.value and g.status in ("suspect", "heard", "confirmed", "given_up"):
                emit(t, g.value, g.status)

    def _emit_goal_state(self, call_id, st, directive, durations_ms, mode, t0) -> None:
        goals = {t: {**v, "display": tag_phones(v["value"]) if v["value"] else None} for t, v in st.snapshot().items()}
        self.bus.publish("goal_state", call_id, {
            "goals": goals, "minutes_wasted": round(self._minutes(durations_ms, mode, t0), 2),
            "pending_readback": st.pending_readback, "turn_seq": st.turn_seq,
            "turns_without_progress": st.turns_without_progress, "end_reason": st.end_reason,
            "directive": {"kind": directive.kind, "target": directive.target, "tactic_id": directive.tactic_id}})

    async def _handoff(self, call_id, sc, scenario_key, verifier, st, stages, turns, minutes) -> str:
        verified = [e for e in verifier.store.values() if e.status == "verified"
                    and any(g.value == e.value and g.status in ("confirmed", "given_up") for g in st.goals.values())]
        facts = build_facts(sc["label"], sc["scam_type"], stages, minutes * 60, turns, st.snapshot(), minutes)
        job = self.reporter.create_job(call_id, verified, sc["scam_type"], facts)
        text = f"@reporter report job {job.job_id} ready"
        assert extract_job_id(text) == job.job_id  # G7: the handoff is only ever this sentence
        mirrored, mid = False, None
        try:
            mirrored, mid = await asyncio.wait_for(self.band.post_ex("verifier", "reporter", text, "handoff"), 8)
        except Exception:
            pass
        if self.band.live_for("verifier"):
            self.band_last_post = bool(mirrored)
        self.bus.publish("band", call_id, {"from_agent": "verifier", "to_agent": "reporter", "text": text,
                                           "kind": "handoff", "mirrored": bool(mirrored),
                                           "t_ms": int(self._sim_ms), "band_msg_id": mid if mirrored else None})
        if mirrored and self.reporter_band.listening:
            if await self.reporter_band.listen(job.job_id, self.s.reporter_fallback_s):
                return job.job_id  # the Band mention woke the Reporter (trigger=band_mention + Band message id)
        await self.reporter_band.on_mention(text, "direct_fallback")
        return job.job_id
