"""TTS adapter. Providers: local Kokoro-82M (TTS_PROVIDER=kokoro), ElevenLabs (elevenlabs), offline stub otherwise.

Catalog/preset voices only, never cloning (gate G2): Kokoro voices are an allow-list of exactly two ids,
Kamla = hf_beta and scammer = hm_psi (founder decision). Clips are cached by hash of (voice, text). The stub
returns no audio (audio_url=None) but a duration estimate, so pacing and 'minutes wasted' behave the same
offline. Kokoro is an optional import: if the package or model files are missing we log and use the stub.
The ElevenLabs request shape is UNVERIFIED until preflight S2 runs with a real key.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import io
import logging
import sys
import threading
import types
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hinglish import to_devanagari

log = logging.getLogger("saarthi.tts")

KOKORO_VOICES = {"kamla": "hf_beta", "scammer": "hm_psi"}  # G2 allow-list: exactly these two ids
KOKORO_SPEED = {"kamla": 0.85, "scammer": 1.05}            # from the bake-off (audio/bakeoff/RESULTS.md)
KOKORO_RATE = 24000


class VoiceNotAllowed(ValueError):
    pass


def check_voice(voice: str) -> str:
    if voice not in KOKORO_VOICES.values():
        raise VoiceNotAllowed(f"voice {voice!r} is not allowed; catalog voices only: {sorted(KOKORO_VOICES.values())}")
    return voice


@dataclass
class Clip:
    url: Optional[str]
    duration_ms: int
    cache_hit: bool
    voice: str
    live: bool


def estimate_ms(text: str) -> int:
    return max(900, len(text) * 62)


def clip_key(voice: str, text: str) -> str:
    return hashlib.sha256(f"{voice}|{text}".encode()).hexdigest()[:24]


class KokoroEngine:
    """Lazy-loaded Kokoro-82M (Hindi, lang_code 'h'). render() is blocking; call via a thread."""

    def __init__(self, model_dir: str, device: str = "auto"):
        self.dir, self.device, self._pipe, self._lock = Path(model_dir), device, None, threading.Lock()

    @staticmethod
    def available(model_dir: str) -> bool:
        d = Path(model_dir)
        return (importlib.util.find_spec("kokoro") is not None and (d / "kokoro-v1_0.pth").exists()
                and (d / "config.json").exists())

    def _load(self):
        if "spacy" not in sys.modules:
            try:
                import spacy  # noqa: F401
            except Exception:  # real spacy can be blocked by OS policy; unused for Hindi G2P (as in the bake-off)
                sys.modules["spacy"] = types.ModuleType("spacy")
        import torch
        from kokoro import KModel, KPipeline
        dev = ("cuda" if torch.cuda.is_available() else "cpu") if self.device == "auto" else self.device
        model = KModel(config=str(self.dir / "config.json"), model=str(self.dir / "kokoro-v1_0.pth"),
                       repo_id="hexgrad/Kokoro-82M").to(dev).eval()
        self._pipe = KPipeline(lang_code="h", repo_id="hexgrad/Kokoro-82M", model=model)
        log.info("kokoro loaded on %s", dev)

    def render(self, text: str, voice: str, speed: float) -> bytes:
        check_voice(voice)  # path below is built only from an allow-listed id
        import numpy as np
        with self._lock:
            if self._pipe is None:
                self._load()
            chunks = [r.audio.cpu().numpy() for r in
                      self._pipe(to_devanagari(text), voice=str(self.dir / "voices" / f"{voice}.pt"), speed=speed)]
        pcm = (np.clip(np.concatenate(chunks) if chunks else np.zeros(1, np.float32), -1, 1) * 32767).astype("<i2")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(KOKORO_RATE)
            w.writeframes(pcm.tobytes())
        return buf.getvalue()


def _make_engine(settings) -> Optional[KokoroEngine]:
    if not KokoroEngine.available(settings.kokoro_model_dir):
        return None
    return KokoroEngine(settings.kokoro_model_dir, settings.kokoro_device)


def wav_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as w:
        return int(w.getnframes() * 1000 / w.getframerate())


class TTS:
    def __init__(self, settings):
        self.s = settings
        self.cache = Path(settings.audio_cache_dir)
        self.engine: Optional[KokoroEngine] = None
        if settings.tts_provider == "kokoro":
            self.engine = self._init_kokoro()

    async def warm_up(self) -> None:
        """Load Kokoro and render one throwaway line at startup so the first call turn doesn't pay the cold load."""
        if self.engine is None:
            return
        try:
            # several realistic lengths: the first long render otherwise pays a multi-second GPU/kernel cold start
            for line in ("namaste", "Arre beta, thoda dheere boliye, main likh rahi hoon.",
                         "Haan haan, sun rahi hoon. Aap kaun se bank se bol rahe ho, zara phir se batao na beta?"):
                await asyncio.to_thread(self.engine.render, line, KOKORO_VOICES["kamla"], KOKORO_SPEED["kamla"])
            log.info("kokoro warmed up")
        except Exception as e:  # never block startup over audio
            log.error("kokoro warm-up failed (%s)", type(e).__name__)

    async def prerender(self, texts: list) -> int:
        """Render and cache Kamla-voice lines (the fillers) so they are instant mid-call. Returns clips ready."""
        n = 0
        for t in texts:
            try:
                c = await self.synth(t, "kamla")
                n += 1 if c.live else 0
            except Exception as e:  # never block startup over audio
                log.error("prerender failed (%s)", type(e).__name__)
        return n

    def _init_kokoro(self) -> Optional[KokoroEngine]:
        for role in KOKORO_VOICES:
            try:
                check_voice(self._voice(role))
            except VoiceNotAllowed as e:
                log.error("TTS_PROVIDER=kokoro but %s; falling back to the stub", e)
                return None
        eng = _make_engine(self.s)
        if eng is None:
            log.warning("TTS_PROVIDER=kokoro but the kokoro package or model files in %s are missing; using the stub",
                        self.s.kokoro_model_dir)
        return eng

    @property
    def live(self) -> bool:
        if self.s.tts_provider == "kokoro":
            return self.engine is not None
        return self.s.tts_provider == "elevenlabs" and bool(self.s.tts_api_key)

    def _voice(self, role: str) -> str:
        r = "scammer" if role == "scammer" else "kamla"
        configured = self.s.tts_voice_scammer if r == "scammer" else self.s.tts_voice_kamla
        if self.s.tts_provider == "kokoro":
            return configured or KOKORO_VOICES[r]
        return configured or ""

    async def synth(self, text: str, role: str) -> Clip:
        if self.s.tts_provider == "kokoro":
            return await self._synth_kokoro(text, role)
        voice = self._voice(role)
        if not (self.live and voice):
            return Clip(None, estimate_ms(text), False, "stub", False)
        f = self.cache / f"{clip_key(voice, text)}.mp3"
        try:
            if f.exists():
                return Clip(f"/audio/{f.name}", int(f.stat().st_size * 8 / 64), True, voice, True)
            from ..safety import egress  # lazy: keeps the local-only path (prerender venv) free of httpx
            r = await egress.request(
                "POST", f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64", self.s,
                headers={"xi-api-key": self.s.tts_api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2"}, timeout=8.0)
            r.raise_for_status()
            self.cache.mkdir(parents=True, exist_ok=True)
            f.write_bytes(r.content)
            return Clip(f"/audio/{f.name}", int(len(r.content) * 8 / 64), False, voice, True)
        except Exception:
            return Clip(None, estimate_ms(text), False, "stub", False)

    async def _synth_kokoro(self, text: str, role: str) -> Clip:
        r = "scammer" if role == "scammer" else "kamla"
        voice = self._voice(r)
        f = self.cache / f"{clip_key(voice, text)}.wav"
        try:
            if f.exists():  # cache first: the hosted image ships pre-rendered clips without the Kokoro engine
                return Clip(f"/audio/{f.name}", wav_ms(f), True, voice, True)
            if self.engine is None:
                return Clip(None, estimate_ms(text), False, "stub", False)
            data = await asyncio.to_thread(self.engine.render, text, voice, KOKORO_SPEED[r])
            self.cache.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
            return Clip(f"/audio/{f.name}", wav_ms(f), False, voice, True)
        except Exception as e:  # never crash a call over audio
            log.error("kokoro synth failed (%s); using the stub for this line", type(e).__name__)
            return Clip(None, estimate_ms(text), False, "stub", False)
