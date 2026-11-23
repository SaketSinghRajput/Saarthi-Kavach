"""C9: append-only approvals.jsonl with the sha256 of the approved body."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()


def append(data_dir: str, **entry) -> dict:
    rec = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    with _lock, open(p / "approvals.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec
