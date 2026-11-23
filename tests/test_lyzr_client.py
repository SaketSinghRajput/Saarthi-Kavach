import json
from pathlib import Path

from app.agents.lyzr_client import clean_scammer_text

_FXD = Path(__file__).resolve().parent.parent / "fixtures"  # the public mirror ships only synthetic.sample.json
FX = json.loads((_FXD / ("synthetic.json" if (_FXD / "synthetic.json").exists() else "synthetic.sample.json")).read_text(encoding="utf-8"))
OUT = "Fake KYC update (bank customer care). Planted details: upi kycdesk.demo@kavachtest"


def test_strips_role_prefixes():
    assert clean_scammer_text("scammer: Namaste ji") == "Namaste ji"
    assert clean_scammer_text("Scammer - Namaste ji") == "Namaste ji"
    assert clean_scammer_text("**Caller:** Scammer: hello") == "hello"
    assert clean_scammer_text("Scammerji, suniye") == "Scammerji, suniye"


def test_placeholders_filled_from_scenario():
    t = clean_scammer_text("Main [Your Name] bol raha hoon, [Your Bank Name] se.", FX, OUT)
    assert "[" not in t and "Demo Bank customer care" in t
    assert "kycdesk.demo@kavachtest" in clean_scammer_text("UPI [UPI ID] par bhejiye", FX, OUT)


def test_unknown_placeholders_dropped_and_parentheticals_kept():
    assert clean_scammer_text("Hello [Your Bank Name] ji.") == "Hello ji."
    assert clean_scammer_text("Jaldi karo (abhi) ji") == "Jaldi karo (abhi) ji"
