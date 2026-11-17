"""Control of the desktop: apps, windows, clipboard, screen, keyboard, mouse,
running programs. This is what lets the desktop app drive the PC.

The screen, keyboard and mouse tools need the `desktop` extra (pyautogui and
friends), which the Windows installer ships. They are only offered to the
model when those packages are there, so a headless server is not cluttered
with tools that cannot work.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import shutil
import subprocess
import time
from importlib.util import find_spec
from pathlib import Path

import psutil

from anexis.platform import IS_WINDOWS, open_with_default_app, spawn_kwargs
from anexis.tools.base import DANGER, SAFE, Tool, ToolContext, params, text

NEEDS = ("Error: screen, keyboard and mouse control is not installed here. The Windows app ships it. "
         "From source run: uv sync --extra desktop")
MAX_IMAGE_WIDTH = 1600


class Unavailable(Exception):
    """Desktop control cannot work on this machine right now. The text says why."""


class Backend:
    """The real desktop. Everything is imported when first used, because the
    packages need a screen to even load."""

    def _gui(self):
        try:
            import pyautogui
        except ImportError:
            raise Unavailable(NEEDS) from None
        except Exception as e:  # no display: a server reached over SSH, or a locked session
            raise Unavailable(f"Error: there is no screen to control here ({type(e).__name__}: {e})") from None
        pyautogui.PAUSE = 0.05
        return pyautogui

    def _clip(self):
        try:
            import pyperclip
        except ImportError:
            raise Unavailable(NEEDS) from None
        return pyperclip

    def _windows(self):
        if not IS_WINDOWS:
            raise Unavailable("Error: listing and switching windows works in the Windows app only.")
        try:
            import pygetwindow
        except ImportError:
            raise Unavailable(NEEDS) from None
        return pygetwindow

    def screen_size(self) -> tuple[int, int]:
        size = self._gui().size()
        return int(size[0]), int(size[1])

    def screenshot(self, path: Path) -> tuple[int, int]:
        image = self._gui().screenshot()
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return image.size

    def type_text(self, value: str) -> None:
        gui = self._gui()
        if value.isascii() and value.isprintable() and len(value) <= 200:
            gui.write(value, interval=0.01)
            return
        # Anything longer or not plain English goes through the clipboard,
        # which is fast and gets every character right. The old clipboard is put back.
        clip = self._clip()
        try:
            before = clip.paste()
        except Exception:
            before = None
        clip.copy(value)
        gui.hotkey("ctrl", "v")
        time.sleep(0.15)
        if before is not None:
            clip.copy(before)

    def press(self, keys: list[str]) -> None:
        gui = self._gui()
        unknown = [k for k in keys if k not in gui.KEYBOARD_KEYS]
        if unknown:
            raise Unavailable(f"Error: there is no key named {unknown[0]}. Examples: enter, tab, esc, ctrl, alt, shift, win, f5, up, a")
        gui.hotkey(*keys) if len(keys) > 1 else gui.press(keys[0])

    def move(self, x: int, y: int) -> None:
        self._gui().moveTo(x, y, duration=0.15)

    def click(self, x: int | None, y: int | None, button: str, clicks: int) -> None:
        self._gui().click(x=x, y=y, button=button, clicks=clicks, interval=0.08)

    def scroll(self, amount: int) -> None:
        self._gui().scroll(amount)

    def clipboard_read(self) -> str:
        return self._clip().paste()

    def clipboard_write(self, value: str) -> None:
        self._clip().copy(value)

    def windows(self) -> list[dict]:
        gw = self._windows()
        active = gw.getActiveWindow()
        return [
            {"title": w.title, "active": bool(active and w._hWnd == active._hWnd), "minimized": bool(w.isMinimized)}
            for w in gw.getAllWindows() if w.title.strip()
        ]

    def _find(self, title: str):
        gw = self._windows()
        wanted = title.lower()
        matches = [w for w in gw.getAllWindows() if w.title.strip() and wanted in w.title.lower()]
        if not matches:
            raise Unavailable(f"Error: no open window has {title!r} in its title. Call list_windows to see what is open.")
        return sorted(matches, key=lambda w: len(w.title))[0]

    def focus(self, title: str) -> str:
        window = self._find(title)
        if window.isMinimized:
            window.restore()
        window.activate()
        return window.title

    def close(self, title: str) -> str:
        window = self._find(title)
        window.close()
        return window.title


_backend: Backend = Backend()


def set_backend(backend) -> None:
    """Tests swap in a stand in for the real desktop."""
    global _backend
    _backend = backend


async def _do(function, *args):
    """Runs one desktop action off the event loop and turns "cannot work here"
    into the plain error text every tool returns."""
    try:
        return await asyncio.to_thread(function, *args), None
    except Unavailable as e:
        return None, str(e)
    except Exception as e:
        if type(e).__name__ == "FailSafeException":
            return None, "Error: stopped, because the mouse was pushed into a corner of the screen. That is the emergency brake."
        return None, f"Error: {type(e).__name__}: {e}"


def _number(args: dict, key: str) -> int | None:
    try:
        return int(float(args[key])) if args.get(key) not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ---- apps, files, links --------------------------------------------------

async def open_path(args: dict, ctx: ToolContext) -> str:
    target = str(args.get("target", "")).strip()
    if not target:
        return "Error: say what to open: a file, a folder, a link or an app name"
    extra = [str(a) for a in args.get("args") or []] if isinstance(args.get("args"), list) else []
    is_link = bool(re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I)) or target.lower().startswith("mailto:")
    path = Path(target).expanduser()
    try:
        if is_link:
            await asyncio.to_thread(open_with_default_app, target)
            return f"Opened {target}"
        if path.exists() and not extra:
            await asyncio.to_thread(open_with_default_app, str(path))
            return f"Opened {path}"
        if IS_WINDOWS:
            # ShellExecute finds apps the way the Run box does (notepad, chrome, a full path).
            # The name and the arguments are passed apart, never as one shell line.
            await asyncio.to_thread(os.startfile, target, "open", subprocess.list2cmdline(extra))
            return f"Started {target}"
        program = shutil.which(target) or (str(path) if path.exists() else None)
        if not program:
            return f"Error: nothing named {target} was found. Give a full path, a link, or the name of an installed program."
        subprocess.Popen([program, *extra], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **spawn_kwargs())
        return f"Started {program}"
    except OSError as e:
        return f"Error: could not open {target}: {e}"


# ---- running programs ----------------------------------------------------

async def list_processes(args: dict, ctx: ToolContext) -> str:
    wanted = str(args.get("name", "")).lower()
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        name = proc.info["name"] or ""
        if wanted and wanted not in name.lower():
            continue
        memory = proc.info["memory_info"].rss if proc.info["memory_info"] else 0
        rows.append((memory, proc.info["pid"], name))
    if not rows:
        return f"No running program has {wanted!r} in its name." if wanted else "No programs found."
    rows.sort(reverse=True)
    lines = [f"{pid:>7}  {memory / 1024**2:>8.0f} MB  {name}" for memory, pid, name in rows[:40]]
    more = f"\n... and {len(rows) - 40} more, pass name to narrow it down" if len(rows) > 40 else ""
    return "    pid     memory  name\n" + "\n".join(lines) + more


def _protected() -> set[int]:
    """Anexis itself and what keeps it running. Ending these would end the
    conversation the request came from."""
    out, proc = set(), psutil.Process()
    while proc is not None and len(out) < 4:
        out.add(proc.pid)
        proc = proc.parent()
        if proc is not None and not any(word in " ".join(proc.cmdline()).lower() for word in ("anexis", "electron")):
            break
    return out


async def end_process(args: dict, ctx: ToolContext) -> str:
    pid, name = _number(args, "pid"), str(args.get("name", "")).strip().lower()
    if pid is None and not name:
        return "Error: give a pid from list_processes, or an exact program name"
    targets = []
    for proc in psutil.process_iter(["pid", "name"]):
        if (pid is not None and proc.info["pid"] == pid) or (name and (proc.info["name"] or "").lower() in (name, f"{name}.exe")):
            targets.append(proc)
    if not targets:
        return "Error: no running program matches that. Call list_processes to see what is running."
    protected = _protected()
    ended, kept = [], []
    for proc in targets:
        if proc.pid in protected:
            kept.append(f"{proc.info['name']} ({proc.pid}) is Anexis itself")
            continue
        try:
            proc.terminate()
            ended.append(proc)
        except psutil.Error as e:
            kept.append(f"{proc.info['name']} ({proc.pid}): {type(e).__name__}")
    _, alive = await asyncio.to_thread(psutil.wait_procs, ended, 3)
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            pass
    report = f"Ended {len(ended)}: " + ", ".join(f"{p.info['name']} ({p.pid})" for p in ended) if ended else "Ended nothing."
    return report + (f"\nLeft alone: {'; '.join(kept)}" if kept else "") if ended or not kept else f"Error: {'; '.join(kept)}"


# ---- windows -------------------------------------------------------------

async def list_windows(args: dict, ctx: ToolContext) -> str:
    rows, error = await _do(_backend.windows)
    if error:
        return error
    if not rows:
        return "No windows are open."
    return "\n".join(f"{'*' if w['active'] else ' '} {w['title']}{'  (minimized)' if w.get('minimized') else ''}" for w in rows) + "\n(* is the one in front)"


async def focus_window(args: dict, ctx: ToolContext) -> str:
    title = str(args.get("title", "")).strip()
    if not title:
        return "Error: give part of the window title"
    found, error = await _do(_backend.focus, title)
    return error or f"Brought to the front: {found}"


async def close_window(args: dict, ctx: ToolContext) -> str:
    title = str(args.get("title", "")).strip()
    if not title:
        return "Error: give part of the window title"
    found, error = await _do(_backend.close, title)
    return error or f"Asked to close: {found}"


# ---- clipboard -----------------------------------------------------------

async def clipboard_read(args: dict, ctx: ToolContext) -> str:
    value, error = await _do(_backend.clipboard_read)
    return error or (value if value else "The clipboard is empty.")


async def clipboard_write(args: dict, ctx: ToolContext) -> str:
    value = str(args.get("text", ""))
    _, error = await _do(_backend.clipboard_write, value)
    return error or f"Copied {len(value)} characters to the clipboard."


# ---- screen --------------------------------------------------------------

def _shot_path(ctx: ToolContext) -> Path:
    return ctx.settings.workspace / "screenshots" / f"screen-{time.strftime('%Y%m%d-%H%M%S')}.png"


async def screenshot(args: dict, ctx: ToolContext) -> str:
    path = _shot_path(ctx)
    size, error = await _do(_backend.screenshot, path)
    if error:
        return error
    ctx.emit({"type": "status", "text": f"Screenshot saved: {path}"})
    return f"Saved a {size[0]}x{size[1]} screenshot to {path}. Use see_screen to find out what is on it."


def _for_model(path: Path) -> tuple[str, float]:
    """The picture as a data link, shrunk when it is very wide. Returns the
    link and how much it was shrunk by."""
    from PIL import Image

    scale = 1.0
    with Image.open(path) as image:
        if image.width > MAX_IMAGE_WIDTH:
            scale = MAX_IMAGE_WIDTH / image.width
            small = path.with_name(path.stem + "-small.png")
            image.resize((MAX_IMAGE_WIDTH, round(image.height * scale))).save(small)
            path = small
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode(), scale


async def see_screen(args: dict, ctx: ToolContext) -> str:
    question = str(args.get("question", "")).strip() or "Describe what is on the screen."
    if not any(p.models.get("vision") for p in ctx.settings.active_providers()):
        return ("Error: no model that can see is set up. In anexis.toml, under a provider's [providers.models], "
                'add a line like  vision = "<a vision model that provider offers>"  and restart. '
                "Until then use list_windows, the clipboard and the keyboard instead of looking.")
    path = _shot_path(ctx)
    size, error = await _do(_backend.screenshot, path)
    if error:
        return error
    try:
        link, scale = await asyncio.to_thread(_for_model, path)
    except ImportError:
        return NEEDS
    shown = (round(size[0] * scale), round(size[1] * scale))
    prompt = (f"This is a screenshot of the owner's screen, {shown[0]} by {shown[1]} pixels. {question}\n"
              "Be exact and short. When asked where something is, give its center as x,y in pixels of this image.")
    reply = await ctx.router.chat("vision", [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": link}}]}])
    note = "" if scale == 1.0 else (f"\n(The picture was shrunk. Multiply any x,y by {1 / scale:.3f} "
                                    f"to get real screen positions. The real screen is {size[0]}x{size[1]}.)")
    return f"{reply.content.strip()}{note}\nScreenshot: {path}"


# ---- keyboard and mouse --------------------------------------------------

async def type_text(args: dict, ctx: ToolContext) -> str:
    value = str(args.get("text", ""))
    if not value:
        return "Error: no text given"
    _, error = await _do(_backend.type_text, value)
    if error:
        return error
    if args.get("enter"):
        _, error = await _do(_backend.press, ["enter"])
    return error or f"Typed {len(value)} characters into the window in front."


async def press_keys(args: dict, ctx: ToolContext) -> str:
    raw = args.get("keys")
    keys = [k.strip().lower() for k in (raw if isinstance(raw, list) else re.split(r"[+\s,]+", str(raw or ""))) if str(k).strip()]
    if not keys:
        return "Error: give the keys, like ctrl+s or alt+tab or enter"
    times = max(1, min(_number(args, "times") or 1, 50))
    for _ in range(times):
        _, error = await _do(_backend.press, keys)
        if error:
            return error
    return f"Pressed {'+'.join(keys)}" + (f" {times} times" if times > 1 else "")


async def _on_screen(x: int | None, y: int | None) -> str | None:
    if x is None or y is None:
        return None
    size, error = await _do(_backend.screen_size)
    if error:
        return error
    if not (0 <= x < size[0] and 0 <= y < size[1]):
        return f"Error: {x},{y} is off the screen, which is {size[0]}x{size[1]}."
    return None


async def mouse_move(args: dict, ctx: ToolContext) -> str:
    x, y = _number(args, "x"), _number(args, "y")
    if x is None or y is None:
        return "Error: give x and y in screen pixels"
    error = await _on_screen(x, y)
    if not error:
        _, error = await _do(_backend.move, x, y)
    return error or f"Mouse is at {x},{y}."


async def mouse_click(args: dict, ctx: ToolContext) -> str:
    x, y = _number(args, "x"), _number(args, "y")
    if (x is None) != (y is None):
        return "Error: give both x and y, or neither to click where the mouse is"
    button = str(args.get("button") or "left").lower()
    if button not in ("left", "right", "middle"):
        return "Error: button is left, right or middle"
    clicks = 2 if args.get("double") else 1
    error = await _on_screen(x, y)
    if not error:
        _, error = await _do(_backend.click, x, y, button, clicks)
    where = f"at {x},{y}" if x is not None else "where the mouse is"
    return error or f"{'Double clicked' if clicks == 2 else 'Clicked'} {button} {where}."


async def mouse_scroll(args: dict, ctx: ToolContext) -> str:
    amount = _number(args, "amount")
    if not amount:
        return "Error: give an amount. Positive scrolls up, negative scrolls down."
    _, error = await _do(_backend.scroll, amount)
    return error or f"Scrolled {'up' if amount > 0 else 'down'} by {abs(amount)}."


_XY = {"type": "number", "description": "Screen pixel. 0,0 is the top left corner."}

ALWAYS = [
    Tool("open_path", "Open a file, a folder, a web link, or start an app by name (notepad, chrome, spotify) on the owner's computer.",
         params(["target"], target=text("A path, a link, or an app name"),
                args={"type": "array", "items": {"type": "string"}, "description": "Arguments for an app, each as its own item"}),
         open_path, tier=DANGER),
    Tool("list_processes", "List the programs running on the owner's computer with their pid and memory. Pass name to filter.",
         params(name=text("Part of a program name")), list_processes, tier=SAFE),
    Tool("end_process", "End a running program by pid or by exact name. Unsaved work in it is lost.",
         params(pid={"type": "number"}, name=text("Exact program name, like notepad or notepad.exe")), end_process, tier=DANGER),
]

GUI = [
    Tool("list_windows", "List the windows open on the owner's desktop and which one is in front.", params(), list_windows, tier=SAFE),
    Tool("focus_window", "Bring a window to the front by part of its title. Do this before typing into an app.",
         params(["title"], title=text("Part of the window title")), focus_window, tier=DANGER),
    Tool("close_window", "Close a window by part of its title.", params(["title"], title=text("Part of the window title")), close_window, tier=DANGER),
    Tool("clipboard_read", "Read the text on the owner's clipboard.", params(), clipboard_read, tier=DANGER),
    Tool("clipboard_write", "Put text on the owner's clipboard.", params(["text"], text=text("What to copy")), clipboard_write, tier=DANGER),
    Tool("screenshot", "Save a picture of the owner's screen to the workspace.", params(), screenshot, tier=DANGER),
    Tool("see_screen", "Look at the owner's screen and answer a question about it: what is open, what a dialog says, where a button is.",
         params(question=text("What to find out. Ask for x,y when you need to click something.")), see_screen, tier=DANGER),
    Tool("type_text", "Type text into the window that is in front, as if on the keyboard. Set enter to press Enter afterwards.",
         params(["text"], text=text("What to type"), enter={"type": "boolean"}), type_text, tier=DANGER),
    Tool("press_keys", "Press a key or a key combination in the window that is in front: enter, tab, esc, ctrl+s, alt+tab, win+d.",
         params(["keys"], keys=text("Keys joined with +"), times={"type": "number", "description": "How many times, default 1"}),
         press_keys, tier=DANGER),
    Tool("mouse_move", "Move the mouse pointer to a spot on the screen.", params(["x", "y"], x=_XY, y=_XY), mouse_move, tier=DANGER),
    Tool("mouse_click", "Click the mouse. Give x and y to click a spot, or neither to click where the pointer is. Use see_screen first to find the spot.",
         params(x=_XY, y=_XY, button=text("left, right or middle. Default left."), double={"type": "boolean"}), mouse_click, tier=DANGER),
    Tool("mouse_scroll", "Scroll the mouse wheel where the pointer is. Positive is up, negative is down.",
         params(["amount"], amount={"type": "number"}), mouse_scroll, tier=DANGER),
]


def gui_installed() -> bool:
    return find_spec("pyautogui") is not None


def tools(gui: bool | None = None) -> list[Tool]:
    """Apps and programs always. Screen, keyboard and mouse when installed."""
    return ALWAYS + (GUI if (gui_installed() if gui is None else gui) else [])
