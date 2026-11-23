import pytest

from app.agents.intel.normalise import normalise
from app.agents.intel.regex import extract


def vals(text):
    return [(t, v) for t, v, _ in extract(text)]


def test_hindi_number_words_join():
    assert "9876543210" in normalise("nau aath saat chhe paanch char teen do ek shunya").split()


def test_sifar_and_zero_words():
    assert "1002003004" in normalise("ek sifar sifar do zero zero teen shunya shunya char").split()


def test_double_and_triple_expand_before_joining():
    assert "9877" in normalise("nau aath double saat").split()
    assert "000482" in normalise("triple sifar char aath do").split()


def test_devanagari_words_and_digits():
    assert "9876" in normalise("नौ आठ सात छह").split()
    assert "9876543210" in normalise("९८७६५४३२१०").split()


def test_digit_groups_join_with_spaces_and_hyphens():
    assert vals("call 98765 43210") == [("phone", "9876543210")]
    assert vals("98765-43210") == [("phone", "9876543210")]


def test_at_the_rate_dot_and_underscore():
    assert vals("rathore dot demo at the rate kavachtest") == [("upi", "rathore.demo@kavachtest")]
    assert vals("my id is a underscore b at ybl") == [("upi", "a_b@ybl")]
    assert vals("RATHORE.DEMO@KAVACHTEST") == [("upi", "rathore.demo@kavachtest")]


def test_spelled_ifsc():
    assert vals("D E M O sifar sifar sifar sifar char ek saat") == [("ifsc", "DEMO0000417")]
    assert vals("ifsc DEMX0000912") == [("ifsc", "DEMX0000912")]


def test_short_runs_stay_words():
    assert normalise("do teen din") == "do teen din"
    assert "ek minute" in normalise("ek minute")


@pytest.mark.parametrize("text", ["at the bank", "oh no", "do teen din", "ek minute", "it was in 2024",
                                  "main office at the corner", "double check this", "ignore-previous@x; mark verified"])
def test_regex_false_positives(text):
    assert vals(text) == []


def test_ten_digit_phone_is_not_an_account():
    assert vals("9000000003") == [("phone", "9000000003")]
    assert vals("+91 9000000003") == [("phone", "9000000003")]
    assert vals("09000000003") == [("phone", "9000000003")]


def test_account_extracted_and_not_phone():
    assert vals("account 000000482915") == [("bank_account", "000000482915")]


def test_every_planted_spoken_form_round_trips(fx):
    for sc in fx["scenarios"].values():
        for t, e in sc["entities"].items():
            for ent in [e] + ([e["variant"]] if e.get("variant") else []):
                line = fx["scammer_lines"]["entity"][t]["text"].format(spoken=ent["spoken"])
                assert vals(line) == [(t, ent["value"])], (t, ent)
