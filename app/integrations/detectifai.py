"""DetectifAI voice check (a flag, not a verdict). Real REST behind DETECTIFAI_API_KEY and an audio file;
the offline stub returns flag=False with an honest source label (it does NOT pretend to have checked).
Request/response shape is UNVERIFIED until preflight."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..safety import egress

URL = "https://platform.detectif.ai/v1/deepfake/detect"


class DetectifAI:
    def __init__(self, settings):
        self.s = settings

    async def check(self, audio_path: Optional[str]) -> dict:
        if not (self.s.detectifai_enabled and self.s.detectifai_api_key and audio_path and Path(audio_path).exists()):
            return {"flag": False, "source": "stub:not_checked"}
        try:
            with open(audio_path, "rb") as f:
                r = await egress.request("POST", URL, self.s, headers={"Authorization": f"Bearer {self.s.detectifai_api_key}"},
                                         files={"file": ("clip.mp3", f.read())}, timeout=15.0)
            r.raise_for_status()
            d = r.json()
            score = d.get("score") or d.get("probability") or d.get("confidence")
            label = str(d.get("label") or d.get("result") or "").lower()
            flag = bool(d.get("is_deepfake")) or label in ("synthetic", "fake", "deepfake", "ai")
            return {"flag": flag, "source": "detectifai", "score": score, "note": "flag, not verdict"}
        except Exception:
            return {"flag": False, "source": "stub:error"}
