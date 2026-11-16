"""Talks to the Greg server over HTTP."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx


class GregClient:
    def __init__(self, url: str, token: str = ""):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _http(self, timeout: float | None = 60.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.url, headers=self.headers, timeout=timeout)

    async def _call(self, method: str, path: str, timeout: float | None = 60.0, **kw):
        async with self._http(timeout) as http:
            resp = await http.request(method, path, **kw)
            resp.raise_for_status()
            return resp

    async def health(self) -> dict:
        return (await self._call("GET", "/health", timeout=10)).json()

    async def chat(self, text: str, session_id: str | None = None, mode: str | None = None) -> AsyncIterator[dict]:
        body = {"text": text, "session_id": session_id, "mode": mode}
        async with self._http(None) as http, http.stream("POST", "/chat", json=body) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    yield json.loads(line)

    async def confirm(self, ask_id: str, allow: bool) -> None:
        await self._call("POST", "/confirm", json={"id": ask_id, "allow": allow})

    async def memories(self, query: str = "", kind: str = "") -> list[dict]:
        return (await self._call("GET", "/memory", params={"q": query, "kind": kind})).json()

    async def remember(self, text: str, kind: str = "fact") -> dict:
        return (await self._call("POST", "/memory", json={"text": text, "kind": kind})).json()

    async def forget(self, memory_id: int) -> dict:
        return (await self._call("DELETE", f"/memory/{memory_id}")).json()

    async def why(self, session_id: str) -> list[dict]:
        return (await self._call("GET", "/why", params={"session_id": session_id})).json()

    async def tools(self) -> dict:
        return (await self._call("GET", "/tools")).json()

    async def about(self) -> dict:
        return (await self._call("GET", "/aboutme")).json()

    async def set_about(self, data: dict) -> dict:
        return (await self._call("POST", "/aboutme", json=data)).json()

    async def doctor(self) -> list[dict]:
        return (await self._call("GET", "/doctor", timeout=120)).json()

    async def transcribe(self, wav: bytes) -> str:
        resp = await self._call("POST", "/voice/transcribe", timeout=300, content=wav)
        return resp.json()["text"]

    async def speak(self, text: str) -> bytes:
        return (await self._call("POST", "/voice/speak", timeout=300, json={"text": text})).content
