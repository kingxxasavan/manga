"""Stand ins shared by tests. They script what a model would say; all the code
under test (agent loop, tools, memory, learner) is the real thing."""

from __future__ import annotations

import json

from anexis.llm.provider import ChatResult, ToolCall
from anexis.llm.router import AllProvidersFailed


def say(text):
    return ChatResult(content=text, provider="fake", model="fake-model")


def call(name, **arguments):
    return ChatResult(tool_calls=[ToolCall(f"c_{name}", name, arguments)], provider="fake", model="fake-model")


class FakeRouter:
    """Returns scripted replies in order. A callable entry gets the messages and
    decides what to say, for tests that depend on what the model was shown."""

    def __init__(self, *script, embedder=None, roles=None):
        self.script = list(script)
        self.roles = {k: list(v) for k, v in (roles or {}).items()}
        self.calls = []
        self.embedder = embedder
        self.last_errors = {}

    async def chat(self, role, messages, tools=None, on_text=None):
        self.calls.append({"role": role, "messages": [dict(m) for m in messages], "tools": tools or []})
        queue = self.roles.get(role, self.script)
        if not queue:
            raise AllProvidersFailed("script ran out")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(messages)
        if isinstance(item, (dict, list)):
            item = say(json.dumps(item))
        if isinstance(item, str):
            item = say(item)
        if item.content and on_text:
            on_text(item.content)
        return item

    async def embed(self, texts, kind="passage"):
        if not self.embedder:
            return None
        return "fake:emb", [self.embedder(t) for t in texts]

    async def status(self):
        return [{"name": "fake", "ok": True, "models": {}, "missing": []}]

    async def close(self):
        pass

    def tool_names(self, i=-1):
        return [t["function"]["name"] for t in self.calls[i]["tools"]]

    def system(self, i=-1):
        return self.calls[i]["messages"][0]["content"]
