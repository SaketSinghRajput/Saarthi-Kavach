from app.agents.detector import Detector, STAGE_ORDER


def test_risk_rises_and_stage_never_goes_back(fx):
    d = Detector(fx, "c")
    r1 = d.update("Main CBI inspector bol raha hoon, parcel pakda gaya", 1)
    r2 = d.update("warrant hai, arrest ho jayega abhi", 2)
    r3 = d.update("UPI par transfer karo", 3)
    r4 = d.update("hello kaise ho", 4)
    assert r1.risk < r2.risk <= r3.risk and r2.is_scam_likely
    assert STAGE_ORDER.index(r4.stage) >= STAGE_ORDER.index(r3.stage) and r4.stage == "payment_ask"
    assert r4.scam_type == "digital_arrest"


def test_pressure_only_after_payment_ask(fx):
    d = Detector(fx, "c")
    assert d.update("jaldi karo", 1).stage != "pressure"
    d.update("UPI transfer", 2)
    assert d.update("jaldi karo ji", 3).stage == "pressure"


def test_benign_text_is_low_risk(fx):
    r = Detector(fx, "c").update("Namaste, kal shaam ko chai peene aayiye", 1)
    assert r.risk == 0 and r.scam_type == "unknown" and not r.is_scam_likely


def test_scam_types(fx):
    assert Detector(fx, "c").update("aapka KYC update pending hai, customer care, account block ho jayega", 1).scam_type == "fake_kyc"
    assert Detector(fx, "c").update("guaranteed profit trading group, abhi invest karo", 1).scam_type == "fake_investment"


BENIGN = [
    "Hello, this is Priya from your bank's customer care. Your new debit card has been dispatched and will reach you in five working days.",
    "Your electricity bill for this month is ready. You can pay it online on the official website or at the nearest collection counter before the due date.",
    "Your courier is out for delivery today. The delivery partner will call you when he is near your address.",
    "Reminder from the bank: your KYC documents are due for periodic renewal. Please visit your home branch with your ID proof when convenient.",
    "This is an automated message from the telecom operator: your recharge of 299 rupees was successful and is valid for 28 days.",
    "Hi, I am calling from the gas agency to confirm the delivery slot for your cylinder tomorrow morning.",
    "Beta, school fees ke account mein transfer ho gaya, receipt sambhal kar rakhna.",
    "Namaste, bijli board se bol raha hoon, meter reading kal aayegi, bill online bhar sakte hain.",
]


def test_benign_calls_are_not_flagged(fx):
    for text in BENIGN:
        r = Detector(fx, "c").update(text, 1)
        assert r.scam_type == "unknown" and not r.is_scam_likely, (text, r.risk, r.scam_type)


def test_benign_conversation_stays_clean(fx):
    d = Detector(fx, "c")
    for i, text in enumerate([BENIGN[2], "Your parcel will be delivered between four and six this evening.",
                              "You can pay cash on delivery to the rider or choose to pay online on the courier app."]):
        r = d.update(text, i + 1)
    assert r.scam_type == "unknown" and r.risk < 0.6


def test_general_scam_language_english_hindi_hinglish(fx):
    cases = {
        "fake_kyc": ["Your electricity connection will be disconnected tonight unless you call this number immediately about the pending bill.",
                     "Your KYC has expired and your account will be blocked today, update it now.",
                     "आपका अकाउंट कुछ ही सेकंड में ब्लॉक हो जाएगा"],
        "digital_arrest": ["Your Aadhaar was used to book a parcel with drugs at customs. Stay on the video call and do not tell anyone, or you will be arrested.",
                           "This is the cyber crime branch. A warrant is issued in your name; keep the call on all night.",
                           "Aapke naam ka parcel customs mein pakda gaya hai, kisi ko mat batana, video call par rehna."],
        "fake_investment": ["Join our trading group for guaranteed returns, pay the first deposit today and double your money."],
    }
    for expect, texts in cases.items():
        for t in texts:
            assert Detector(fx, "c").update(t, 1).scam_type == expect, t


def test_awareness_advisory_is_not_flagged(fx):
    r = Detector(fx, "c").update("Beware of fraud calls: never share your OTP, CVV or PIN, even if the caller says he is from the RBI.", 1)
    assert r.scam_type == "unknown" and not r.is_scam_likely and r.risk < 0.6


def test_corroborated_scam_story_alerts(fx):
    # reported-speech phrasing, no verbatim keywords from the synthetic scripts
    d = Detector(fx, "c")
    for i, t in enumerate(["A caller posing as a federal investigation agency officer said the victim was implicated in money laundering.",
                           "He threatened imprisonment and kept the victim in custody on a video call.",
                           "The victim was told to liquidate fixed deposits and transfer the funds to a safe account."]):
        r = d.update(t, i)
    assert r.scam_type == "digital_arrest" and r.is_scam_likely


def test_generic_words_alone_stay_below_alert(fx):
    r = Detector(fx, "c").update("The company said the payment was reversed to your account; please check the link in the app and download the receipt.", 1)
    assert not r.is_scam_likely and r.scam_type == "unknown"
