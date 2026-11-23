"""Reporter: job store, template-filled drafts (template owns every identifier), AdaL narrative behind ADAL_ENABLED.

AdaL input is the ReportJob only (verified fields + code-built facts): no transcript text (C3).
Drafts are never sent anywhere. 'Approve' only flips a status and appends to the audit log (C1, C9).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from ..bus import EventBus
from ..contracts import WATERMARK, ReportDraft, ReportJob, VerifiedEntity, extract_job_id
from ..fixtures import tag_phones
from ..safety import audit
from ..safety.redact import filter_narrative

TYPE_LABEL = {"upi": "UPI ID", "bank_account": "Account number", "ifsc": "IFSC", "phone": "Phone"}
SCAM_LABEL = {"digital_arrest": "digital arrest (fake officer)", "fake_kyc": "fake KYC update",
              "fake_investment": "fake investment", "unknown": "unclassified"}
BandCb = Callable[[str, Optional[str], str, str], Awaitable[None]]


def build_facts(scenario_label: str, scam_type: str, stages: list, duration_s: float, turns: int,
                goals: dict, minutes_wasted: float) -> dict:
    """Facts built by code from fixtures and metrics. Never transcript text."""
    return {"scenario_label": scenario_label, "scam_type": scam_type, "stage_sequence": stages,
            "duration_s": round(duration_s, 1), "turn_count": turns, "minutes_wasted": round(minutes_wasted, 2),
            "goals_total": len(goals), "goals_confirmed": sum(1 for g in goals.values() if g["status"] == "confirmed"),
            "goals_given_up": sum(1 for g in goals.values() if g["status"] == "given_up")}


def build_adal_task(job: ReportJob, skills_text: str = "") -> str:
    """The complete AdaL input. Built from the job only; a unit test asserts no transcript text can appear."""
    ents = "\n".join(f"- {TYPE_LABEL[e.type]}: {e.value} (confidence {e.confidence})" for e in job.verified_entities)
    return (
        "# Task\nWrite a neutral 4-6 sentence incident narrative (max 900 characters, plain text) for a fraud "
        "report DRAFT. Do not use tools, do not fetch URLs, do not write any numbers or identifiers: the "
        "template adds them. Do not say a report was sent or approved.\n\n"
        f"# Job {job.job_id}\nScam type: {job.scam_type}\nFacts: {json.dumps(job.facts, sort_keys=True)}\n"
        f"Verified identifiers (for context only, do not repeat them):\n{ents or '- none'}\n"
        + (f"\n# Skills\n{skills_text}\n" if skills_text else ""))


def template_narrative(job: ReportJob) -> str:
    f = job.facts
    stages = " > ".join(f.get("stage_sequence", [])) or "n/a"
    n = len(job.verified_entities)
    return (f"A simulated {SCAM_LABEL.get(job.scam_type, job.scam_type)} call was handled by an automated decoy "
            f"for about {f.get('minutes_wasted', 0)} minutes over {f.get('turn_count', 0)} turns. The scam moved through "
            f"these stages: {stages}. {n} payment identifier(s) were verified by read-back and are listed in this draft. "
            f"{f.get('goals_given_up', 0)} goal(s) could not be resolved and are excluded. This is a simulated demo.")


def skills_line(names: list) -> list:
    # Finch names are third-party text: keep a safe character set and cap length before they enter a draft.
    names = [n for n in (re.sub(r"[^A-Za-z0-9 ._-]", "", str(x))[:60].strip() for x in names[:3]) if n]
    return ["Related skills discovered via Finch catalogue (discovery only, not executed): " + ", ".join(names),
            ""] if names else []


UPI_PSP = {"okaxis": "Axis (PSP)", "ybl": "PhonePe/Yes (PSP)", "paytm": "Paytm (PSP)", "oksbi": "SBI (PSP)",
           "ibl": "ICICI (PSP)"}  # offline label map only, no network
IST = timezone(timedelta(hours=5, minutes=30))
REQUEST_LINE = "Request: please review under your own procedures and, if warranted, flag or hold the beneficiary account and UPI handle pending investigation."
COMPLAINANT_FIELDS = ("Complainant name / account", "UTR / transaction reference", "Amount (INR)",
                      "Debit date and time")


def upi_psp(handle: str) -> Optional[str]:
    return UPI_PSP.get(handle.rsplit("@", 1)[-1].lower()) if "@" in handle else None


def case_id_for(call_id: str, started: datetime) -> str:
    """Human-readable case id shared by both drafts of a call: SK-<IST date>-<6 hex of sha256(call_id)>."""
    return f"SK-{started.astimezone(IST):%Y%m%d}-{hashlib.sha256(call_id.encode()).hexdigest()[:6]}"


def trim_sentences(text: str, limit: int) -> str:
    """Cap length at a sentence boundary (never mid-sentence); a single over-long sentence ends with '...'."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = max(text.rfind(c, 0, limit) for c in ".!?")
    return text[:cut + 1] if cut > 0 else text[:limit - 3].rstrip() + "..."


