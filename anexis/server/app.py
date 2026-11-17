"""The HTTP API the terminal chat and the deck talk to."""

from __future__ import annotations

import asyncio
import hmac
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response, StreamingResponse
from starlette.requests import HTTPConnection
from starlette.staticfiles import StaticFiles

from anexis.config import LOOPBACK
from anexis.core.agent import MODES
from anexis.core.doctor import doctor
from anexis.memory.store import KINDS
from anexis.profile.about import export_profile, import_profile, save_profile_file
from anexis.tools.builtin.core import due_soon

PUBLIC = ("/", "/ui")  # the deck's own files hold no secrets, everything else needs the token
LOCAL_NAMES = LOOPBACK | {"[::1]"}


def _hostname(value: str) -> str:
    """The host part of a Host header or an Origin, without scheme or port."""
    value = value.split("://", 1)[-1].split("/", 1)[0].strip().lower()
    if value.startswith("["):
        return value.split("]", 1)[0] + "]"
    return value.rsplit(":", 1)[0] if ":" in value else value


class LocalOnly:
    """While Anexis listens on this machine only, it answers only requests that
    were really meant for this machine. A web page from some other site cannot
    reach it by pointing a made up name at 127.0.0.1, and cannot post to it
    from the browser either."""

    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and self.settings.host in LOOPBACK:
            headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
            names = [headers.get("host", "")] + ([headers["origin"]] if headers.get("origin") not in (None, "null") else [])
            if any(_hostname(name) not in LOCAL_NAMES for name in names):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4403})
                else:
                    await PlainTextResponse("This Anexis only answers its own machine.", 403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class DeckFiles(StaticFiles):
    """The deck is edited while it runs, so the browser must never keep an old copy."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def token_ok(settings, given: str) -> bool:
    return not settings.token or hmac.compare_digest(given.encode(), settings.token.encode())


def create_app(anexis) -> FastAPI:
    settings = anexis.settings
    pending: dict[str, asyncio.Future] = {}
    turns: dict[str, asyncio.Task] = {}  # session id -> the turn running in it

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await anexis.start()
        yield
        await anexis.stop()

    def authorized(conn: HTTPConnection) -> None:
        # Sockets check the token themselves, a browser cannot set headers on one.
        if conn.scope["type"] == "websocket" or conn.url.path in PUBLIC:
            return
        given = conn.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not token_ok(settings, given):
            raise HTTPException(401, "Wrong or missing token")

    app = FastAPI(title=settings.name, lifespan=lifespan, dependencies=[Depends(authorized)])
    app.state.anexis = anexis
    app.add_middleware(LocalOnly, settings=settings)

    @app.get("/")
    async def home():
        return RedirectResponse("/ui/")

    @app.get("/health")
    async def health():
        running = [s for s in anexis.mcp.status.values() if s["state"] == "running"]
        starting = [n for n, s in anexis.mcp.status.items() if s["state"] == "starting"]
        return {
            "name": settings.name,
            "memories": anexis.memory.count(),
            "tools": len(anexis.registry),
            "tools_offered": settings.max_tools,
            "control": settings.control,
            "busy": sorted(turns),
            "tool_servers": len(running),
            "tool_servers_starting": starting,
            "providers": [p.name for p in getattr(anexis.router, "providers", [])],
            "due": [f"{i['title']} (due {i['due_at']})" for i in due_soon(anexis.memory, days=2)],
        }

    @app.post("/chat")
    async def chat(body: dict):
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "Nothing to say")
        mode = body.get("mode") if body.get("mode") in MODES else None
        queue: asyncio.Queue = asyncio.Queue()
        # The session exists before the turn starts, so stop can name it.
        sid = anexis.memory.ensure_session(body.get("session_id"), mode)

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
                await anexis.agent.run_turn(sid, text, queue.put_nowait, confirm, mode)
            except asyncio.CancelledError:
                queue.put_nowait({"type": "stopped", "session_id": sid})
            except Exception as e:  # keep the server up whatever a turn does
                queue.put_nowait({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                if turns.get(sid) is task:
                    del turns[sid]
                queue.put_nowait(None)

        task = asyncio.create_task(run())
        turns[sid] = task

        async def stream():
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

    @app.post("/chat/stop")
    async def chat_stop(body: dict | None = None):
        """Stops the turn in one conversation, or every running turn. Whatever
        the turn started (a shell command, a coding job) is ended with it."""
        wanted = (body or {}).get("session_id")
        stopping = [task for sid, task in list(turns.items()) if not wanted or sid == wanted]
        for task in stopping:
            task.cancel()
        await asyncio.gather(*stopping, return_exceptions=True)
        return {"stopped": len(stopping)}

    @app.get("/events")
    async def events():
        """Everything Anexis is doing, as it happens. One JSON object per line."""
        async def stream():
            feed = anexis.events.subscribe().__aiter__()
            nxt = None
            yield json.dumps({"type": "hello", "name": settings.name, "control": settings.control}) + "\n"
            try:
                while True:
                    nxt = nxt or asyncio.ensure_future(feed.__anext__())
                    done, _ = await asyncio.wait({nxt}, timeout=15)
                    if not done:
                        yield "\n"  # keeps the line open through quiet minutes
                        continue
                    yield json.dumps(nxt.result()) + "\n"
                    nxt = None
            finally:
                if nxt:
                    nxt.cancel()
                await feed.aclose()

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.get("/activity")
    async def activity():
        return anexis.events.recent(200)

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
                vec = await anexis.router.embed([q], "query")
            except Exception:
                pass
            rows = anexis.memory.search(q, 20, vec[1][0] if vec else None, vec[0] if vec else None)
        else:
            rows = anexis.memory.list(kind if kind in KINDS else None, 50)
        return [r.public() for r in rows]

    @app.post("/memory")
    async def memory_add(body: dict):
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "Nothing to remember")
        kind = body.get("kind") if body.get("kind") in KINDS else "fact"
        memory_id = anexis.memory.add(kind, text, confidence=0.9, importance=0.7, source="told")
        return anexis.memory.get(memory_id).public()

    @app.delete("/memory/{memory_id}")
    async def memory_forget(memory_id: int):
        return {"forgotten": anexis.memory.forget(memory_id)}

    @app.get("/why")
    async def why(session_id: str):
        last = anexis.memory.last_message(session_id, "assistant")
        ids = last["meta"].get("memories_used", []) if last else []
        return [m.public() for m in (anexis.memory.get(i) for i in ids) if m]

    @app.get("/tools")
    async def tools():
        return {
            "servers": anexis.mcp.status,
            "tools": [{"name": t.name, "source": t.source, "tier": t.tier, "about": t.description[:100]} for t in anexis.registry.all()],
        }

    @app.get("/aboutme")
    async def about_get():
        return export_profile(anexis.memory)

    @app.post("/aboutme")
    async def about_set(body: dict):
        report = import_profile(anexis.memory, body)
        save_profile_file(settings.home, export_profile(anexis.memory))
        return report

    @app.get("/doctor")
    async def doctor_report():
        return await doctor(anexis)

    @app.post("/voice/transcribe")
    async def transcribe(request: Request):
        ok, why_not = anexis.voice.can_hear()
        if not ok:
            raise HTTPException(503, why_not)
        text = await asyncio.to_thread(anexis.voice.transcribe, await request.body())
        return {"text": text}

    @app.post("/voice/speak")
    async def speak(body: dict):
        ok, why_not = anexis.voice.can_speak()
        if not ok:
            raise HTTPException(503, why_not)
        return Response(await anexis.voice.speak(str(body.get("text", ""))), media_type="audio/wav")

    from anexis.desktop.routes import attach

    attach(app, anexis)
    if settings.ui_dir.is_dir():
        app.mount("/ui", DeckFiles(directory=settings.ui_dir, html=True), name="ui")
    return app
