"""ADR-004 / G3: local CONNECT proxy that lets the AdaL subprocess reach only ADAL_ALLOWED_HOST (port 443).

Start it, pass `HTTPS_PROXY=http://127.0.0.1:<port>` in AdaL's stripped env, stop it afterwards.
Anything else (other host, other port, non-CONNECT method) gets 403 and no upstream connection.
"""
from __future__ import annotations

import asyncio
from typing import Optional


class AdalProxy:
    def __init__(self, allowed_host: str, allowed_ports: tuple = (443,)):
        self.hosts = {h.strip().lower() for h in allowed_host.split(",") if h.strip()}
        self.ports = set(allowed_ports)
        self.server: Optional[asyncio.AbstractServer] = None
        self.port = 0
        self.denied: list = []

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def _handle(self, r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        try:
            line = (await asyncio.wait_for(r.readline(), 10)).decode("latin-1").strip()
            while (await asyncio.wait_for(r.readline(), 10)) not in (b"\r\n", b"\n", b""):
                pass  # drain headers
            parts = line.split()
            ok, host, port = False, "", 0
            if len(parts) == 3 and parts[0].upper() == "CONNECT" and ":" in parts[1]:
                host, _, p = parts[1].rpartition(":")
                host = host.strip("[]").lower()
                port = int(p) if p.isdigit() else 0
                ok = host in self.hosts and port in self.ports
            if not ok:
                self.denied.append(parts[1] if len(parts) > 1 else line)
                w.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                await w.drain()
                return
            try:
                ur, uw = await asyncio.wait_for(asyncio.open_connection(host, port), 10)
            except Exception:
                w.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                await w.drain()
                return
            w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await w.drain()

            async def pipe(src, dst):
                try:
                    while data := await src.read(65536):
                        dst.write(data)
                        await dst.drain()
                except Exception:
                    pass
                finally:
                    dst.close()

            await asyncio.gather(pipe(r, uw), pipe(ur, w))
        except Exception:
            pass
        finally:
            w.close()
