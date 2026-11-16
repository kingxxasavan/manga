"""One client for any server that speaks the OpenAI style chat API.

Ollama and Nvidia both do, so the same code talks to either.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from greg.config import Provider


class ProviderError(Exception):
    """The provider could not answer. `emitted` says if text already reached the user."""

    def __init__(self, message: str, emitted: bool = False):
        super().__init__(message)
        self.emitted = emitted


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""

    def message(self) -> dict:
        """This reply as an assistant message, ready to append to the history."""
        msg: dict = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in self.tool_calls
            ]
        return msg


class ThinkFilter:
    """Drops <think>...</think> blocks from a stream, even when a tag is split
    across chunks. Some local models print their reasoning this way."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.buf = ""
        self.inside = False

    def feed(self, text: str) -> str:
        self.buf += text
        out: list[str] = []
        while True:
            tag = self.CLOSE if self.inside else self.OPEN
            at = self.buf.find(tag)
            if at >= 0:
                if not self.inside:
                    out.append(self.buf[:at])
                self.buf = self.buf[at + len(tag) :]
                self.inside = not self.inside
                continue
            # Hold back a tail that might be the first half of a tag.
            keep = 0
            for n in range(min(len(tag) - 1, len(self.buf)), 0, -1):
                if self.buf.endswith(tag[:n]):
                    keep = n
                    break
            cut = len(self.buf) - keep
            if not self.inside:
                out.append(self.buf[:cut])
            self.buf = self.buf[cut:]
            return "".join(out)

    def flush(self) -> str:
        rest = "" if self.inside else self.buf
        self.buf = ""
        return rest


def _arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, ValueError):
        return {"_unparsed": str(raw)}


def _calls(raw_calls) -> list[ToolCall]:
    calls = []
    for i, c in enumerate(raw_calls or []):
        fn = c.get("function") or {}
        if fn.get("name"):
            calls.append(ToolCall(c.get("id") or f"call_{i}", fn["name"], _arguments(fn.get("arguments"))))
    return calls


class OpenAIProvider:
    def __init__(self, cfg: Provider, timeout: float = 300.0, transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = cfg
        self.name = cfg.name
        headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
        self.http = httpx.AsyncClient(
            base_url=cfg.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_text: Callable[[str], None] | None = None,
        stream: bool = True,
    ) -> ChatResult:
        body: dict = {"model": model, "messages": messages, "stream": stream}
        if tools:
            body["tools"] = tools
        emitted = False
        try:
            if not stream:
                resp = await self.http.post("/chat/completions", json=body)
                _raise_for(resp)
                msg = resp.json()["choices"][0]["message"]
                filt = ThinkFilter()
                text = (filt.feed(msg.get("content") or "") + filt.flush()).strip()
                if text and on_text:
                    on_text(text)
                return ChatResult(text, _calls(msg.get("tool_calls")), self.name, model)

            filt = ThinkFilter()
            parts: list[str] = []
            partial: dict[int, dict] = {}

            def emit(piece: str) -> None:
                nonlocal emitted
                if piece:
                    parts.append(piece)
                    if on_text:
                        emitted = True
                        on_text(piece)

            async with self.http.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    _raise_for(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    choices = json.loads(data).get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    if delta.get("content"):
                        emit(filt.feed(delta["content"]))
                    for tc in delta.get("tool_calls") or []:
                        slot = partial.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                        fn = tc.get("function") or {}
                        slot["id"] = tc.get("id") or slot["id"]
                        slot["name"] = fn.get("name") or slot["name"]
                        args = fn.get("arguments")
                        slot["args"] += args if isinstance(args, str) else json.dumps(args) if args else ""
            emit(filt.flush())
            calls = [
                ToolCall(s["id"] or f"call_{i}", s["name"], _arguments(s["args"]))
                for i, s in sorted(partial.items())
                if s["name"]
            ]
            return ChatResult("".join(parts).strip(), calls, self.name, model)
        except ProviderError as e:
            e.emitted = emitted
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
            raise ProviderError(f"{self.name}: {type(e).__name__}: {e}", emitted) from e

    async def embed(self, model: str, texts: list[str], kind: str = "passage") -> list[list[float]]:
        body: dict = {"model": model, "input": texts}
        if self.cfg.embed_input_type:
            body["input_type"] = kind
        try:
            resp = await self.http.post("/embeddings", json=body)
            _raise_for(resp)
            return [row["embedding"] for row in resp.json()["data"]]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise ProviderError(f"{self.name}: {type(e).__name__}: {e}") from e

    async def models(self) -> list[str]:
        """Model names the provider says it has. Raises ProviderError if unreachable."""
        try:
            resp = await self.http.get("/models", timeout=8.0)
            _raise_for(resp)
            return [m.get("id", "") for m in resp.json().get("data", [])]
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"{self.name}: {type(e).__name__}: {e}") from e


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:300]}")
