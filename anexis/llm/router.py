"""Picks which provider answers, and moves to the next one when one breaks."""

from __future__ import annotations

import re
import time
from collections.abc import Callable

import httpx
import numpy as np

from anexis.config import Settings
from anexis.llm.provider import ChatResult, OpenAIProvider, ProviderError

NO_TOOLS = re.compile(r"does not support tools|tools? (is|are) not supported|not support (tool|function)", re.I)


class AllProvidersFailed(Exception):
    pass


class Router:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.providers = [
            OpenAIProvider(p, settings.request_timeout, transport) for p in settings.active_providers()
        ]
        self._resting_until: dict[str, float] = {}
        self.toolless: set[tuple[str, str]] = set()
        self.last_errors: dict[str, str] = {}

    async def close(self) -> None:
        for p in self.providers:
            await p.close()

    def _model(self, provider: OpenAIProvider, role: str) -> str | None:
        models = provider.cfg.models
        return models.get(role) or models.get("chat")

    def _order(self) -> list[OpenAIProvider]:
        """Healthy providers first. Resting ones go last instead of being
        dropped, so there is always something to try."""
        now = time.monotonic()
        healthy = [p for p in self.providers if self._resting_until.get(p.name, 0) <= now]
        resting = [p for p in self.providers if p not in healthy]
        return healthy + resting

    def _rest(self, provider: OpenAIProvider, error: Exception) -> None:
        self._resting_until[provider.name] = time.monotonic() + self.settings.provider_cooldown
        self.last_errors[provider.name] = str(error)

    async def chat(
        self,
        role: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> ChatResult:
        errors: list[str] = []
        for provider in self._order():
            model = self._model(provider, role)
            if not model:
                continue
            try:
                result = await self._ask(provider, model, messages, tools, on_text)
                self._resting_until.pop(provider.name, None)
                return result
            except ProviderError as e:
                self._rest(provider, e)
                if e.emitted:
                    # Half a reply is already on screen. Switching now would
                    # show two different answers glued together.
                    raise
                errors.append(str(e) if provider.name in str(e) else f"{provider.name}: {e}")
        raise AllProvidersFailed("No model answered. " + " | ".join(errors or ["no providers configured"]))

    async def _ask(self, provider: OpenAIProvider, model: str, messages, tools, on_text) -> ChatResult:
        if (provider.name, model) in self.toolless:
            tools = None
        try:
            result = await provider.chat(model, messages, tools, on_text, stream=True)
        except ProviderError as e:
            if not tools or e.emitted or not NO_TOOLS.search(str(e)):
                raise
            # This model cannot use tools at all. A plain answer beats no answer,
            # and it is remembered so the failed call is not repeated every turn.
            self.toolless.add((provider.name, model))
            return await provider.chat(model, messages, None, on_text, stream=True)
        if tools and not result.content and not result.tool_calls:
            # Some servers drop tool calls while streaming. Ask again plainly.
            result = await provider.chat(model, messages, tools, on_text, stream=False)
        return result

    async def embed(self, texts: list[str], kind: str = "passage") -> tuple[str, list[np.ndarray]] | None:
        """Vectors for the texts plus a tag naming who made them, or None when
        nobody can embed. Vectors from different models never get compared."""
        for provider in self._order():
            model = provider.cfg.models.get("embed")
            if not model:
                continue
            try:
                raw = await provider.embed(model, texts, kind)
                return f"{provider.name}:{model}", [np.asarray(v, dtype=np.float32) for v in raw]
            except ProviderError as e:
                self.last_errors[provider.name] = str(e)
        return None

    async def status(self) -> list[dict]:
        out = []
        for provider in self.providers:
            entry = {"name": provider.name, "models": provider.cfg.models, "ok": True, "missing": []}
            try:
                have = await provider.models()
                wanted = set(provider.cfg.models.values())
                # Ollama lists "name:tag"; a config without a tag means ":latest".
                known = set(have) | {h.removesuffix(":latest") for h in have}
                entry["missing"] = sorted(m for m in wanted if m not in known)
            except ProviderError as e:
                entry.update(ok=False, error=str(e))
            out.append(entry)
        return out
