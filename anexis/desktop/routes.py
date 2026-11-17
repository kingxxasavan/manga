"""Routes the deck needs beyond chat and memory: the system panel, the file
browser, the terminal, setup, settings and the app itself."""

from __future__ import annotations

import asyncio
import json
import os
import platform as host_platform
import sys
from importlib.util import find_spec
from pathlib import Path

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

import anexis as package
from anexis.cli import setup as wizard
from anexis.config import REPO_ROOT, find_config, read_dotenv
from anexis.core.agent import MODES
from anexis.desktop import files as browser
from anexis.desktop import install as installer
from anexis.desktop import system
from anexis.desktop.config_file import set_values
from anexis.desktop.terminal import open_terminal
from anexis.platform import IS_WINDOWS, open_with_default_app
from anexis.profile.about import SECTIONS

RESTART_CODE = 75  # the supervisor starts the brain again when it exits with this
KEY_NAMES = {option.env for option in wizard.KEY_OPTIONS}


def _config_path(settings) -> Path:
    return find_config(settings.home) or settings.home / "anexis.toml"


def attach(app, anexis) -> None:
    from anexis.server.app import token_ok

    settings = anexis.settings

    # ---- the machine -------------------------------------------------------
    @app.get("/system/stats")
    async def system_stats():
        return await asyncio.to_thread(system.stats)

    # ---- files -------------------------------------------------------------
    @app.get("/files")
    async def files_list(path: str = ""):
        try:
            return await asyncio.to_thread(browser.list_folder, path, settings.workspace)
        except (FileNotFoundError, NotADirectoryError) as e:
            raise HTTPException(404, str(e)) from None

    @app.get("/files/roots")
    async def files_roots():
        return browser.roots(settings.workspace, REPO_ROOT)

    @app.post("/files/open")
    async def files_open(body: dict):
        path = Path(str(body.get("path", ""))).expanduser()
        if not path.exists():
            raise HTTPException(404, f"There is nothing at {path}")
        try:
            await asyncio.to_thread(open_with_default_app, str(path))
        except OSError as e:
            raise HTTPException(500, f"Could not open it: {e}") from None
        return {"opened": str(path)}

    # ---- conversations -----------------------------------------------------
    @app.post("/sessions/new")
    async def session_new(body: dict | None = None):
        mode = (body or {}).get("mode")
        return {"session_id": anexis.memory.ensure_session(None, mode if mode in MODES else None)}

    @app.get("/sessions/{session_id}/messages")
    async def session_messages(session_id: str):
        session = anexis.memory.session(session_id)
        if session is None:
            raise HTTPException(404, "No conversation with that id")
        return {"mode": session["mode"], "messages": anexis.memory.history(session_id, 200)}

    @app.get("/aboutme/sections")
    async def about_sections():
        return [{"key": s.key, "label": s.label, "question": s.question, "many": s.many} for s in SECTIONS]

    # ---- settings ----------------------------------------------------------
    @app.get("/settings")
    async def settings_get():
        return {
            "name": settings.name, "control": settings.control, "workspace": str(settings.workspace),
            "home": str(settings.home), "config": str(_config_path(settings)),
            "providers": [{"name": p.name, "active": p.active, "models": p.models} for p in settings.providers],
        }

    @app.post("/settings")
    async def settings_set(body: dict):
        changes: dict[str, object] = {}
        if "control" in body:
            if body["control"] not in ("ask", "full"):
                raise HTTPException(400, 'control must be "ask" or "full"')
            changes["agent.control"] = body["control"]
        if "name" in body:
            name = str(body["name"]).strip()[:40]
            if not name:
                raise HTTPException(400, "The name cannot be empty")
            changes["name"] = name
        if changes:
            try:
                set_values(_config_path(settings), changes)
            except (OSError, ValueError) as e:
                raise HTTPException(500, f"Could not save the settings: {e}") from None
            # Both take effect right now, no restart needed.
            settings.control = changes.get("agent.control", settings.control)
            settings.name = changes.get("name", settings.name)
            anexis.events.publish({"type": "settings", "control": settings.control, "name": settings.name})
        return await settings_get()

    # ---- the app itself ----------------------------------------------------
    @app.get("/app")
    async def app_info():
        return {
            "version": package.__version__,
            "folder": str(REPO_ROOT),
            "installed": bool(os.environ.get("ANEXIS_RUNTIME")),
            "supervised": bool(os.environ.get("ANEXIS_SUPERVISED")),
            "platform": host_platform.system(),
            "python": sys.version.split()[0],
            "frame": os.environ.get("ANEXIS_FRAME", ""),
        }

    @app.post("/app/restart")
    async def app_restart():
        """Restarts the brain so new keys, settings or code take hold."""
        server = getattr(app.state, "server", None)
        if not os.environ.get("ANEXIS_SUPERVISED") or server is None:
            return {"restarting": False, "why": "Nothing is here to start it again. Run `anexis stop`, then open it again."}
        app.state.exit_code = RESTART_CODE
        asyncio.get_running_loop().call_later(0.3, lambda: setattr(server, "should_exit", True))
        return {"restarting": True}

    @app.post("/app/notice")
    async def app_notice(body: dict):
        """The supervisor reports here, so the deck can show what it is doing."""
        if body.get("type") not in ("brain_error", "brain_restarting"):
            raise HTTPException(400, "Not a notice Anexis knows")
        anexis.events.publish({"type": body["type"], "files": body.get("files", []), "errors": body.get("errors", [])})
        return {"ok": True}

    # ---- setup -------------------------------------------------------------
    @app.get("/setup")
    async def setup_state():
        machine = await asyncio.to_thread(wizard.detect_machine)
        saved = read_dotenv(settings.home / ".env")
        env = {**dict(settings.env), **saved}
        plan = settings.home / "setup-plan"
        return {
            "done": (settings.home / "anexis.toml").is_file(),
            "name": settings.name,
            "control": settings.control,
            "preset": wizard.read_plan(plan).get("PRESET", "") if plan.is_file() else "",
            "best": wizard.recommend(machine, env),
            "windows": IS_WINDOWS,
            "machine": {
                "summary": machine.describe(), "vram_gb": round(machine.vram_gb, 1), "ram_gb": round(machine.ram_gb, 1),
                "ollama": machine.has_ollama, "node": machine.node_major, "claude": machine.has_claude,
                "voice": find_spec("faster_whisper") is not None,
            },
            "presets": [
                {"name": p.name, "title": p.title, "blurb": p.blurb, "models": p.pull, "voice": p.voice}
                for p in wizard.PRESETS.values()
            ],
            "keys": [
                {"env": o.env, "title": o.title, "label": o.label, "turns_on": o.turns_on, "get_it": o.get_it,
                 "set": bool(env.get(o.env)), "ends": env[o.env][-4:] if len(env.get(o.env, "")) >= 12 else ""}
                for o in wizard.KEY_OPTIONS
            ],
        }

    @app.post("/setup")
    async def setup_apply(body: dict):
        """Saves the choices and the keys. Only key names Anexis knows are
        written, so this can never be used to change other settings in .env."""
        keys = body.get("keys") or {}
        unknown = sorted(set(keys) - KEY_NAMES)
        if unknown:
            raise HTTPException(400, f"Not a key Anexis knows: {', '.join(unknown)}")
        changes, warnings = {}, {}
        for name, value in keys.items():
            value = str(value).strip()
            if value == "-":
                changes[name] = ""
            elif value:
                if "\n" in value or "\r" in value:
                    raise HTTPException(400, f"{name} has a line break in it, which a key never has")
                changes[name] = value
                if warning := wizard.key_warning(name, value):
                    warnings[name] = warning
        backup = None
        if body.get("preset"):
            name = str(body.get("name") or settings.name).strip()[:40] or "Anexis"
            control = body.get("control") or "full"
            voice = bool(body.get("voice"))
            plan = {"PRESET": body["preset"], "INSTALL_VOICE": str(int(voice))}
            try:
                backup = wizard.apply_choices(settings.home, body["preset"], name, changes, plan, control)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
        elif changes:
            wizard.update_env_file(settings.home / ".env", changes)
        return {
            "saved": True, "warnings": warnings, "backup": backup.name if backup else "",
            "keys_changed": sorted(changes), "restart": bool(body.get("preset") or changes),
        }

    @app.post("/setup/install")
    async def setup_install(body: dict):
        """Downloads what the owner picked. One JSON object per line as it goes."""
        queue: asyncio.Queue = asyncio.Queue()

        async def work() -> None:
            try:
                await installer.install(settings, body, queue.put_nowait)
            except Exception as e:
                queue.put_nowait({"state": "finished", "ok": False, "message": f"{type(e).__name__}: {e}"})
            finally:
                queue.put_nowait(None)

        async def stream():
            task = asyncio.create_task(work())
            try:
                while (event := await queue.get()) is not None:
                    yield json.dumps(event) + "\n"
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    # ---- terminal ----------------------------------------------------------
    @app.websocket("/terminal")
    async def terminal(ws: WebSocket):
        """A shell on this machine. The first message must be the token, since
        a browser cannot put it in a header and a URL would leak it into logs."""
        await ws.accept()
        term = None
        try:
            hello = json.loads(await asyncio.wait_for(ws.receive_text(), 10))
            if not token_ok(settings, str(hello.get("token", ""))):
                await ws.close(4401, "Wrong or missing token")
                return
            cwd = hello.get("cwd") or str(settings.workspace)
            settings.workspace.mkdir(parents=True, exist_ok=True)
            term = open_terminal(cwd, int(hello.get("cols") or 100), int(hello.get("rows") or 30),
                                 argv=hello.get("argv") if isinstance(hello.get("argv"), list) else None)
            await ws.send_text(json.dumps({"ready": True, "kind": term.kind}))

            async def pump() -> None:
                while data := await term.read():
                    await ws.send_bytes(data)
                await ws.close(1000, "The shell ended")

            pumping = asyncio.create_task(pump())
            try:
                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message.get("bytes") is not None:
                        term.write(message["bytes"])
                    elif message.get("text"):
                        note = json.loads(message["text"])
                        if "resize" in note:
                            cols, rows = note["resize"]
                            term.resize(int(cols), int(rows))
                        elif "input" in note:
                            term.write(str(note["input"]).encode())
            finally:
                pumping.cancel()
        except (TimeoutError, WebSocketDisconnect, ValueError, RuntimeError):
            pass
        finally:
            if term:
                term.close()
