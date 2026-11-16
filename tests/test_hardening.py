"""Gaps found in the system check. Each test failed before its fix."""

import json
import time

import httpx
import pytest

from greg.coder.claude import ClaudeRunner, parse_reset
from greg.config import Provider, Settings
from greg.core.agent import Agent
from greg.llm.provider import ChatResult, ToolCall
from greg.llm.router import Router
from greg.tools.base import WRITE, Tool
from greg.tools.builtin import register_builtin
from greg.tools.permissions import decide
from greg.tools.registry import Registry
from tests.fakes import FakeRouter, say


def sse(*chunks):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def router_for(tmp_path, handler):
    s = Settings(home=tmp_path, providers=[Provider("ollama", "http://ollama/v1", models={"chat": "local"})])
    return Router(s, transport=httpx.MockTransport(handler))


# ---- Claude's real limit message -------------------------------------------

REAL_LIMIT = "You've hit your 5-hour limit · resets 9pm (UTC)"


def test_the_real_five_hour_limit_message_is_recognized(settings, memory):
    result = ClaudeRunner(settings, memory)._classify(0, REAL_LIMIT)
    assert result.limited
    envelope = json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": REAL_LIMIT})
    assert ClaudeRunner(settings, memory)._classify(0, envelope).limited


def test_a_reset_time_given_in_utc_is_read_as_utc(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")  # the server is somewhere else
    time.tzset()
    at = parse_reset(REAL_LIMIT)
    monkeypatch.delenv("TZ")
    time.tzset()
    assert 0 < at - time.time() <= 86400
    assert time.gmtime(at).tm_hour == 21 and time.gmtime(at).tm_min == 0


# ---- model quirks ------------------------------------------------------------


async def test_two_tool_calls_that_reuse_index_zero_stay_two_calls(tmp_path):
    def tool(id_, name, args):
        return {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": id_, "function": {"name": name, "arguments": json.dumps(args)}}]}}]}

    def handler(req):
        return sse(tool("a", "time_now", {}), tool("b", "calculate", {"expression": "1+1"}))

    r = await router_for(tmp_path, handler).chat("chat", [], tools=[{"type": "function"}])
    assert [(c.name, c.arguments) for c in r.tool_calls] == [("time_now", {}), ("calculate", {"expression": "1+1"})]


async def test_a_model_that_cannot_use_tools_still_answers_without_them(tmp_path):
    sent = []

    def handler(req):
        body = json.loads(req.content)
        sent.append("tools" in body)
        if "tools" in body:
            return httpx.Response(400, json={"error": {"message": "registry.ollama.ai/library/tiny does not support tools"}})
        return sse({"choices": [{"delta": {"content": "plain answer"}}]})

    r = await router_for(tmp_path, handler).chat("chat", [], tools=[{"type": "function"}])
    assert r.content == "plain answer" and sent == [True, False]


def agent_with(settings, memory, *script):
    settings.workspace.mkdir(parents=True, exist_ok=True)
    settings.learn = False
    registry = Registry()
    register_builtin(registry)
    router = FakeRouter(*script)
    return Agent(settings, memory, router, registry), router


async def test_tool_arguments_that_are_not_json_are_bounced_back_not_run(settings, memory):
    broken = ChatResult(tool_calls=[ToolCall("c1", "write_file", {"_unparsed": '{"path": "a.txt", "content": "x'})])
    agent, router = agent_with(settings, memory, broken, "Sorry, retrying.")
    await agent.run_turn(None, "write the file")
    assert "not valid JSON" in router.calls[1]["messages"][-1]["content"]
    assert list(settings.workspace.iterdir()) == []


async def test_an_empty_reply_from_the_model_is_never_shown_as_silence(settings, memory):
    agent, _ = agent_with(settings, memory, say(""))
    events = []
    result = await agent.run_turn(None, "hello", emit=events.append)
    assert "empty reply" in result["text"]
    assert any(e["type"] == "text" for e in events)


async def test_old_messages_are_dropped_to_fit_the_character_budget(settings, memory):
    settings.history_chars = 500
    agent, router = agent_with(settings, memory, "ok")
    sid = memory.ensure_session(None)
    for i in range(20):
        memory.add_message(sid, "user" if i % 2 == 0 else "assistant", f"message {i} " + "x" * 100)
    await agent.run_turn(sid, "newest question")
    sent = [m["content"] for m in router.calls[0]["messages"][1:]]
    assert sent[-1] == "newest question"
    assert sum(len(c) for c in sent[:-1]) <= 500 and len(sent) < 21
    assert sent[-2].startswith("message 19")  # the most recent ones are the ones kept


# ---- paths hidden in odd arguments -------------------------------------------


async def noop(args, ctx):
    return "ok"


def file_tool():
    return Tool("convert_to_markdown", "convert a file", {}, noop, tier=WRITE)


@pytest.mark.parametrize("args", [
    {"uri": "file:///etc/passwd"},
    {"uri": "file://localhost/etc/passwd"},
    {"anything": "/etc/passwd"},
    {"anything": "~/.ssh/id_rsa"},
    {"names": ["notes.txt", "/root/.greg/.env"]},
    {"options": {"input": "/etc/shadow"}},
])
def test_a_path_outside_the_workspace_is_caught_under_any_argument_name(settings, args):
    assert decide(file_tool(), args, settings)[0] == "ask"


@pytest.mark.parametrize("args", [
    {"uri": "https://example.com/paper.pdf"},
    {"content": "/* a comment */ and some text with / slashes"},
    {"content": "~ roughly 5 dollars"},
    {"pattern": "/"},
    {"query": "what is a/b testing"},
])
def test_ordinary_text_is_not_mistaken_for_a_path(settings, args):
    assert decide(file_tool(), args, settings)[0] == "allow"


def test_a_file_uri_inside_the_workspace_is_fine(settings):
    inside = f"file://{settings.workspace}/notes/a.pdf"
    assert decide(file_tool(), {"uri": inside}, settings)[0] == "allow"
