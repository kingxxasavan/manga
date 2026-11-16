import httpx
import pytest

from greg.cli.client import GregClient
from tests.fakes import call


async def collect(client, text, answer=None, **kw):
    events = []
    async for event in client.chat(text, **kw):
        events.append(event)
        if event["type"] == "confirm" and answer is not None:
            await client.confirm(event["id"], answer)
    return events


async def test_chat_streams_text_then_done(live):
    _, client = await live("Hello there")
    events = await collect(client, "hi")
    assert [e["type"] for e in events] == ["text", "done"]
    assert events[0]["delta"] == "Hello there" and events[1]["session_id"]


async def test_health_reports_name_memory_and_tools(live):
    greg, client = await live()
    greg.memory.add("fact", "Likes tea")
    health = await client.health()
    assert health["name"] == "Greg" and health["memories"] == 1 and health["tools"] > 10


async def test_a_wrong_or_missing_token_is_rejected(live, settings):
    settings.token = "s3cret"
    _, client = await live("hi")
    assert (await client.health())["name"] == "Greg"
    for bad in ("", "wrong"):
        stranger = GregClient(client.url, bad)
        with pytest.raises(httpx.HTTPStatusError) as e:
            await stranger.health()
        assert e.value.response.status_code == 401


async def test_dangerous_tool_waits_for_a_yes_from_the_cli(live, settings):
    _, client = await live(call("run_shell", command="touch approved.txt"), "Done.")
    events = await collect(client, "run the shell command", answer=True)
    confirm = next(e for e in events if e["type"] == "confirm")
    assert confirm["tool"] == "run_shell" and confirm["args"] == {"command": "touch approved.txt"}
    assert (settings.workspace / "approved.txt").exists()


async def test_dangerous_tool_does_not_run_on_a_no(live, settings):
    _, client = await live(call("run_shell", command="touch denied.txt"), "Okay.")
    await collect(client, "run the shell command", answer=False)
    assert not (settings.workspace / "denied.txt").exists()


async def test_an_unanswered_question_times_out_as_a_no(live, settings):
    settings.confirm_timeout = 0.2
    _, client = await live(call("run_shell", command="touch late.txt"), "Timed out.")
    events = await collect(client, "run the shell command")  # never answers
    assert events[-1]["type"] == "done" and not (settings.workspace / "late.txt").exists()


async def test_memory_can_be_added_searched_explained_and_forgotten(live):
    _, client = await live("Thursday.")
    saved = await client.remember("Chemistry lab is on Thursday")
    assert [m["text"] for m in await client.memories("chemistry")] == ["Chemistry lab is on Thursday"]
    done = (await collect(client, "when is chemistry lab"))[-1]
    assert [m["id"] for m in await client.why(done["session_id"])] == [saved["id"]]
    assert (await client.forget(saved["id"]))["forgotten"] is True
    assert await client.memories("chemistry") == []


async def test_about_me_can_be_sent_and_read_back(live):
    greg, client = await live()
    report = await client.set_about({"name": "Sam", "classes": ["Chem 101"]})
    assert report["added"] == 2
    assert await client.about() == {"name": "Sam", "classes": ["Chem 101"]}
    assert (greg.settings.home / "about_me.yaml").exists()


async def test_tools_endpoint_lists_built_ins(live):
    _, client = await live()
    tools = await client.tools()
    assert "code_task" in [t["name"] for t in tools["tools"]]


async def test_doctor_reports_each_part(live):
    _, client = await live()
    parts = {c["part"]: c for c in await client.doctor()}
    assert parts["memory"]["ok"] and "model: fake" in parts
    assert "about me" in parts and not parts["about me"]["ok"]  # nothing filled in yet


async def test_mode_is_remembered_between_messages(live):
    greg, client = await live("ok", "ok")
    first = (await collect(client, "hi", mode="work"))[-1]
    await collect(client, "again", session_id=first["session_id"])
    assert greg.memory.session(first["session_id"])["mode"] == "work"


async def test_one_broken_turn_does_not_take_the_server_down(live):
    _, client = await live()  # no scripted replies: the model call fails
    events = await collect(client, "hi")
    assert events[-1]["type"] == "error"
    assert (await client.health())["name"] == "Greg"


async def test_missing_voice_is_marked_optional_and_does_not_fail_the_checkup(live, settings):
    import io

    from rich.console import Console

    from greg.cli.repl import show_doctor

    settings.piper_bin = "/nonexistent/piper"
    greg, client = await live()
    greg.memory.add("fact", "Name: Sam", pinned=True, source="about_me")
    checks = await client.doctor()
    voice_out = next(c for c in checks if c["part"] == "voice out")
    assert not voice_out["ok"] and voice_out["optional"]
    out = io.StringIO()
    required = [c for c in checks if c["part"] in ("config", "memory", "about me", "model: fake", "voice out")]
    assert show_doctor(Console(file=out, width=200), required) is True
    assert "install.sh" in out.getvalue()  # the fix it names


async def test_the_checkup_says_so_when_no_model_is_set_up(live, settings):
    settings.providers = []
    _, client = await live()
    config = next(c for c in await client.doctor() if c["part"] == "config")
    assert not config["ok"] and "model" in config["detail"].lower()
