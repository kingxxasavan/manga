import json

import httpx
import pytest

from anexis.config import Provider, Settings
from anexis.llm.provider import ProviderError
from anexis.llm.router import AllProvidersFailed, Router


def sse(*chunks):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def delta(**d):
    return {"choices": [{"index": 0, "delta": d}]}


def plain(content="", tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return httpx.Response(200, json={"choices": [{"message": msg}]})


def make_router(tmp_path, handler, providers=None):
    providers = providers or [
        Provider("ollama", "http://ollama/v1", models={"chat": "local", "embed": "emb"}),
        Provider("nvidia", "http://nvidia/v1", "K", "key", {"chat": "big"}, embed_input_type=True),
    ]
    s = Settings(home=tmp_path, providers=providers)
    return Router(s, transport=httpx.MockTransport(handler))


async def test_streamed_text_arrives_in_pieces_and_as_a_whole(tmp_path):
    def handler(req):
        return sse(delta(content="Hel"), delta(content="lo"))

    seen = []
    r = await make_router(tmp_path, handler).chat("chat", [{"role": "user", "content": "hi"}], on_text=seen.append)
    assert (seen, r.content, r.provider, r.model) == (["Hel", "lo"], "Hello", "ollama", "local")


async def test_streamed_tool_call_fragments_are_joined(tmp_path):
    def handler(req):
        return sse(
            delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "get_time", "arguments": ""}}]),
            delta(tool_calls=[{"index": 0, "function": {"arguments": '{"zone":'}}]),
            delta(tool_calls=[{"index": 0, "function": {"arguments": ' "UTC"}'}}]),
        )

    r = await make_router(tmp_path, handler).chat("chat", [], tools=[{"type": "function"}])
    assert [(c.id, c.name, c.arguments) for c in r.tool_calls] == [("c1", "get_time", {"zone": "UTC"})]


async def test_thinking_blocks_are_hidden_from_the_reply(tmp_path):
    def handler(req):
        return sse(delta(content="<thi"), delta(content="nk>secret plan</th"), delta(content="ink>Hi "), delta(content="there"))

    seen = []
    r = await make_router(tmp_path, handler).chat("chat", [], on_text=seen.append)
    assert r.content == "Hi there" and "".join(seen) == "Hi there"


async def test_fails_over_to_the_next_provider_and_rests_the_broken_one(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        if req.url.host == "ollama":
            raise httpx.ConnectError("refused")
        assert req.headers["authorization"] == "Bearer key"
        return sse(delta(content="from nvidia"))

    router = make_router(tmp_path, handler)
    first = await router.chat("chat", [])
    second = await router.chat("chat", [])
    assert first.provider == second.provider == "nvidia"
    assert calls == ["ollama", "nvidia", "nvidia"]  # ollama is skipped while it rests


async def test_an_http_error_also_triggers_failover(tmp_path):
    def handler(req):
        if req.url.host == "ollama":
            return httpx.Response(500, text="model crashed")
        return sse(delta(content="ok"))

    assert (await make_router(tmp_path, handler).chat("chat", [])).provider == "nvidia"


async def test_when_every_provider_fails_the_error_names_each_one(tmp_path):
    def handler(req):
        return httpx.Response(503, text="down")

    with pytest.raises(AllProvidersFailed) as e:
        await make_router(tmp_path, handler).chat("chat", [])
    assert "ollama" in str(e.value) and "nvidia" in str(e.value)


async def test_a_resting_provider_is_still_tried_when_nothing_else_is_left(tmp_path):
    state = {"up": False}

    def handler(req):
        if not state["up"]:
            return httpx.Response(503, text="down")
        return sse(delta(content="back"))

    router = make_router(tmp_path, handler)
    with pytest.raises(AllProvidersFailed):
        await router.chat("chat", [])
    state["up"] = True
    assert (await router.chat("chat", [])).content == "back"


async def test_empty_streamed_reply_with_tools_is_retried_without_streaming(tmp_path):
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body["stream"])
        if body["stream"]:
            return sse(delta(content=""))
        return plain(tool_calls=[{"id": "c9", "function": {"name": "t", "arguments": "{}"}}])

    r = await make_router(tmp_path, handler).chat("chat", [], tools=[{"type": "function"}])
    assert bodies == [True, False] and r.tool_calls[0].name == "t"


async def test_no_failover_after_text_was_already_shown(tmp_path):
    def handler(req):
        if req.url.host == "ollama":
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"par"}}]}\n\ndata: {broken\n\n')
        return sse(delta(content="other"))

    seen = []
    with pytest.raises(ProviderError):
        await make_router(tmp_path, handler).chat("chat", [], on_text=seen.append)
    assert seen == ["par"]


async def test_unknown_role_uses_the_chat_model(tmp_path):
    models = []

    def handler(req):
        models.append(json.loads(req.content)["model"])
        return sse(delta(content="x"))

    await make_router(tmp_path, handler).chat("coder", [])
    assert models == ["local"]


async def test_embed_returns_vectors_tagged_with_provider_and_model(tmp_path):
    def handler(req):
        body = json.loads(req.content)
        assert "input_type" not in body  # only nvidia wants it
        return httpx.Response(200, json={"data": [{"embedding": [1, 0]}, {"embedding": [0, 1]}]})

    tag, vecs = await make_router(tmp_path, handler).embed(["a", "b"])
    assert tag == "ollama:emb" and [list(v) for v in vecs] == [[1.0, 0.0], [0.0, 1.0]]


async def test_embed_is_none_when_no_provider_can_do_it(tmp_path):
    def handler(req):
        return httpx.Response(404, text="no such model")

    assert await make_router(tmp_path, handler).embed(["a"]) is None


async def test_nvidia_embeddings_say_whether_text_is_a_query(tmp_path):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"data": [{"embedding": [1]}]})

    providers = [Provider("nvidia", "http://nvidia/v1", "K", "key", {"embed": "e"}, embed_input_type=True)]
    await make_router(tmp_path, handler, providers).embed(["q"], kind="query")
    assert seen["input_type"] == "query"