def _vals(job: ReportJob, t: str, fmt=lambda e: e.value) -> str:
    out = [fmt(e) for e in job.verified_entities if e.type == t]
    return "; ".join(out) if out else "not captured"


def _ifsc_fmt(e: VerifiedEntity) -> str:
    return f"{e.value} ({e.lookup['bank']}, {e.lookup['branch']})" if e.lookup else e.value


def _upi_fmt(e: VerifiedEntity) -> str:
    psp = upi_psp(e.value)
    return f"{e.value} ({psp})" if psp else e.value


def _intel_block(job: ReportJob, ctx: dict, unclear: int) -> list:
    f = job.facts
    return ["INTEL (extracted by code, verified by read-back; synthetic demo data)",
            f"  Beneficiary account : {_vals(job, 'bank_account')}",
            f"  IFSC                : {_vals(job, 'ifsc', _ifsc_fmt)}",
            "                        (format checked only; verify in the RBI IFSC directory)",
            f"  UPI handle          : {_vals(job, 'upi', _upi_fmt)}",
            f"  Scammer phone(s)    : {_vals(job, 'phone')}",
            f"  Scam type           : {SCAM_LABEL.get(job.scam_type, job.scam_type)}",
            f"  Stages observed     : {' > '.join(f.get('stage_sequence', [])) or 'n/a'}",
            f"  Call start (IST)    : {ctx['started'].astimezone(IST).isoformat(timespec='seconds')}",
            f"  Call ID             : {job.call_id}",
            f"  Job ID              : {job.job_id}",
            f"  Evidence            : transcript sha256 {ctx['transcript_sha256']}",
            f"  Unclear identifiers not included: {unclear}"]


def _complainant_block() -> list:
    return ["TO BE FILLED BY COMPLAINANT BEFORE SUBMISSION"] + [f"  {x}: ______________________"
                                                                  for x in COMPLAINANT_FIELDS]


def _draft(title: str, job: ReportJob, ctx: dict, narrative: str, unclear: int, skills: list) -> str:
    lines = [WATERMARK, "", title, "",
             f"Case ID: {ctx['case_id']}   (one case: the bank and 1930 drafts carry the same ID, file it once)", "",
             *_intel_block(job, ctx, unclear), "", "SUMMARY", narrative, "", *_complainant_block(), "",
             REQUEST_LINE, ""] + skills_line(skills) + [WATERMARK]
    return tag_phones("\n".join(lines))


def _bank_alert(job: ReportJob, ctx: dict, narrative: str, unclear: int, skills: list = ()) -> str:
    return _draft("SUSPECTED FRAUD ALERT (DRAFT) - for the fraud desk of the receiving bank",
                  job, ctx, narrative, unclear, skills)


def _helpline(job: ReportJob, ctx: dict, narrative: str, unclear: int, skills: list = ()) -> str:
    return _draft("CYBER FRAUD COMPLAINT (DRAFT) - for the national helpline 1930 / cybercrime portal",
                  job, ctx, narrative, unclear, skills)


