"""Data contracts (ARCHITECTURE section 5). Pydantic is the source of truth."""
from __future__ import annotations

import hashlib
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

EntityType = Literal["upi", "bank_account", "ifsc", "phone"]
ScamType = Literal["digital_arrest", "fake_kyc", "fake_investment", "unknown"]
Stage = Literal["hook", "authority", "urgency", "payment_ask", "pressure", "unknown"]
WATERMARK = "DRAFT - SIMULATED DEMO DATA - NOT SENT TO ANY BANK OR 1930"

# G7: the only thing that crosses Band is a job id, parsed with this strict regex.
JOB_ID_RE = re.compile(r"^rj_[a-f0-9]{12}$")
HANDOFF_RE = re.compile(r"^@reporter report job (rj_[a-f0-9]{12}) ready$")


# Band stores a mention as an `@[[<uuid>]]` marker prepended to the stored content (live: `@[[uuid]] @reporter report job ..`);
# the whole message must still be the handoff sentence, preceded only by the marker and/or @reporter.
BAND_HANDOFF_RE = re.compile(r"^(?=@)(?:@\[\[[A-Za-z0-9_./:-]{1,80}\]\] +)?(?:@reporter +){0,2}report job (rj_[a-f0-9]{12}) ready$")


def extract_job_id_band(text: str) -> Optional[str]:
    """Strict, for text read back from Band (plain or stored marker mention form)."""
    m = BAND_HANDOFF_RE.match(text.strip()) if isinstance(text, str) and len(text) < 140 else None
    return m.group(1) if m else None


def extract_job_id(text: str) -> Optional[str]:
    """Strict: the whole message must be the handoff sentence. Anything else is ignored."""
    m = HANDOFF_RE.match(text.strip()) if isinstance(text, str) and len(text) < 100 else None
    return m.group(1) if m else None


class DetectorResult(BaseModel):
    call_id: str
    turn_seq: int
    risk: float = Field(ge=0, le=1)
    scam_type: ScamType
    stage: Stage
    signals: list[str] = Field(default_factory=list, max_length=10)
    is_scam_likely: bool
    deepfake: Optional[dict] = None


class Entity(BaseModel):
    entity_id: str
    call_id: str
    type: EntityType
    raw_span: str = Field(default="", max_length=120)
    normalized: str = Field(max_length=64)
    source: Literal["regex", "llm"] = "regex"
    turn_seq: int


class VerifiedEntity(BaseModel):
    call_id: str
    type: EntityType
    value: str = Field(max_length=64)
    status: Literal["verified", "unverified", "invalid"]
    confidence: Literal["high", "medium", "low"]
    lookup: Optional[dict] = None
    checks: dict = Field(default_factory=dict)
    heard_count: int = 0
    readback_confirmed: bool = False
    reasons: list[str] = Field(default_factory=list)
    first_turn: int = 0
    last_turn: int = 0


class Directive(BaseModel):
    directive_id: str
    kind: Literal["NEUTRAL", "STALL", "ASK", "REPEAT", "READ_BACK", "METHOD_FAILED", "WRAP_UP"]
    target: Optional[EntityType] = None
    tactic_id: str = ""
    text: str = Field(default="", max_length=240)


class ReportJob(BaseModel):
    job_id: str
    call_id: str
    verified_entities: list[VerifiedEntity]
    scam_type: str
    facts: dict
    state: Literal["pending", "running", "done", "failed"] = "pending"

    @field_validator("job_id")
    @classmethod
    def _jid(cls, v: str) -> str:
        if not JOB_ID_RE.match(v):
            raise ValueError("bad job_id")
        return v


class ReportDraft(BaseModel):
    draft_id: str
    job_id: str
    call_id: str
    kind: Literal["bank_alert", "helpline_1930"]
    watermark: Literal["DRAFT - SIMULATED DEMO DATA - NOT SENT TO ANY BANK OR 1930"] = WATERMARK
    scam_type: ScamType = "unknown"
    entities: list[VerifiedEntity]
    unclear_count: int = 0
    narrative: str = Field(default="", max_length=1200)
    narrative_source: Literal["adal", "adal_finch_skill", "template"] = "template"
    trigger: Literal["band_mention", "direct_fallback"] = "band_mention"
    band_msg_id: Optional[str] = Field(default=None, max_length=80)
    body_text: str = Field(max_length=6000)
    sha256: str = ""
    status: Literal["draft", "approved", "rejected"] = "draft"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    @field_validator("entities")
    @classmethod
    def _only_verified(cls, v: list[VerifiedEntity]) -> list[VerifiedEntity]:
        bad = [e for e in v if e.status != "verified"]
        if bad:  # C4: a draft may only carry verified entities
            raise ValueError("draft contains non-verified entity")
        return v

    @model_validator(mode="after")
    def _hash(self) -> "ReportDraft":
        digest = hashlib.sha256(self.body_text.encode("utf-8")).hexdigest()
        if self.sha256 and self.sha256 != digest:
            raise ValueError("sha256 mismatch")
        self.sha256 = digest
        return self


class PttBody(BaseModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=500)


class StartBody(BaseModel):
    model_config = {"extra": "forbid"}
    scenario: Literal["digital_arrest", "fake_kyc", "fake_investment"] = "digital_arrest"
    input_mode: Literal["scripted", "ptt"] = "scripted"


class ApproveBody(BaseModel):
    model_config = {"extra": "forbid"}
    approver: str = Field(default="human", max_length=40)
