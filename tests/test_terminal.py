import asyncio
import json

import pytest
import websockets

from anexis.desktop.terminal import open_terminal


async def read_until(term, needle: bytes, seconds: float = 15) -> bytes:
    seen = b""
    async with asyncio.timeout(seconds):
        while needle not in seen:
            chunk = await term.read()
            if not chunk:
                break
            seen += chunk
    return seen


@pytest.mark.parametrize("plain", [False, True])
async def test_a_command_typed_into_the_terminal_runs(tmp_path, plain):
    term = open_terminal(tmp_path, 80, 24, argv=["/bin/sh"], plain=plain)
    try:
        assert term.kind == ("pipes" if plain else "pty")
        term.write(b"echo deck-$((40 + 2))\r")
        assert b"deck-42" in await read_until(term, b"deck-42")
        term.resize(120, 40)
    finally:
        term.close()
    term.close()  # closing twice is fine


async def test_a_real_terminal_knows_its_size(tmp_path):
    term = open_terminal(tmp_path, 91, 33, argv=["/bin/sh"])
    try:
        term.write(b"stty size\r")
        assert b"33 91" in await read_until(term, b"33 91")
    finally:
        term.close()


async def test_read_returns_empty_when_the_shell_ends(tmp_path):
    term = open_terminal(tmp_path, 80, 24, argv=["/bin/sh"])
    term.write(b"exit\r")
    async with asyncio.timeout(15):
        while await term.read():
            pass
    term.close()


async def connect(client, token="", **hello):
    ws = await websockets.connect(client.url.replace("http", "ws") + "/terminal")
    await ws.send(json.dumps({"token": token, **hello}))
    return ws


async def test_the_terminal_socket_runs_a_shell(live, settings):
    settings.token = "s3cret"
    _, client = await live()
    ws = await connect(client, "s3cret", argv=["/bin/sh"], cols=80, rows=24)
    assert json.loads(await ws.recv())["ready"] is True
    await ws.send(b"echo sock-$((1 + 1))\r")
    seen = b""
    async with asyncio.timeout(15):
        while b"sock-2" not in seen:
            seen += await ws.recv()
    await ws.send(json.dumps({"resize": [100, 30]}))
    await ws.send(b"stty size\r")
    async with asyncio.timeout(15):
        while b"30 100" not in seen:
            seen += await ws.recv()
    await ws.close()


async def test_the_terminal_socket_refuses_a_wrong_token(live, settings):
    settings.token = "s3cret"
    _, client = await live()
    ws = await connect(client, "wrong")
    with pytest.raises(websockets.ConnectionClosed) as closed:
        await ws.recv()
    assert closed.value.rcvd.code == 4401


async def test_the_terminal_socket_refuses_another_site(live):
    _, client = await live()
    with pytest.raises(websockets.InvalidStatus):
        await websockets.connect(client.url.replace("http", "ws") + "/terminal", origin="https://evil.example")
