import asyncio

from app.safety.adal_proxy import AdalProxy


async def _connect(proxy, target):
    r, w = await asyncio.open_connection("127.0.0.1", proxy.port)
    w.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    await w.drain()
    status = (await r.readline()).decode()
    return r, w, status


def test_proxy_refuses_other_hosts_and_ports_allows_model_host():
    async def go():
        async def echo(r, w):
            w.write(await r.read(5)); await w.drain(); w.close()
        srv = await asyncio.start_server(echo, "127.0.0.1", 0)
        eport = srv.sockets[0].getsockname()[1]
        p = AdalProxy("127.0.0.1", allowed_ports=(eport,))
        await p.start()
        out = {}
        for tgt in ("evil.example:443", f"localhost:{eport}", "127.0.0.1:22"):
            _, w, st = await _connect(p, tgt)
            out[tgt] = st
            w.close()
        r, w, st = await _connect(p, f"127.0.0.1:{eport}")
        await r.readline()
        w.write(b"hello"); await w.drain()
        echoed = await r.read(5)
        w.close(); await p.stop(); srv.close()
        return out, st, echoed, p.denied
    out, st, echoed, denied = asyncio.run(go())
    assert all("403" in v for v in out.values())
    assert "200" in st and echoed == b"hello" and len(denied) == 3


def test_proxy_denies_non_connect_and_empty_allowlist():
    async def go():
        p = AdalProxy("")
        await p.start()
        r, w, st = await _connect(p, "api.example.com:443")
        await p.stop()
        return st
    assert "403" in asyncio.run(go())
