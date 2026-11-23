"""Band mirror (one way). Real REST post behind BAND_* keys; otherwise the stub still yields the same
`band` event with mirrored=false. Band never changes state (C4); texts are built by code (G7).

Request shape (band_rest ChatMessageRequest, verified live): POST {api}/chats/{room}/messages with
{"message": {"content": str, "mentions": [{"id": uuid, "handle": "owner/slug", "name": str}]}}.
Mentions need the participant id/handle, not the agent slug, so they are resolved once via
GET {api}/chats/{room}/participants (cached). A message with no resolvable mention is not sent.
"""
from __future__ import annotations

import asyncio
import time

from ..safety import egress


class BandMirror:
    def __init__(self, settings):
        self.s = settings
        self._last = 0.0
        self._lock = asyncio.Lock()
        self._peers: dict = {}  # slug (or "human") -> {"id","handle","name"}

    def live_for(self, agent: str) -> bool:
        return bool(self.s.band_enabled and self.s.band_room_id and self.s.band_keys.get(agent))

    async def _resolve(self, from_agent: str, slug):
        """Mention entry (id, handle, name) for an agent slug; None/"human" gives the room's human. None if unknown."""
        if not self._peers:
            try:
                r = await egress.request("GET", f"{self.s.band_api_url}/chats/{self.s.band_room_id}/participants",
                                         self.s, headers={"X-API-Key": self.s.band_keys[from_agent]}, timeout=5.0)
                rows = (r.json().get("data") or []) if r.status_code < 300 else []
                for p in rows:
                    h = str(p.get("handle") or "")
                    if not (p.get("id") and h):
                        continue
                    entry = {"id": p["id"], "handle": h, "name": p.get("name") or h}
                    if str(p.get("type", "")).lower() == "agent":
                        self._peers[h.rsplit("/", 1)[-1].lower()] = entry
                    else:
                        self._peers.setdefault("human", entry)
            except Exception:
                return None
        return self._peers.get(str(slug or "human").lower())

    async def post(self, from_agent: str, to_agent, text: str, kind: str) -> bool:
        """Returns mirrored (True only if Band accepted the message). Never raises."""
        return (await self.post_ex(from_agent, to_agent, text, kind))[0]

    async def post_ex(self, from_agent: str, to_agent, text: str, kind: str) -> tuple:
        """(mirrored, band_msg_id or None). Never raises."""
        if not self.live_for(from_agent):
            return False, None
        body_text = (f"@{to_agent} " if to_agent and not text.startswith(f"@{to_agent} ") else "") + (f"[thought] {text}" if kind == "thought" else text)
        async with self._lock:  # 1 msg/s, 3 attempts
            peer = await self._resolve(from_agent, to_agent)
            if peer is None or str(peer["handle"]).rsplit("/", 1)[-1].lower() == from_agent:
                return False, None  # Band requires a mention of another participant (not self)
            for attempt in range(3):
                wait = 1.0 - (time.monotonic() - self._last)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
                try:
                    r = await egress.request(
                        "POST", f"{self.s.band_api_url}/chats/{self.s.band_room_id}/messages", self.s,
                        headers={"X-API-Key": self.s.band_keys[from_agent]},
                        json={"message": {"content": body_text[:400], "mentions": [peer]}}, timeout=5.0)
                    if r.status_code < 300:
                        return True, _msg_id(r)
                    if r.status_code < 500 and r.status_code != 429:
                        break  # a 4xx will not fix itself on retry
                except Exception:
                    pass
        return False, None


def _msg_id(r):
    """Parse the id in the Band POST response ({"data": {"id": ...}} or flat)."""
    try:
        d = r.json()
    except Exception:
        return None
    for src in (d, d.get("data") if isinstance(d, dict) else None):
        if isinstance(src, dict):
            for k in ("id", "message_id", "messageId"):
                if isinstance(src.get(k), (str, int)) and not isinstance(src.get(k), bool) and str(src[k]):
                    return str(src[k])[:80]
    return None
