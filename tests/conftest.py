import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _k in list(os.environ):
    if _k.startswith(("LYZR_", "BAND_", "TTS_", "DETECTIFAI_", "ADAL_", "FINCH_")):
        os.environ.pop(_k)
os.environ["SAARTHI_NO_DOTENV"] = "1"
os.environ["PACING_SPEED"] = "0"
os.environ.pop("APP_PASSCODE", None)
os.environ.pop("SPACE_ID", None)
os.environ["HOSTED_SCRIPTED_ONLY"] = "true"  # tests run as the hosted demo: scammer never calls the live LLM
os.environ["INTERNAL_TOKEN"] = "t" * 40

from app.bus import EventBus  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.fixtures import load_fixtures  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    s = load_settings()
    s.data_dir = str(tmp_path)
    s.db_path = str(tmp_path / "t.db")
    s.audio_cache_dir = str(tmp_path / "audio")
    s.pacing_speed = 0
    return s


@pytest.fixture
def fx(settings):
    return load_fixtures(settings.fixtures_path)


def run_call(settings, fx, scenario="digital_arrest", mode="scripted"):
    """Run one full offline call; returns (orchestrator, result)."""
    async def go():
        orch = Orchestrator(settings, fx, EventBus(":memory:"))
        orch.start(scenario, mode)
        return orch, await orch.wait()
    return asyncio.run(go())


# The public mirror ships only fixtures/synthetic.sample.json (outline beats, no scripted payment read-outs).
# Tests that depend on the full scam beats carry this marker and are skipped there with a reason.
needs_full_fixture = pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent / "fixtures" / "synthetic.json").exists(),
    reason="needs the full scam beats in fixtures/synthetic.json (withheld from the public mirror)")
