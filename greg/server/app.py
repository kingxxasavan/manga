"""The HTTP API the CLI talks to."""

from __future__ import annotations

import asyncio
import hmac
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from greg.core.agent import MODES
from greg.core.doctor import doctor
from greg.memory.store import KINDS
from greg.profile.about import export_profile, import_profile, save_profile_file
from greg.tools.builtin.core import due_soon


def create_app(greg) -> FastAPI:
    settings = greg.settings
    pending: dict[str, asyncio.Future] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await greg.start()
        yield
        await greg.stop()

    def authorized(request: Request) -> None:
        if not settings.token:
            return
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), settings.token.encode()):
            raise HTTPException(401, "Wrong or missing token")

    app = FastAPI(title=settings.name, lifespan=lifespan, dependencies=[Depends(authorized)])
    app.state.greg = greg

    @app.get("/health")
    async def health():
        running = [s for s in greg.mcp.status.values() if s["state"] == "running"]
        starting = [n for n, s in greg.mcp.status.items() if s["state"] == "starting"]
        return {
            "name": settings.name,
            "memories": greg.memory.count(),
            "tools": len(greg.registry),
            "tools_offered": settings.max_tools,
            "tool_servers": len(running),
            "tool_servers_starting": starting,
            "providers": [p.name for p in getattr(greg.router, "providers", [])],
            "due": [f"{i['title']} (due {i['due_at']})" for i in due_soon(greg.memory, days=2)],
        }

    @app.post("/chat")
    async def chat(body: dict):
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "Nothing to say")
        mode = body.get("mode") if body.get("mode") in MODES else None
        queue: asyncio.Queue = asyncio.Queue()

        async def confirm(tool, args, reason) -> bool:
            ask_id = uuid.uuid4().hex[:10]
            future = asyncio.get_running_loop().create_future()
            pending[ask_id] = future
            queue.put_nowait({"type": "confirm", "id": ask_id, "tool": tool.name, "args": args, "reason": reason})
            try:
                return bool(await asyncio.wait_for(future, settings.confirm_timeout))
            except TimeoutError:
                return False  # nobody answered, so the answer is no
            finally:
                pending.pop(ask_id, None)

        async def run() -> None:
            try:
                await greg.agent.run_turn(body.get("session_id"), text, queue.put_nowait, confirm, mode)
            except Exception as e:  # keep the server up whatever a turn does
                queue.put_nowait({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                queue.put_nowait(None)

        async def stream():
            task = asyncio.create_task(run())
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                    yield json.dumps(event) + "\n"
            finally:
                if not task.done():
                    task.cancel()  # the owner hung up, stop working

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/confirm")
    async def confirm_answer(body: dict):
        future = pending.get(str(body.get("id")))
        if future is None or future.done():
            raise HTTPException(404, "Nothing is waiting on that answer")
        future.set_result(bool(body.get("allow")))
        return {"ok": True}

    @app.get("/memory")
    async def memory_list(q: str = "", kind: str = ""):
        if q:
            vec = None
            try:
                vec = await greg.router.embed([q], "query")
            except Exception:
                pass
            rows = greg.memory.search(q, 20, vec[1][0] if vec else None, vec[0] if vec else None)
        else:
            rows = greg.memory.list(kind if kind in KINDS else None, 50)
        return [r.public() for r in rows]

    @app.post("/memory")
    async def memory_add(body: dict):
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "Nothing to remember")
        kind = body.get("kind") if body.get("kind") in KINDS else "fact"
        memory_id = greg.memory.add(kind, text, confidence=0.9, importance=0.7, source="told")
        return greg.memory.get(memory_id).public()

    @app.delete("/memory/{memory_id}")
    async def memory_forget(memory_id: int):
        return {"forgotten": greg.memory.forget(memory_id)}

    @app.get("/why")
    async def why(session_id: str):
        last = greg.memory.last_message(session_id, "assistant")
        ids = last["meta"].get("memories_used", []) if last else []
        return [m.public() for m in (greg.memory.get(i) for i in ids) if m]

    @app.get("/tools")
    async def tools():
        return {
            "servers": greg.mcp.status,
            "tools": [{"name": t.name, "source": t.source, "tier": t.tier, "about": t.description[:100]} for t in greg.registry.all()],
        }

    @app.get("/aboutme")
    async def about_get():
        return export_profile(greg.memory)

    @app.post("/aboutme")
    async def about_set(body: dict):
        report = import_profile(greg.memory, body)
        save_profile_file(settings.home, export_profile(greg.memory))
        return report

    @app.get("/doctor")
    async def doctor_report():
        return await doctor(greg)

    @app.post("/voice/transcribe")
    async def transcribe(request: Request):
        ok, why_not = greg.voice.can_hear()
        if not ok:
            raise HTTPException(503, why_not)
        text = await asyncio.to_thread(greg.voice.transcribe, await request.body())
        return {"text": text}

    @app.post("/voice/speak")
    async def speak(body: dict):
        ok, why_not = greg.voice.can_speak()
        if not ok:
            raise HTTPException(503, why_not)
        return Response(await greg.voice.speak(str(body.get("text", ""))), media_type="audio/wav")

    return app
