"""Settings from environment variables (see .env.example). No secrets in code (G6)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    p = ROOT / ".env"
    if os.environ.get("SAARTHI_NO_DOTENV") or not p.exists():  # tests/run10 never read a developer .env
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0]  # inline comments
        if v.strip():  # empty values stay unset so defaults apply
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _b(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None or v == "" else v.strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _s(name: str, default: str = "") -> str:
    return os.environ.get(name, "") or default


def _default_fixtures() -> str:
    """synthetic.json when present; the public mirror ships only the sanitised synthetic.sample.json."""
    full = ROOT / "fixtures" / "synthetic.json"
    return str(full if full.exists() else ROOT / "fixtures" / "synthetic.sample.json")


@dataclass
class Settings:
    input_mode: str = "scripted"
    app_mode: str = "semi"
    pacing_speed: float = 1.0
    internal_token: str = ""
    kill_switch: bool = False
    max_turns: int = 30
    max_call_seconds: float = 300.0
    demo_synthetic_only: bool = True
    fixtures_path: str = ""
    db_path: str = ""
    audio_cache_dir: str = ""
    data_dir: str = ""
    lyzr_api_key: str = ""
    lyzr_user_id: str = ""
    lyzr_chat_url: str = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"
    lyzr_agent_scammer: str = ""
    lyzr_agent_kamla: str = ""
    lyzr_agent_intel: str = ""
    kamla_timeout_s: float = 6.0
    scammer_timeout_s: float = 8.0
    lyzr_turn_budget_s: float = 3.5  # founder decision: per-turn Lyzr latency budget (preflight S1 p95 gate)
    agent37_url: str = ""
    agent37_instance: str = ""
    tts_provider: str = ""
    tts_api_key: str = ""
    tts_voice_scammer: str = ""
    tts_voice_kamla: str = ""
    kokoro_model_dir: str = ""
    kokoro_device: str = "auto"
    band_enabled: bool = True
    band_api_url: str = "https://app.band.ai/api/v1/agent"
    band_room_id: str = ""
    band_keys: dict = field(default_factory=dict)
    reporter_fallback_s: float = 20.0
    adal_enabled: bool = False
    adal_bin: str = "adal"
    adal_model: str = ""
    adal_timeout_s: float = 90.0
    adal_provider_key: str = ""
    adal_allowed_host: str = ""
    finch_enabled: bool = False
    finch_search_url: str = "https://www.finchtech.ai/api/market/search"
    detectifai_enabled: bool = True
    detectifai_api_key: str = ""
    egress_allowlist: tuple = ()
    start_rate_per_min: int = 12
    ptt_idle_s: float = 60.0
    hosted_scripted_only: bool = False  # hosted abuse guard: the Scammer never calls the live LLM


BAND_AGENTS = ("saarthi", "detector", "kamla", "intel", "verifier", "reporter")


def load_settings() -> Settings:
    _load_dotenv()
    data_dir = _s("DATA_DIR", str(ROOT / "data"))
    tok = _s("INTERNAL_TOKEN")
    if tok and len(tok.encode()) < 32:
        raise ValueError("INTERNAL_TOKEN must be at least 32 bytes")
    s = Settings(
        input_mode=_s("INPUT_MODE", "scripted"),
        app_mode=_s("APP_MODE", "semi"),
        pacing_speed=_f("PACING_SPEED", 1.0),
        internal_token=_s("INTERNAL_TOKEN") or secrets.token_hex(32),
        kill_switch=_b("KILL_SWITCH", False),
        max_turns=int(_f("MAX_TURNS", 30)),
        max_call_seconds=_f("MAX_CALL_SECONDS", 300),
        demo_synthetic_only=_b("DEMO_SYNTHETIC_ONLY", True),
        fixtures_path=_s("FIXTURES_PATH", _default_fixtures()),
        db_path=_s("DB_PATH", str(Path(data_dir) / "saarthi.db")),
        audio_cache_dir=_s("AUDIO_CACHE_DIR", str(ROOT / "audio" / "cache")),
        data_dir=data_dir,
        lyzr_api_key=_s("LYZR_API_KEY"),
        lyzr_user_id=_s("LYZR_USER_ID"),
        lyzr_chat_url=_s("LYZR_CHAT_URL", Settings.lyzr_chat_url),
        lyzr_agent_scammer=_s("LYZR_AGENT_SCAMMER"),
        lyzr_agent_kamla=_s("LYZR_AGENT_KAMLA"),
        lyzr_agent_intel=_s("LYZR_AGENT_INTEL"),
        kamla_timeout_s=_f("KAMLA_TIMEOUT_S", 6),
        scammer_timeout_s=_f("SCAMMER_TIMEOUT_S", 8),
        lyzr_turn_budget_s=_f("LYZR_TURN_BUDGET_S", 3.5),
        agent37_url=_s("AGENT37_URL").rstrip("/"),
        agent37_instance=_s("AGENT37_INSTANCE"),
        tts_provider=_s("TTS_PROVIDER"),
        tts_api_key=_s("TTS_API_KEY"),
        tts_voice_scammer=_s("TTS_VOICE_SCAMMER"),
        tts_voice_kamla=_s("TTS_VOICE_KAMLA"),
        kokoro_model_dir=_s("KOKORO_MODEL_DIR", str(ROOT / "models" / "kokoro-82m")),
        kokoro_device=_s("KOKORO_DEVICE", "auto"),
        band_enabled=_b("BAND_ENABLED", True),
        band_api_url=_s("BAND_API_URL", Settings.band_api_url),
        band_room_id=_s("BAND_ROOM_ID"),
        band_keys={a: _s(f"BAND_KEY_{a.upper()}") for a in BAND_AGENTS},
        reporter_fallback_s=_f("REPORTER_FALLBACK_S", 20),
        adal_enabled=_b("ADAL_ENABLED", False),
        adal_bin=_s("ADAL_BIN", "adal"),
        adal_model=_s("ADAL_MODEL"),
        adal_timeout_s=_f("ADAL_TIMEOUT_S", 90),
        adal_provider_key=_s("ADAL_PROVIDER_KEY"),
        adal_allowed_host=_s("ADAL_ALLOWED_HOST"),
        finch_enabled=_b("FINCH_ENABLED", False),
        finch_search_url=_s("FINCH_SEARCH_URL", Settings.finch_search_url),
        detectifai_enabled=_b("DETECTIFAI_ENABLED", True),
        detectifai_api_key=_s("DETECTIFAI_API_KEY"),
        egress_allowlist=tuple(h.strip().lower() for h in _s("EGRESS_ALLOWLIST").split(",") if h.strip()),
        start_rate_per_min=int(_f("START_RATE_PER_MIN", 12)),
        ptt_idle_s=_f("PTT_IDLE_S", 60),
        hosted_scripted_only=_b("HOSTED_SCRIPTED_ONLY", bool(_s("SPACE_ID"))),  # default on when hosted (HF sets SPACE_ID)
    )
    return s
