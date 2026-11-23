from app.agents.verifier import Verifier, normalise_phone
from app.contracts import Entity


def ent(t, v, seq=1):
    return Entity(entity_id="e", call_id="c", type=t, normalized=v, turn_seq=seq)


def test_planted_valid_flow(fx):
    v = Verifier(fx)
    a = v.check(ent("upi", "rathore.demo@kavachtest"))
    assert (a.status, a.confidence) == ("unverified", "medium") and v.is_valid(a)
    b = v.check(ent("upi", "rathore.demo@kavachtest", 2))
    assert (b.status, b.confidence, b.heard_count) == ("verified", "medium", 2)
    c = v.confirm("upi", "rathore.demo@kavachtest")
    assert (c.status, c.confidence, c.readback_confirmed) == ("verified", "high", True)


def test_not_planted_never_verified(fx):
    v = Verifier(fx)
    for i in range(3):
        a = v.check(ent("upi", "someone@ybl", i))
    assert a.status == "unverified" and not v.is_valid(a) and "not planted" in a.reasons
    v.confirm("upi", "someone@ybl")
    assert v.get("upi", "someone@ybl").status == "unverified"


def test_format_rules(fx):
    v = Verifier(fx)
    assert v.check(ent("ifsc", "BAD123")).status == "invalid"
    assert v.check(ent("bank_account", "11111111111")).status == "invalid"  # single repeated digit
    assert v.check(ent("bank_account", "12345")).status == "invalid"
    assert v.check(ent("phone", "1234567890")).status == "invalid"
    assert v.check(ent("upi", "x@unknownhandle")).status == "invalid"  # handle not allowlisted


def test_account_may_not_equal_phone(fx):
    assert Verifier(fx).check(ent("bank_account", "9000000003")).status == "invalid"


def test_ifsc_lookup_is_fictional(fx):
    r = Verifier(fx).check(ent("ifsc", "DEMO0000417"))
    assert r.lookup["fictional"] is True and "fictional" in r.lookup["bank"].lower()


def test_phone_normalisation():
    assert normalise_phone("+91 9000000003") == "9000000003"
    assert normalise_phone("09000000003") == "9000000003"
    assert normalise_phone("919000000003") == "9000000003"


def test_dedup(fx):
    v = Verifier(fx)
    v.check(ent("phone", "9000000003"))
    assert v.check(ent("phone", "9000000003")).checks["dedup_of"] == "phone:9000000003"
    assert len(v.store) == 1


def test_injection_text_is_not_a_candidate_value(fx):
    r = Verifier(fx).check(ent("upi", "ignore-previous@x"))
    assert r.status == "invalid"
