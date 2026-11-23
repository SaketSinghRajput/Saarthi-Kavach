"""Finch skill scout (read-only DISCOVERY). Live search behind FINCH_ENABLED; dated offline snapshot otherwise.
Finch never executes anything for us: every result carries role="discovery_only".
Keywords are tried in order until one yields results, inside one overall time budget."""
from __future__ import annotations

import time

from ..safety import egress

BUDGET_S = 8.0       # total wall-clock budget across keyword attempts (runs in background; TTS CPU load made 4 s too tight)
MAX_SKILLS = 3
SUMMARY_CHARS = 100


def _clean(v, n: int) -> str:
    return str(v or "").encode("utf-8", "ignore").decode("utf-8", "ignore").strip()[:n]


def _free(item: dict) -> bool:
    """Live items carry price.atomic ("0" = free); older shape had unitPrice. Missing price = not claimed free."""
    price = item.get("price")
    raw = item.get("unitPrice", price.get("atomic") if isinstance(price, dict) else None)
    return str(raw) == "0"


def _skill(item: dict) -> dict:
    return {"name": _clean(item.get("name") or item.get("title"), 60), "slug": _clean(item.get("slug"), 80),
            "category": _clean(item.get("category"), 40), "free": _free(item),
            "summary": _clean(item.get("summary"), SUMMARY_CHARS), "source": "finch_live"}


class FinchScout:
    def __init__(self, settings, fx: dict):
        self.s, self.fx = settings, fx

    async def scout(self, scam_type: str) -> dict:
        kws = self.fx["finch_keywords"].get(scam_type, [])
        if self.s.finch_enabled and kws:
            deadline = time.monotonic() + BUDGET_S
            for kw in kws:
                left = deadline - time.monotonic()
                if left <= 0.05:
                    break
                try:
                    r = await egress.request("GET", self.s.finch_search_url, self.s,
                                             params={"kind": "skill", "q": kw}, timeout=left)
                    r.raise_for_status()
                    data = r.json()
                    items = (data.get("results") or data.get("items")) if isinstance(data, dict) else data
                    items = items if isinstance(items, list) else []
                    skills = [_skill(i) for i in items[:MAX_SKILLS] if isinstance(i, dict)]
                    skills = [k for k in skills if k["name"]]
                    if skills:
                        total = data.get("totalCount") if isinstance(data, dict) else None
                        return {"skills": skills, "live": True, "query": kw,
                                "total": total if isinstance(total, int) else len(items),
                                "role": "discovery_only"}
                except Exception:
                    continue
        snap = [{"name": s["name"], "slug": s.get("slug", ""), "category": s.get("category", ""),
                 "free": bool(s.get("free")), "summary": s.get("summary", ""), "source": s["source"]}
                for s in self.fx["finch_snapshot"]]
        return {"skills": snap, "live": False, "query": (kws or [""])[0], "total": len(snap),
                "role": "discovery_only"}
