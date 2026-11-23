"""Romanised Hinglish -> Devanagari for TTS input.

The TTS bake-off (audio/bakeoff/RESULTS.md) found Devanagari input far better than romanised for
Kokoro Hindi (romanised is read with English phonemes). Scripted lines are converted with a lexicon of
the words in fixtures/synthetic.json (spelled-out English words and initialisms as in the bake-off's
hand transliterations); unknown words fall back to a small rule-based transliterator. Text that is
already Devanagari passes through unchanged.
"""
from __future__ import annotations

import re

_DEV = re.compile(r"[ऀ-ॿ]")
_TOKEN = re.compile(r"[A-Za-z]+|[^A-Za-z]+")

LEXICON = {
    # Hindi
    "aa": "आ", "aaj": "आज", "aap": "आप", "aapka": "आपका", "aapke": "आपके", "aath": "आठ", "ab": "अब",
    "abhi": "अभी", "achha": "अच्छा", "agar": "अगर", "apna": "अपना", "arre": "अरे", "aur": "और",
    "baad": "बाद", "baar": "बार", "baat": "बात", "bahut": "बहुत", "baj": "बज", "band": "बंद",
    "bas": "बस", "bata": "बता", "batana": "बताना", "batao": "बताओ", "beta": "बेटा", "bhar": "भर",
    "bhej": "भेज", "bhejna": "भेजना", "bhi": "भी", "bilkul": "बिल्कुल", "bol": "बोल", "bolo": "बोलो",
    "chal": "चल", "char": "चार", "chashma": "चश्मा", "dega": "देगा", "der": "देर", "deta": "देता",
    "dheere": "धीरे", "dhoond": "ढूँढ", "din": "दिन", "diya": "दिया", "do": "दो", "dobara": "दोबारा",
    "dungi": "दूँगी", "ek": "एक", "galat": "गलत", "gaya": "गया", "gayi": "गई", "ghabra": "घबरा",
    "ghante": "घंटे", "ghar": "घर", "haan": "हाँ", "hai": "है", "hain": "हैं", "ho": "हो", "hoga": "होगा",
    "hone": "होने", "hoon": "हूँ", "humare": "हमारे", "is": "इस", "jaake": "जाके", "jaise": "जैसे",
    "jaldi": "जल्दी", "jayega": "जाएगा", "ji": "जी", "ka": "का", "kaam": "काम", "kam": "कम",
    "kamaya": "कमाया", "kar": "कर", "karna": "करना", "karne": "करने", "karo": "करो", "karti": "करती",
    "karunga": "करूँगा", "kaun": "कौन", "ke": "के", "kharab": "खराब", "khata": "खाता", "ki": "की",
    "kijiye": "कीजिए", "kis": "किस", "kisi": "किसी", "kiya": "किया", "ko": "को", "koi": "कोई",
    "kya": "क्या", "lijiye": "लीजिए", "likh": "लिख", "likha": "लिखा", "likhiye": "लिखिए", "liya": "लिया",
    "liye": "लिए", "logon": "लोगों", "mahine": "महीने", "main": "मैं", "mat": "मत", "mauka": "मौका",
    "mein": "में", "mera": "मेरा", "mere": "मेरे", "mil": "मिल", "mile": "मिले", "milta": "मिलता",
    "mujhe": "मुझे", "mutabik": "मुताबिक", "na": "ना", "naam": "नाम", "nahi": "नहीं",
    "namaste": "नमस्ते", "nau": "नौ", "naye": "नए", "ne": "ने", "nikal": "निकल", "nikla": "निकला",
    "niyam": "नियम", "paanch": "पाँच", "padega": "पड़ेगा", "padhti": "पढ़ती", "paisa": "पैसा",
    "paise": "पैसे", "pakda": "पकड़ा", "pakka": "पक्का", "par": "पर", "pehla": "पहला", "pehle": "पहले",
    "phir": "फिर", "pichle": "पिछले", "raha": "रहा", "rahe": "रहे", "rahi": "रही", "rakhti": "रखती",
    "rehna": "रहना", "ruko": "रुको", "rupaya": "रुपया", "saat": "सात", "sahi": "सही",
    "sahyog": "सहयोग", "samjhao": "समझाओ", "se": "से", "seedha": "सीधा", "sifar": "सिफ़र",
    "sirf": "सिर्फ़", "sun": "सुन", "sunayi": "सुनाई", "sunyie": "सुनिए", "tareeka": "तरीका",
    "teen": "तीन", "theek": "ठीक", "thoda": "थोड़ा", "turant": "तुरंत", "utha": "उठा", "waise": "वैसे",
    "wala": "वाला", "warna": "वरना", "wo": "वो", "woh": "वो", "ye": "ये", "zara": "ज़रा",
    "shunya": "शून्य", "chhe": "छह", "hmm": "हम्म", "oh": "ओह",
    # English words as spoken in Hinglish (bake-off lines.py style)
    "aadhaar": "आधार", "aarav": "आरव", "account": "अकाउंट", "app": "ऐप", "arrest": "अरेस्ट",
    "at": "एट", "bank": "बैंक", "block": "ब्लॉक", "call": "कॉल", "capital": "कैपिटल", "care": "केयर",
    "case": "केस", "cell": "सेल", "code": "कोड", "customer": "कस्टमर", "cyber": "साइबर",
    "demo": "डेमो", "deposit": "डिपॉज़िट", "details": "डिटेल्स", "digital": "डिजिटल",
    "doorbell": "डोरबेल", "dot": "डॉट", "double": "डबल", "error": "एरर", "group": "ग्रुप",
    "guaranteed": "गारंटीड", "hello": "हेलो", "hi": "हाय", "inspector": "इंस्पेक्टर",
    "invest": "इन्वेस्ट", "investment": "इन्वेस्टमेंट", "kavachtest": "कवचटेस्ट", "kycdesk": "केवाईसी डेस्क",
    "last": "लास्ट", "line": "लाइन", "madam": "मैडम", "minute": "मिनट", "narcotics": "नारकोटिक्स",
    "number": "नंबर", "parcel": "पार्सल", "payment": "पेमेंट", "pen": "पेन", "pending": "पेंडिंग",
    "phone": "फ़ोन", "profit": "प्रॉफ़िट", "rate": "रेट", "rathore": "राठौर", "registered": "रजिस्टर्ड",
    "scheme": "स्कीम", "second": "सेकंड", "security": "सिक्योरिटी", "settle": "सेटल", "slot": "स्लॉट",
    "system": "सिस्टम", "the": "द", "time": "टाइम", "trading": "ट्रेडिंग", "transfer": "ट्रांसफर",
    "triple": "ट्रिपल", "update": "अपडेट", "verification": "वेरिफिकेशन", "video": "वीडियो",
    "warrant": "वारंट",
    # initialisms
    "upi": "यू पी आई", "id": "आईडी", "ifsc": "आई एफ एस सी", "cbi": "सी बी आई", "rbi": "आर बी आई",
    "sebi": "सेबी", "kyc": "के वाई सी",
}

