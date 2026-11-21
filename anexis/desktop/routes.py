"""Routes the deck needs beyond chat and memory: the system panel, the file
browser, the terminal, setup, settings and the app itself."""

from __future__ import annotations

import asyncio
import json
import os
import platform as host_platform
import sys
import time
from pathlib import Path

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

import anexis as package
from anexis.cli import setup as wizard
from anexis.config import REPO_ROOT, find_config, read_dotenv
from anexis.core.agent import MODES
from anexis.desktop import files as browser
from anexis.desktop import install as installer
from anexis.desktop import models as model_picker
from anexis.desktop import system
from anexis.desktop.config_file import set_values
from anexis.desktop.terminal import open_terminal
from anexis.platform import IS_WINDOWS, open_with_default_app
from anexis.profile.about import SECTIONS

RESTART_CODE = 75  # the supervisor starts the brain again when it exits with this
KEY_NAMES = {option.env for option in wizard.KEY_OPTIONS}


def _config_path(settings) -> Path:
    return find_config(settings.home) or settings.home / "anexis.toml"


def _jarvis_ready(settings) -> bool:
    """The JARVIS voice can start: its packages are installed and its models downloaded."""
    from anexis.voice.hailmary import engine

    return engine.available(settings)[0]


def _voice_section(settings) -> dict:
    """The [voice] values in anexis.toml now (plain values only), to put back after setup rewrites it."""
    import tomllib

    path = _config_path(settings)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
    return {k: v for k, v in voice.items() if isinstance(v, (bool, int, float, str))}


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

    @app.get("/sessions")
    async def sessions_list():
        return anexis.memory.list_sessions(60)

    @app.delete("/sessions/{session_id}")
    async def session_delete(session_id: str):
        """Clear chat: the conversation is deleted. What was learned stays."""
        return {"deleted": anexis.memory.delete_session(session_id)}

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
            "name": settings.name, "control": settings.control, "autonomy": settings.autonomy, "workspace": str(settings.workspace),
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
        if "autonomy" in body:
            if body["autonomy"] not in ("off", "ask", "act"):
                raise HTTPException(400, 'autonomy must be "off", "ask" or "act"')
            changes["agent.autonomy"] = body["autonomy"]
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
            settings.autonomy = changes.get("agent.autonomy", settings.autonomy)
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

    @app.get("/voice/wake")
    async def wake_state():
        from anexis.voice.hailmary import engine as hailmary
        from anexis.voice.wake import can_wake

        simple = ("simple", settings.wake_word.replace("_", " "))
        if settings.voice_engine == "simple":
            (ok, why), (engine, word) = can_wake(), simple
        else:
            (ok, why), (engine, word) = hailmary.available(settings), ("hailmary", "jarvis")
            if not ok and settings.voice_engine != "hailmary" and can_wake()[0]:
                ok, why, (engine, word) = True, "", simple
        running = getattr(anexis.wake, "name", "simple") if anexis.wake else ""
        return {"on": settings.voice_wake, "state": anexis.wake.state if anexis.wake else "off",
                "available": ok, "why": why, "word": word, "engine": running or engine,
                "attention": settings.voice_attention, "error": getattr(anexis.wake, "error", "") if anexis.wake else ""}

    @app.get("/voice/log")
    async def voice_log(lines: int = 80):
        """The end of voice.log: what JARVIS heard, taken or ignored and why, and what it said."""
        return {"lines": anexis.voice_log.tail(max(1, min(lines, 500))), "path": str(anexis.voice_log.path)}

    @app.post("/voice/approval")
    async def voice_approval(body: dict):
        """A spoken approval answered by click instead (Hail Mary's GUI approvals)."""
        conversation = getattr(anexis.wake, "conversation", None)
        if conversation is None:
            raise HTTPException(404, "JARVIS is not listening")
        conversation.receive({"type": "approval", "id": str(body.get("id", "")), "approved": bool(body.get("approved"))})
        return {"ok": True}

    @app.post("/voice/wake")
    async def wake_switch(body: dict):
        """Turns listening for the wake word on or off, and keeps that choice."""
        on = bool(body.get("on"))
        if on:
            ok, why = anexis.start_wake()
            if not ok:
                raise HTTPException(400, why)
        else:
            await asyncio.to_thread(anexis.stop_wake)
        settings.voice_wake = on
        set_values(_config_path(settings), {"voice.voice_wake": on})
        return await wake_state()

    @app.post("/initiative/now")
    async def initiative_now():
        """Checks in right now instead of waiting, from the App screen."""
        from anexis.core.initiative import Initiative

        return await Initiative(anexis).check_in()

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
                # the JARVIS voice with its models, not just the older simple voice
                "voice": _jarvis_ready(settings),
            },
            "presets": [
                {"name": p.name, "title": p.title, "blurb": p.blurb, "models": p.pull, "voice": p.voice}
                for p in wizard.PRESETS.values()
            ],
            "keys": [
                {"env": o.env, "title": o.title, "label": o.label, "turns_on": o.turns_on, "get_it": o.get_it,
                 "secret": o.secret, "set": bool(env.get(o.env)),
                 # an address is shown whole, a key only by its last four characters
                 "ends": (env.get(o.env, "") if not o.secret else env[o.env][-4:] if len(env.get(o.env, "")) >= 12 else "")}
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
            kept = _voice_section(settings)  # setup rewrites anexis.toml; the voice choices stay
            try:
                backup = wizard.apply_choices(settings.home, body["preset"], name, changes, plan, control)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
            if voice:
                kept["voice_wake"] = True  # picked voice in setup: JARVIS listens from now on
            if kept:
                set_values(_config_path(settings), {f"voice.{k}": v for k, v in kept.items()})
                settings.voice_wake = bool(kept.get("voice_wake", settings.voice_wake))
        elif changes:
            wizard.update_env_file(settings.home / ".env", changes)
        # A preset names models that the provider may have retired since this
        # was written. Check against what it has today, with the keys just saved.
        healed: dict = {}
        if body.get("preset"):
            try:
                healed = await model_picker.heal(settings, {**dict(settings.env), **read_dotenv(settings.home / ".env")})
            except Exception:  # offline, or a bad key: Models in the app can fix it later
                healed = {}
        return {
            "saved": True, "warnings": warnings, "backup": backup.name if backup else "", "healed": healed,
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

    # ---- models ------------------------------------------------------------
    @app.get("/models")
    async def models_state():
        return await model_picker.state(settings)

    @app.post("/models")
    async def models_save(body: dict):
        try:
            backup = model_picker.save(settings, body.get("providers") or [])
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e)) from None
        return {"saved": True, "backup": backup.name if backup else "", "restart": True}

    @app.post("/models/heal")
    async def models_heal():
        """Replaces retired models with what the provider has now."""
        try:
            changed = await model_picker.heal(settings)
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e)) from None
        return {"changed": changed, "restart": bool(changed)}

    @app.post("/models/test")
    async def models_test(body: dict):
        model = str(body.get("model", "")).strip()
        if not model:
            raise HTTPException(400, "Pick a model to try")
        return await model_picker.test(settings, str(body.get("provider", "")), model, str(body.get("role") or "chat"))

    # ---- Claude: how it is signed in and how full the plan is -------------
    @app.get("/claude")
    async def claude_state(fresh: bool = False):
        auth = await anexis.claude.auth()
        usage = await anexis.claude.usage(fresh) if auth["signed_in"] else None
        model, note = (await anexis.claude.pick_model()) if auth["signed_in"] else (settings.claude_model, "")
        resting, why = anexis.claude.available()
        return {
            **auth, "usage": usage, "model": model or "its best model", "note": note,
            "switch_percent": settings.claude_switch_percent, "switch_model": settings.claude_switch_model,
            "resting": "" if resting else why,
        }

    @app.post("/claude")
    async def claude_settings(body: dict):
        changes: dict[str, object] = {}
        if "switch_percent" in body:
            percent = int(body["switch_percent"])
            if not 0 <= percent <= 100:
                raise HTTPException(400, "The percent is between 0 and 100. 0 turns the switch off.")
            changes["coder.claude_switch_percent"] = percent
        for key in ("switch_model", "model"):
            if key in body:
                value = str(body[key]).strip()
                if len(value) > 80 or any(c in value for c in " \n\"'"):
                    raise HTTPException(400, "That is not a model name")
                changes[f"coder.claude_{key}"] = value
        if changes:
            set_values(_config_path(settings), changes)
            settings.claude_switch_percent = changes.get("coder.claude_switch_percent", settings.claude_switch_percent)
            settings.claude_switch_model = changes.get("coder.claude_switch_model", settings.claude_switch_model)
            settings.claude_model = changes.get("coder.claude_model", settings.claude_model)
        return await claude_state()

    # ---- Canvas: signed in through the browser -----------------------------
    @app.get("/canvas")
    async def canvas_state():
        from anexis.tools.builtin import canvas

        if settings.env.get("CANVAS_URL") and settings.env.get("CANVAS_TOKEN"):
            return {"method": "token", "url": settings.env["CANVAS_URL"], "user": ""}
        session = canvas.load_session(settings)
        if session:
            return {"method": "session", "url": session["url"], "user": session.get("user", ""), "saved_at": session.get("saved_at", 0)}
        return {"method": "none", "url": read_dotenv(settings.home / ".env").get("CANVAS_URL", ""), "user": ""}

    @app.post("/canvas/session")
    async def canvas_session_save(body: dict):
        """The desktop window sends the cookies of a Canvas sign in here. They
        are checked against Canvas before anything is kept."""
        from anexis.cli.setup import update_env_file
        from anexis.tools.builtin import canvas

        url = canvas.clean_url(str(body.get("url", "")))
        local_test = os.environ.get("ANEXIS_CANVAS_ALLOW_LOCAL_HTTP") and canvas.urlhost(url) in ("127.0.0.1", "localhost")
        if (not url.startswith("https://") and not local_test) or len(url) > 200:
            raise HTTPException(400, "That is not a Canvas address. It starts with https://")
        host = canvas.urlhost(url)
        cookies = [
            {"name": str(c["name"]), "value": str(c["value"]), "domain": str(c.get("domain") or host), "path": str(c.get("path") or "/")}
            for c in body.get("cookies") or [] if isinstance(c, dict) and c.get("name") and c.get("value") is not None
            # only cookies of the school's Canvas host, never anything else the login touched
            and host.endswith(str(c.get("domain") or host).lstrip("."))
        ]
        if not cookies:
            raise HTTPException(400, "The sign in came back with nothing to keep. Try again.")
        client = canvas.Canvas(url, cookies=cookies, transport=canvas._transport)
        try:
            me = (await client.get("users/self"))[0]
        except canvas.CanvasError as e:
            raise HTTPException(400, f"That sign in did not work: {e}") from None
        finally:
            await client.http.aclose()  # a check only: nothing to save back yet
        user = str(me.get("short_name") or me.get("name") or "") if isinstance(me, dict) else ""
        canvas.write_private(canvas.session_path(settings), {"url": url, "user": user, "saved_at": time.time(), "cookies": cookies})
        update_env_file(settings.home / ".env", {"CANVAS_URL": url})
        return {"saved": True, "user": user, "url": url, "restart": True}

    @app.delete("/canvas/session")
    async def canvas_session_forget():
        from anexis.tools.builtin import canvas

        canvas.session_path(settings).unlink(missing_ok=True)
        return {"forgotten": True, "restart": True}

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
