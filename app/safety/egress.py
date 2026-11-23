"""C1: every outbound HTTP call goes through here; host allowlist, https only."""
from __future__ import annotations

from urllib.parse import urlparse

DEFAULT_HOSTS = {
    "agent-prod.studio.lyzr.ai",
    "app.band.ai",
    "www.finchtech.ai",
    "platform.detectif.ai",
}
TTS_HOSTS = {"elevenlabs": "api.elevenlabs.io"}


class EgressDenied(Exception):
    pass


def allowed_hosts(settings) -> set[str]:
    hosts = set(DEFAULT_HOSTS) | set(settings.egress_allowlist)
    if settings.tts_provider in TTS_HOSTS:
        hosts.add(TTS_HOSTS[settings.tts_provider])
    return hosts


def check(url: str, settings) -> str:
    u = urlparse(url)
    if u.scheme != "https" or (u.hostname or "").lower() not in allowed_hosts(settings):
        raise EgressDenied(f"egress denied: {u.hostname}")
    return url


async def request(method: str, url: str, settings, **kw):
    """Allowlisted httpx call. Imported lazily so offline tests never touch the network layer."""
    import httpx

    check(url, settings)
    kw.setdefault("timeout", 10.0)
    kw.setdefault("follow_redirects", False)
    async with httpx.AsyncClient() as c:
        return await c.request(method, url, **kw)
