"""REST + SSE. Same-origin only. Passcode on start / PTT / approve / kill (C7); INTERNAL_TOKEN on /api/internal/*."""
from __future__ import annotations

import asyncio
import logging
import re
import hmac
import json
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import runlog
from .bus import EventBus, Snapshot
from .config import ROOT, Settings, load_settings
from .contracts import ApproveBody, PttBody, StartBody
from .fixtures import load_fixtures
from .orchestrator import Busy, Orchestrator

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; connect-src 'self'; img-src 'self' data:"


class _ScrubPc(logging.Filter):
    """Never log the passcode query param."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(re.sub(r"([?&]pc=)[^&\s]*", r"\g<1>***", a) if isinstance(a, str) else a for a in record.args)
        return True


def _sse(ev: dict) -> str:
    return f"id: {ev['event_id']}\nevent: {ev['event']}\ndata: {json.dumps(ev)}\n\n"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    s = settings or load_settings()
    logging.getLogger("uvicorn.access").addFilter(_ScrubPc())
    fx = load_fixtures(s.fixtures_path)
    bus = EventBus(s.db_path)
    snap = Snapshot()
    bus.listeners.append(snap.apply)
    orch = Orchestrator(s, fx, bus)
    starts: deque = deque()
    @asynccontextmanager
    async def lifespan(_app):
        if s.passcode_is_dev:
            print(f"[saarthi] APP_PASSCODE not set: ephemeral dev passcode for this process is {s.app_passcode}")
        await orch.tts.warm_up()
        await orch.tts.prerender([f["text"] for f in fx["fillers"]])  # fillers must be instant mid-call
        yield

    docs = s.passcode_is_dev  # real APP_PASSCODE set (hosted): no public API docs
    app = FastAPI(title="Saarthi Kavach", version="0.1", docs_url="/api/docs" if docs else None,
                  openapi_url="/api/openapi.json" if docs else None,
                  lifespan=lifespan)
    app.state.settings, app.state.bus, app.state.orch = s, bus, orch

    def _pass_ok(candidate: Optional[str]) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), s.app_passcode.encode())

    def read_auth(x_passcode: Optional[str] = Header(default=None), pc: Optional[str] = Query(default=None, max_length=128)) -> None:
        """F7: read endpoints need the passcode when APP_PASSCODE is set (header, or ?pc= for EventSource)."""
        if s.passcode_is_dev:
            return
        if not _pass_ok(x_passcode or pc):
            raise HTTPException(401, "passcode required")

    def need_passcode(x_passcode: Optional[str] = Header(default=None)) -> Optional[str]:
        return x_passcode

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp


    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "active": orch.active, "mode": {"app": s.app_mode, "pacing": s.pacing_speed},
                "band_last_post": orch.band_last_post,  # null: no live post yet this process; else whether the last one landed
                "adapters": {"lyzr": orch.lyzr.live, "tts": orch.tts.live, "band": bool(s.band_room_id),
                             "adal": s.adal_enabled, "finch": s.finch_enabled,
                             "detectifai": bool(s.detectifai_api_key)}}

    @app.get("/api/runs", dependencies=[Depends(read_auth)])
    async def runs() -> dict:
        return {"runs": runlog.list_runs(s.data_dir)}

    @app.get("/api/runs/{run_id}", dependencies=[Depends(read_auth)])
    async def run_one(run_id: str) -> dict:
        r = runlog.read_run(s.data_dir, run_id)
        if r is None:
            raise HTTPException(404, "no such run")
        return r

    @app.get("/api/state", dependencies=[Depends(read_auth)])
    async def state() -> dict:
        v = snap.view()
        return {**v, "agent_status": v.get("agent_status") or orch.agent_status(), "active": orch.active,
                "session_impact": dict(orch.session_impact)}

    @app.post("/api/call/start")
    async def call_start(body: StartBody, x_passcode: Optional[str] = Depends(need_passcode)) -> dict:
        if not _pass_ok(x_passcode or body.passcode):
            raise HTTPException(401, "passcode required")
        now = time.monotonic()
        while starts and now - starts[0] > 60:
            starts.popleft()
        if len(starts) >= s.start_rate_per_min:
            raise HTTPException(429, "too many call starts")
        starts.append(now)
        try:
            call_id = orch.start(body.scenario, body.input_mode)
        except Busy:
            raise HTTPException(409, "a call is already running")
        return {"call_id": call_id, "scenario": body.scenario, "input_mode": body.input_mode}

    @app.post("/api/ptt")
    async def ptt(body: PttBody, x_passcode: Optional[str] = Depends(need_passcode)) -> dict:
        if not _pass_ok(x_passcode):
            raise HTTPException(401, "passcode required")
        if not orch.submit_ptt(body.text):
            raise HTTPException(409, "no active ptt call (or queue full)")
        return {"accepted": True}

    @app.post("/api/kill")
    async def kill(x_passcode: Optional[str] = Depends(need_passcode)) -> dict:
        if not _pass_ok(x_passcode):
            raise HTTPException(401, "passcode required")
        orch.kill()
        return {"kill": True}

    @app.post("/api/drafts/{draft_id}/approve")
    async def approve(draft_id: str, body: ApproveBody, x_passcode: Optional[str] = Depends(need_passcode)) -> dict:
        if not _pass_ok(x_passcode or body.passcode):
            raise HTTPException(401, "passcode required")
        if not draft_id.startswith("dr_") or len(draft_id) > 20:
            raise HTTPException(404, "no such draft")
        d = orch.reporter.get_draft(draft_id)
        if d is None:
            raise HTTPException(404, "no such draft")
        if d.status != "draft":
            raise HTTPException(409, f"draft already {d.status}")
        d = orch.reporter.approve(draft_id, body.approver)
        return {"draft_id": d.draft_id, "status": d.status, "sha256": d.sha256,
                "note": "status flipped only; nothing was sent to any bank or 1930"}

    @app.get("/api/internal/report-jobs/{job_id}")
    async def report_job(job_id: str, x_internal_token: Optional[str] = Header(default=None)):
        if not x_internal_token or not hmac.compare_digest(x_internal_token.encode(), s.internal_token.encode()):
            raise HTTPException(401, "internal token required")
        job = orch.reporter.get_job(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        return job.model_dump()

    @app.get("/api/events", dependencies=[Depends(read_auth)])
    async def events(request: Request, since: Optional[int] = Query(default=None, ge=0),
                     last_event_id: Optional[str] = Header(default=None)):
        start_after = since
        if start_after is None and last_event_id and last_event_id.isdigit():
            start_after = int(last_event_id)

        async def gen():
            q = bus.subscribe()
            last = start_after if start_after is not None else bus.last_id()
            try:
                yield "retry: 2000\n\n"
                if start_after is not None:
                    for ev in bus.since(start_after):
                        last = max(last, ev["event_id"])
                        yield _sse(ev)
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), 15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if ev["event_id"] <= last:
                        continue
                    last = ev["event_id"]
                    yield _sse(ev)
            finally:
                bus.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    Path(s.audio_cache_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=s.audio_cache_dir), name="audio")
    web = ROOT / "web"
    if web.exists():
        @app.get("/", include_in_schema=False)
        async def root() -> RedirectResponse:  # browsers keep the #fragment (passcode) across a 307
            return RedirectResponse("/start.html", status_code=307)
        app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
    return app