LETTERS = {c: n for c, n in zip("abcdefghijklmnopqrstuvwxyz", [
    "ए", "बी", "सी", "डी", "ई", "एफ", "जी", "एच", "आई", "जे", "के", "एल", "एम",
    "एन", "ओ", "पी", "क्यू", "आर", "एस", "टी", "यू", "वी", "डब्ल्यू", "एक्स", "वाई", "ज़ेड"])}

# --- rule-based fallback for words not in the lexicon -------------------------------------------
_CONS = [("chh", "छ"), ("ksh", "क्ष"), ("shh", "ष"), ("kh", "ख"), ("gh", "घ"), ("ch", "च"), ("jh", "झ"),
         ("th", "थ"), ("dh", "ध"), ("ph", "फ"), ("bh", "भ"), ("sh", "श"), ("k", "क"), ("g", "ग"),
         ("c", "क"), ("j", "ज"), ("t", "ट"), ("d", "ड"), ("n", "न"), ("p", "प"), ("b", "ब"), ("m", "म"),
         ("y", "य"), ("r", "र"), ("l", "ल"), ("v", "व"), ("w", "व"), ("s", "स"), ("h", "ह"), ("f", "फ"),
         ("z", "ज़"), ("q", "क"), ("x", "क्स")]
_VOW = [("aa", "आ", "ा"), ("ai", "ऐ", "ै"), ("au", "औ", "ौ"), ("ee", "ई", "ी"), ("oo", "ऊ", "ू"),
        ("ei", "ए", "े"), ("a", "अ", ""), ("i", "इ", "ि"), ("u", "उ", "ु"), ("e", "ए", "े"), ("o", "ओ", "ो")]


def _fallback(word: str) -> str:
    w, out, i, after_cons = word.lower(), [], 0, False
    while i < len(w):
        for rom, dev in _CONS:
            if w.startswith(rom, i):
                if after_cons:
                    out.append("्")
                out.append(dev)
                i, after_cons = i + len(rom), True
                break
        else:
            for rom, ind, mat in _VOW:
                if w.startswith(rom, i):
                    out.append(mat if after_cons else ind)
                    i, after_cons = i + len(rom), False
                    break
            else:
                i += 1
    return "".join(out)


def _word(tok: str) -> str:
    low = tok.lower()
    if low in LEXICON:
        return LEXICON[low]
    if len(tok) == 1:
        return LETTERS[low]
    if tok.isupper() and len(tok) <= 5:  # unknown initialism: spell it out
        return " ".join(LETTERS[c] for c in low)
    return _fallback(tok)


def to_devanagari(text: str) -> str:
    """Convert romanised Hinglish to Devanagari. Already-Devanagari text is returned unchanged."""
    if _DEV.search(text):
        return text
    out = []
    for tok in _TOKEN.findall(text):
        out.append(_word(tok) if tok[0].isalpha() else tok.replace("...", "…"))
    return re.sub(r"\s+", " ", "".join(out)).strip().replace(".", "।").replace("…", "...")
