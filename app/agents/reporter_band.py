"""Reporter wake-up via Band (G7). A mention is acted on only if the WHOLE message is the strict
handoff sentence and the job exists in our own store. No Band text is ever passed to an LLM or to AdaL.

Listener: after the Verifier posts the handoff, the Reporter polls the Band room as the Reporter agent (its own
key) for messages addressed to it, parses the stored mention marker form (`@[[id]] report job rj_.. ready`),
looks the job up and runs it with trigger=band_mention + the Band message id. Poll ~1 s, back off on 429, and
give up after REPORTER_FALLBACK_S: the orchestrator then delivers the mention in-process (direct_fallback).
Missing Band key or Band off => listener is not live and the fallback path is used immediately.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ..contracts import extract_job_id, extract_job_id_band
from ..safety import egress
from .reporter import Reporter

POLL_S = 1.0


class ReporterBand:
    def __init__(self, settings, reporter: Reporter):
        self.s, self.reporter = settings, reporter
        self._seen: set = set()

    @property
    def listening(self) -> bool:
        return bool(self.s.band_enabled and self.s.band_room_id and self.s.band_keys.get("reporter"))

    async def on_mention(self, text: str, trigger: str = "band_mention", band_msg_id: Optional[str] = None) -> Optional[list]:
        job_id = extract_job_id(text) or extract_job_id_band(text)
        if job_id is None:
            return None  # anything that is not the exact handoff sentence is ignored
        if self.reporter.get_job(job_id) is None:
            return None  # forged id: nothing exists, nothing runs
        return await self.reporter.run_job(job_id, trigger, band_msg_id)

    async def _fetch(self) -> Optional[list]:
        """Newest messages addressed to the Reporter; None on error / rate limit (caller backs off)."""
        try:
            r = await egress.request(
                "GET", f"{self.s.band_api_url}/chats/{self.s.band_room_id}/messages", self.s,
                headers={"X-API-Key": self.s.band_keys["reporter"]},
                params={"sort_order": "desc", "limit": 10}, timeout=5.0)
            if r.status_code >= 300:
                return None
            d = r.json()
            rows = d.get("data") if isinstance(d, dict) else d
            return rows if isinstance(rows, list) else []
        except Exception:
            return None

    async def listen(self, job_id: str, timeout_s: float, poll_s: float = POLL_S) -> bool:
        """Wait for a Band mention that wakes the Reporter for `job_id`. True once its drafts exist."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        delay = poll_s
        while loop.time() < deadline:
            rows = await self._fetch()
            if rows is None:
                delay = min(delay * 2, 8.0)  # error or 429: back off
            else:
                delay = poll_s
                for m in rows:
                    mid = str(m.get("id") or "")[:80] if isinstance(m, dict) else ""
                    if not mid or mid in self._seen:
                        continue
                    self._seen.add(mid)
                    if len(self._seen) > 500:
                        self._seen.clear()
                    content = m.get("content")
                    if isinstance(content, str):
                        await self.on_mention(content, "band_mention", mid)
                if self.reporter.drafts_for(job_id):
                    return True
            await asyncio.sleep(min(delay, max(0.0, deadline - loop.time())))
        return bool(self.reporter.drafts_for(job_id))
