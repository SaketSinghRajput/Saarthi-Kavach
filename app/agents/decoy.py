"""Kamla ji (decoy): prompt window, code-rendered read-back, C2 output filter before TTS."""
from __future__ import annotations

import re

from ..fixtures import planted_values, spoken_form, tag_phones
from ..safety.redact import c2_filter
from .lyzr_client import LlmReply, LyzrClient


MAX_WORDS, MAX_SENTENCES = 22, 2
_SENT = re.compile(r"(?<!\.\.)(?<=[.!?।])\s+")
_IDENT = re.compile(r"\d{3,}|@")  # identifiers: a trim must never drop these


def trim_reply(text: str, max_words: int = MAX_WORDS, max_sents: int = MAX_SENTENCES) -> str:
    """Hard cap on a live Kamla reply: <= max_sents sentences and <= max_words words, cut at a sentence
    boundary (else the last comma, else the word limit). Text that would lose a digit run or '@' is returned whole."""
    text = text.strip()
    sents = [x for x in _SENT.split(text) if x]
    kept = sents[:max_sents]
    while len(kept) > 1 and len(" ".join(kept).split()) > max_words:
        kept.pop()
    out = " ".join(kept)
    if len(out.split()) > max_words:
        cut = " ".join(out.split()[:max_words])
        comma = cut.rfind(",")
        out = (cut[:comma] if comma > len(cut) // 2 else cut).rstrip(" ,;:-") + "."
    if out == text:
        return text
    return text if _IDENT.search(text[len(out.rstrip(".")):]) else out


class Decoy:
    def __init__(self, fx: dict, lyzr: LyzrClient):
        self.fx, self.lyzr = fx, lyzr
        self.planted = planted_values(fx)

    def render_readback(self, etype: str, value: str, attempt: int) -> LlmReply:
        tpl = self.fx["readback_templates"][attempt % len(self.fx["readback_templates"])]
        return LlmReply(tpl["text"].format(spoken=spoken_form(value, etype, self.fx)), "readback",
                        tag_phones(tpl["gloss_en"].format(value=value)), 0)

    async def reply(self, call_id: str, seq: int, window: list, scammer_text: str, directive,
                    goal_value=None, readback_attempts: int = 0):
        """-> (LlmReply, redactions). READ_BACK never calls the LLM, so the value cannot be mangled."""
        if directive.kind == "READ_BACK" and directive.target and goal_value:
            r = self.render_readback(directive.target, goal_value, readback_attempts)
        else:
            r = await self.lyzr.kamla(window, scammer_text, directive, seq, call_id)
            if r.source == "lyzr_live":
                r = LlmReply(trim_reply(r.text), r.source, r.gloss_en, r.llm_ms)
        safe, n = c2_filter(r.text, self.planted)
        if n:  # leak caught: the neutral line replaces it, and the English gloss no longer applies
            r = LlmReply(safe, "canned", "Oh dear, I do not follow all this, explain slowly.", r.llm_ms)
        return r, n

    def fallback(self, directive, seq: int) -> LlmReply:
        """Hard-timeout path: a pre-rendered in-character line (still goes through the C2 filter)."""
        line = self.fx["canned"][directive.kind][seq % len(self.fx["canned"][directive.kind])]
        tl = self.fx["target_labels"].get(directive.target or "", {"hi": "", "en": ""})
        text, n = c2_filter(line["text"].replace("{target_label}", tl["hi"]), self.planted)
        return LlmReply(text, "canned", line["gloss_en"].replace("{target_label_en}", tl["en"]), 0)
