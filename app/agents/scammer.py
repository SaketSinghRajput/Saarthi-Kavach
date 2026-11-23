"""Scammer. `semi` = scripted beat machine (offline, deterministic); `live` = Lyzr agent with beat fallback.

Entity beats are released only when Kamla asks (the last directive says ASK/REPEAT/METHOD_FAILED for it).
"""
from __future__ import annotations

from ..fixtures import tag_phones


class SemiScammer:
    def __init__(self, fx: dict, scenario_key: str):
        self.fx = fx
        self.key = scenario_key
        self.sc = fx["scenarios"][scenario_key]
        self.lines = fx["scammer_lines"]
        self.beat_idx = 0
        self.pressure_idx = 0
        self.said: dict[str, str] = {}  # target -> value currently stated
        self.corrected: set[str] = set()
        self.evaded: set[str] = set()

    def _line(self, tpl: dict, **kw) -> dict:
        text = tpl["text"].format(**{k: v for k, v in kw.items() if k in ("spoken", "target_label")})
        gloss = tpl["gloss_en"].format(**{k: v for k, v in kw.items() if k in ("value", "target_label_en")})
        return {"text": text, "gloss_en": tag_phones(gloss), "source": "scripted"}

    def _give(self, target: str, method_failed: bool) -> dict:
        ent = self.sc["entities"][target]
        var = ent.get("variant")
        use_var = bool(var) and target == self.sc.get("correction_for") and target not in self.said \
            and target not in self.corrected and not method_failed
        src = var if use_var else ent
        self.said[target] = src["value"]
        tpl = self.lines["method_failed"] if method_failed else self.lines["entity"][target]
        return self._line(tpl, spoken=src["spoken"], value=src["value"])

    def next(self, directive) -> dict:
        kind = getattr(directive, "kind", None)
        target = getattr(directive, "target", None)
        ents = self.sc["entities"]
        if kind in ("ASK", "REPEAT", "METHOD_FAILED") and target in ents:
            ev = self.sc.get("evasions", {}).get(target)
            if kind == "ASK" and ev and target not in self.evaded:
                self.evaded.add(target)
                return {"text": ev["text"], "gloss_en": ev["gloss_en"], "source": "scripted"}
            return self._give(target, kind == "METHOD_FAILED")
        if kind == "READ_BACK" and target in ents:
            ent = ents[target]
            if ent.get("variant") and self.said.get(target) == ent["variant"]["value"]:
                self.corrected.add(target)
                self.said[target] = ent["value"]
                tl = self.fx["target_labels"][target]
                return self._line(self.lines["correction"], spoken=ent["spoken"], value=ent["value"],
                                  target_label=tl["hi"], target_label_en=tl["en"])
            return self._line(self.lines["affirm"])
        if kind == "WRAP_UP":
            return self._line(self.lines["wrap_up"])
        beats = self.sc["beats"]
        if self.beat_idx < len(beats):
            b = beats[self.beat_idx]
            self.beat_idx += 1
            return {"text": b["text"], "gloss_en": b["gloss_en"], "source": "scripted"}
        p = self.sc["pressure_lines"]
        line = p[self.pressure_idx % len(p)]
        self.pressure_idx += 1
        return {"text": line["text"], "gloss_en": line["gloss_en"], "source": "scripted"}
