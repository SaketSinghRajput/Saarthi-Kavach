"""Event bus: append-only SQLite log + in-process pub/sub (SSE) + listeners. The bus is authoritative."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

RESERVED = {"event_id", "event", "ts"}
EVENT_TYPES = {"call_status", "turn", "detector", "entity", "goal_state", "band", "metrics", "draft",
               "skill", "policy", "agent_status", "call_summary"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, call_id TEXT, type TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_call ON events(call_id, id);
CREATE TABLE IF NOT EXISTS report_jobs(
  job_id TEXT PRIMARY KEY, call_id TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(
  draft_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_drafts_job ON drafts(job_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class EventBus:
    def __init__(self, db_path: str = ":memory:"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.RLock()
        self.subs: set[asyncio.Queue] = set()
        self.listeners: list[Callable[[dict], None]] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    # -- publish ---------------------------------------------------------
    def publish(self, type_: str, call_id: Optional[str], payload: dict) -> dict:
        if type_ not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type_}")
        if RESERVED & set(payload):
            raise ValueError("payload uses a reserved key")
        ts = now_iso()
        with self.lock:
            cur = self.db.execute("INSERT INTO events(ts, call_id, type, payload) VALUES (?,?,?,?)",
                                  (ts, call_id, type_, json.dumps(payload)))
            self.db.commit()
            eid = cur.lastrowid
        ev = {"event_id": eid, "event": type_, "ts": ts, "call_id": call_id, **payload}
        for fn in list(self.listeners):
            fn(ev)
        self._fanout(ev)
        return ev

    def _fanout(self, ev: dict) -> None:
        for q in list(self.subs):
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not None and running is self.loop:
                q.put_nowait(ev)
            elif self.loop is not None:
                self.loop.call_soon_threadsafe(q.put_nowait, ev)

    # -- subscribe / replay ---------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        self.loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs.discard(q)

    def since(self, event_id: int, call_id: Optional[str] = None, limit: int = 5000) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT id, ts, call_id, type, payload FROM events WHERE id > ? "
                + ("AND call_id = ? " if call_id else "") + "ORDER BY id LIMIT ?",
                (event_id, call_id, limit) if call_id else (event_id, limit)).fetchall()
        return [{"event_id": r[0], "event": r[3], "ts": r[1], "call_id": r[2], **json.loads(r[4])} for r in rows]

    def last_id(self) -> int:
        with self.lock:
            return self.db.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]


class Snapshot:
    """Reduces events into the GET /api/state snapshot (page reload)."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.s = {"call": None, "turns": [], "detector": None, "entities": {}, "goal_state": None,
                  "band": [], "metrics": None, "call_summary": None, "drafts": {}, "skills": [], "agent_status": None,
                  "last_event_id": 0}

    def apply(self, ev: dict) -> None:
        t = ev["event"]
        body = {k: v for k, v in ev.items() if k not in ("event_id", "event")}
        if t == "call_status":
            if ev.get("state") == "ringing":
                self.reset()
            self.s["call"] = body
        elif t == "turn":
            self.s["turns"] = (self.s["turns"] + [body])[-300:]
        elif t == "entity":
            self.s["entities"][ev["id"]] = body
        elif t == "band":
            self.s["band"] = (self.s["band"] + [body])[-200:]
        elif t == "draft":
            self.s["drafts"][ev["draft_id"]] = body
        elif t == "skill":
            self.s["skills"] = (self.s["skills"] + [body])[-20:]
        elif t == "agent_status":
            self.s["agent_status"] = {"agents": ev["agents"]}
        elif t in ("detector", "goal_state", "metrics", "call_summary"):
            self.s[t] = body
        self.s["last_event_id"] = ev["event_id"]

    def view(self) -> dict:
        s = dict(self.s)
        s["entities"] = list(s["entities"].values())
        s["drafts"] = list(s["drafts"].values())
        return s
