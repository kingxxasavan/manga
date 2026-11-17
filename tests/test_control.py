import asyncio
import json
import sys

import httpx

from anexis import platform
from anexis.tools.base import DANGER, Tool
from anexis.tools.permissions import decide
from tests.fakes import call
from tests.test_server import collect


def danger(name="run_shell"):
    async def handler(args, ctx):
        return "ok"

    return Tool(name, "x", {}, handler, tier=DANGER)


def test_full_control_runs_risky_tools_without_asking(settings):
    assert decide(danger(), {}, settings)[0] == "ask"
    settings.control = "full"
    assert decide(danger(), {}, settings) == ("allow", "full control is on")


def test_one_tool_can_still_be_set_to_ask_under_full_control(settings):
    settings.control = "full"
    settings.permissions = {"run_shell": "ask"}
    assert decide(danger(), {}, settings)[0] == "ask"
    assert decide(danger("run_python"), {}, settings)[0] == "allow"


async def test_full_control_never_sends_a_confirm_to_the_chat(live, settings):
    settings.control = "full"
    _, client = await live(call("run_shell", command="echo hi > made.txt"), "Done.")
    events = await collect(client, "make the file")
    assert "confirm" not in [e["type"] for e in events]
    assert (settings.workspace / "made.txt").exists()


async def test_the_model_is_told_when_it_has_full_control(live, settings):
    settings.control = "full"
    anexis, client = await live("ok")
    await collect(client, "hi")
    assert "full control of this computer" in anexis.router.calls[0]["messages"][0]["content"]


async def test_stop_ends_the_turn_and_whatever_it_started(live, settings):
    settings.control = "full"
    marker = settings.workspace / "pid"
    script = f"import os, time; open(r'{marker}', 'w').write(str(os.getpid())); time.sleep(120)"
    anexis, client = await live(call("run_python", code=script), "never said", "Still here.")
    sid = anexis.memory.ensure_session(None)
    events = []

    async def chat():
        async for event in client.chat("run it", session_id=sid):
            events.append(event)

    task = asyncio.create_task(chat())
    for _ in range(200):
        if marker.exists() and marker.read_text():
            break
        await asyncio.sleep(0.05)
    pid = int(marker.read_text())
    assert (await client.health())["busy"] == [sid]

    async with httpx.AsyncClient(base_url=client.url) as http:
        stopped = (await http.post("/chat/stop", json={"session_id": sid})).json()
    await asyncio.wait_for(task, 10)

    assert stopped == {"stopped": 1}
    assert events[-1]["type"] == "stopped"
    assert not platform.is_running(pid)
    assert (await client.health())["busy"] == []
    # the conversation carries on afterwards
    anexis.router.script[:] = ["Still here."]
    again = await collect(client, "you there", session_id=sid)
    assert again[0]["delta"] == "Still here."


async def test_stop_with_nothing_running_is_fine(live):
    _, client = await live()
    async with httpx.AsyncClient(base_url=client.url) as http:
        assert (await http.post("/chat/stop", json={})).json() == {"stopped": 0}


async def test_every_tool_call_shows_up_in_the_activity_feed(live, settings):
    settings.control = "full"
    _, client = await live(call("run_shell", command=f'"{sys.executable}" -c "print(41 + 1)"'), "Done.")
    seen = []

    async def listen():
        async with httpx.AsyncClient(base_url=client.url, timeout=None) as http, http.stream("GET", "/events") as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    seen.append(json.loads(line))
                    if seen[-1].get("status") in ("done", "failed"):
                        return

    listener = asyncio.create_task(listen())
    await asyncio.sleep(0.2)
    await collect(client, "add them")
    await asyncio.wait_for(listener, 10)
    assert [e["status"] for e in seen] == ["running", "done"]
    assert seen[0]["tool"] == "run_shell" and "42" in seen[1]["preview"]

    async with httpx.AsyncClient(base_url=client.url) as http:
        kept = (await http.get("/activity")).json()
    assert [e["status"] for e in kept] == ["running", "done"]