ADAL_ENV_ALLOW = ("PATH", "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "TEMP", "TMP", "COMSPEC")
ADAL_DISABLED_TOOLS = "Bash,Edit,Web,Image,Video,Consult"
_TEXT_KEYS = ("answer", "result", "text", "output", "content")


def resolve_adal_bin(name: str) -> Optional[str]:
    """ADAL_BIN may be a full path (the Windows installer does not put adal on PATH) or a PATH name."""
    if name and os.path.isfile(name):
        return name
    return shutil.which(name) if name else None


def adal_env(provider_key: str, proxy_url: str = "") -> dict:
    """Minimal env: the allow-list lets the CLI find its own login; none of our .env secrets pass through."""
    env = {k: os.environ[k] for k in ADAL_ENV_ALLOW if os.environ.get(k)}
    env["ADAL_PROVIDER_KEY"] = provider_key
    if proxy_url:
        env["HTTPS_PROXY"] = env["https_proxy"] = proxy_url
        env["NO_PROXY"] = env["no_proxy"] = "localhost,127.0.0.1"  # local Ollama must not go through the proxy
    return env


def parse_adal_output(raw: str) -> tuple:
    """(text, error) from `-o json` (one object) or `-o stream-json` (event lines). Last good text wins."""
    text, err = None, None
    try:  # `-o json` pretty-prints one multi-line object
        objs = [json.loads(raw)]
    except ValueError:
        objs = []
        for line in raw.splitlines():
            try:
                objs.append(json.loads(line))
            except ValueError:
                continue
    for o in objs:
        if not isinstance(o, dict):
            continue
        if o.get("type") == "error" and o.get("message"):
            err = str(o["message"])
        if o.get("success") is False or o.get("error"):
            err = str(o.get("error") or err or "failed")
        if o.get("success") is False or o.get("type") == "error":
            continue
        t = next((o[k] for k in _TEXT_KEYS if isinstance(o.get(k), str) and o[k].strip()), None)
        if t and (o.get("success") is True or o.get("type") in (None, "answer", "result", "final", "assistant", "text", "message")):
            text = t
    return text, err


async def _default_adal_runner(cmd: list, env: dict, cwd: str, timeout: float) -> tuple:
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=cwd, env=env, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -9, b""
    return proc.returncode, out


class Reporter:
    def __init__(self, bus: EventBus, settings, band_cb: Optional[BandCb] = None, adal_runner=None):
        self.bus, self.s = bus, settings
        self.band_cb = band_cb
        self.adal_runner = adal_runner or _default_adal_runner

    # ---- jobs -----------------------------------------------------------
    def create_job(self, call_id: str, verified: list, scam_type: str, facts: dict) -> ReportJob:
        verified = [e for e in verified if e.status == "verified"]  # C4: only verified entities enter a job
        job = ReportJob(job_id="rj_" + uuid.uuid4().hex[:12], call_id=call_id, verified_entities=verified,
                        scam_type=scam_type, facts=facts)
        with self.bus.lock:
            self.bus.db.execute("INSERT INTO report_jobs VALUES (?,?,?,?)",
                                (job.job_id, call_id, job.model_dump_json(), "pending"))
            self.bus.db.commit()
        return job

    def get_job(self, job_id: str) -> Optional[ReportJob]:
        if not isinstance(job_id, str) or not re.match(r"^rj_[a-f0-9]{12}$", job_id):
            return None
        with self.bus.lock:
            row = self.bus.db.execute("SELECT body, state FROM report_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        job = ReportJob.model_validate_json(row[0])
        job.state = row[1]
        return job

    def _set_state(self, job_id: str, state: str) -> None:
        with self.bus.lock:
            self.bus.db.execute("UPDATE report_jobs SET state=? WHERE job_id=?", (state, job_id))
            self.bus.db.commit()

    def drafts_for(self, job_id: str) -> list:
        with self.bus.lock:
            rows = self.bus.db.execute("SELECT body FROM drafts WHERE job_id=? ORDER BY rowid", (job_id,)).fetchall()
        return [ReportDraft.model_validate_json(r[0]) for r in rows]

    def get_draft(self, draft_id: str) -> Optional[ReportDraft]:
        with self.bus.lock:
            row = self.bus.db.execute("SELECT body FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
        return ReportDraft.model_validate_json(row[0]) if row else None

    def _skill_names(self, call_id: str) -> list:
        """Names from the call's `skill` event (code-built by the scout, never transcript text)."""
        with self.bus.lock:
            row = self.bus.db.execute("SELECT payload FROM events WHERE call_id=? AND type='skill' ORDER BY id LIMIT 1",
                                      (call_id,)).fetchone()
        try:
            return [str(s["name"])[:60] for s in json.loads(row[0])["skills"]] if row else []
        except Exception:
            return []

    def case_context(self, call_id: str) -> dict:
        """Code-built evidence context: call start, shared case id, sha256 over the stored transcript turns.
        The transcript itself never enters a draft (only its hash)."""
        with self.bus.lock:
            first = self.bus.db.execute("SELECT ts FROM events WHERE call_id=? ORDER BY id LIMIT 1",
                                        (call_id,)).fetchone()
            turns = self.bus.db.execute("SELECT payload FROM events WHERE call_id=? AND type='turn' ORDER BY id",
                                        (call_id,)).fetchall()
        try:
            started = datetime.fromisoformat(first[0].replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
        except Exception:
            started = datetime.now(timezone.utc)
        lines = []
        for (p,) in turns:
            try:
                t = json.loads(p)
                lines.append(f"{t.get('speaker')}: {t.get('text')}")
            except Exception:
                continue
        return {"started": started, "case_id": case_id_for(call_id, started),
                "transcript_sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()}

    def _save(self, d: ReportDraft) -> None:
        with self.bus.lock:
            self.bus.db.execute("INSERT OR REPLACE INTO drafts VALUES (?,?,?,?)",
                                (d.draft_id, d.job_id, d.model_dump_json(), d.status))
            self.bus.db.commit()

    def _emit(self, d: ReportDraft) -> None:
        self.bus.publish("draft", d.call_id, {
            "draft_id": d.draft_id, "kind": d.kind, "body": d.body_text,
            "status": "approved" if d.status == "approved" else "pending", "job_id": d.job_id,
            "sha256": d.sha256, "narrative_source": d.narrative_source, "trigger": d.trigger, "band_msg_id": d.band_msg_id,
            "watermark": d.watermark, "case_id": self.case_context(d.call_id)["case_id"]})

    # ---- narrative ------------------------------------------------------
    async def _adal_narrative(self, job: ReportJob) -> Optional[str]:
        """AdaL headless run. Returns None on any problem so the caller uses the template (exit 2 = abort)."""
        if self.s.adal_enabled and not self.s.adal_allowed_host:
            self.bus.publish("policy", job.call_id, {"kind": "adal_refused", "detail": "ADAL_ALLOWED_HOST empty"})
            return None
        binpath = resolve_adal_bin(self.s.adal_bin)
        if not (self.s.adal_enabled and (self.adal_runner is not _default_adal_runner or binpath)):
            return None
        tmp = tempfile.mkdtemp(prefix="adal_")  # empty cwd (G3)
        try:
            task = os.path.join(tmp, "reporter_task.md")
            with open(task, "w", encoding="utf-8") as f:
                f.write(build_adal_task(job))
            cmd = [binpath or self.s.adal_bin, "--prompt-file", task, "-o", "stream-json",
                   "--disabled-default-tools", ADAL_DISABLED_TOOLS] + (["-m", self.s.adal_model] if self.s.adal_model else [])
            proxy = None  # no --yolo; stripped env
            if self.s.adal_allowed_host:  # G3: AdaL may reach only its own hosts
                from ..safety.adal_proxy import AdalProxy
                proxy = AdalProxy(self.s.adal_allowed_host)
                await proxy.start()
            env = adal_env(self.s.adal_provider_key, proxy.url if proxy else "")
            try:
                code, out = await self.adal_runner(cmd, env, tmp, self.s.adal_timeout_s)
            finally:
                if proxy:
                    await proxy.stop()
            if code == 2:
                self.bus.publish("policy", job.call_id, {"kind": "adal_tool_attempt_aborted", "detail": "exit 2"})
                return None
            text, err = parse_adal_output(out.decode("utf-8", "replace"))
            if code != 0 or err or not text:
                if err or code != 0:  # out of credits, model not found, ...: fall back to the template
                    self.bus.publish("policy", job.call_id, {"kind": "adal_unavailable",
                                                             "detail": (err or f"exit {code}")[:200]})
                return None
            return text
        except Exception:
            return None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- run (idempotent) -------------------------------------------------
    async def run_job(self, job_id: str, trigger: str, band_msg_id: Optional[str] = None) -> list:
        job = self.get_job(job_id)
        if job is None:
            return []
        existing = self.drafts_for(job_id)
        if existing:  # a forged or repeated mention can only re-show existing drafts
            return existing
        self._set_state(job_id, "running")
        if self.band_cb:
            await self.band_cb("reporter", None, f"Reporter: picked up {job_id}", "post")
        allowed = {e.value for e in job.verified_entities}
        narrative = await self._adal_narrative(job)
        source = "adal" if narrative else "template"
        narrative = trim_sentences(filter_narrative(narrative, allowed), 1200) if narrative else template_narrative(job)
        unclear = max(0, job.facts.get("goals_total", 0) - len(job.verified_entities))
        skills = self._skill_names(job.call_id)
        ctx = self.case_context(job.call_id)
        drafts = []
        for kind, fn in (("bank_alert", _bank_alert), ("helpline_1930", _helpline)):
            d = ReportDraft(draft_id="dr_" + uuid.uuid4().hex[:12], job_id=job_id, call_id=job.call_id, kind=kind,
                            scam_type=job.scam_type if job.scam_type in SCAM_LABEL else "unknown",
                            entities=[e for e in job.verified_entities if e.status == "verified"],
                            unclear_count=unclear, narrative=narrative, narrative_source=source,
                            trigger=trigger, band_msg_id=band_msg_id, body_text=fn(job, ctx, tag_phones(narrative), unclear, skills))
            self._save(d)
            self._emit(d)
            drafts.append(d)
        self._set_state(job_id, "done")
        if self.band_cb:
            await self.band_cb("reporter", "human", "drafts ready for review", "post")
        return drafts

    # ---- approve ------------------------------------------------------------
    def approve(self, draft_id: str, approver: str) -> Optional[ReportDraft]:
        d = self.get_draft(draft_id)
        if d is None or d.status != "draft":
            return d
        d.status, d.approved_by, d.approved_at = "approved", approver, datetime.now(timezone.utc).isoformat()
        audit.append(self.s.data_dir, action="approve", draft_id=d.draft_id, job_id=d.job_id, sha256=d.sha256,
                     approver=approver, note="status flip only; nothing was sent")
        self._save(d)
        self._emit(d)
        return d
