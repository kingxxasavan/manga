import subprocess
import sys

import pytest

from anexis import platform
from anexis.config import Provider
from anexis.tools.base import ToolContext
from anexis.tools.builtin import desktop
from tests.fakes import FakeRouter


class FakeDesktop:
    """Records what the tools asked the desktop to do."""

    def __init__(self):
        self.did = []
        self.clip = "old"
        self.open = [{"title": "Notes - Notepad", "active": True}, {"title": "Inbox - Mail", "active": False, "minimized": True}]

    def screen_size(self):
        return 1920, 1080

    def screenshot(self, path):
        from PIL import Image

        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (3200, 1800), "navy").save(path)
        return 3200, 1800

    def windows(self):
        return self.open

    def _title(self, part):
        match = [w["title"] for w in self.open if part.lower() in w["title"].lower()]
        if not match:
            raise desktop.Unavailable(f"Error: no open window has {part!r} in its title.")
        return match[0]

    def focus(self, title):
        self.did.append(("focus", self._title(title)))
        return self._title(title)

    def close(self, title):
        self.did.append(("close", self._title(title)))
        return self._title(title)

    def clipboard_read(self):
        return self.clip

    def clipboard_write(self, value):
        self.clip = value

    def type_text(self, value):
        self.did.append(("type", value))

    def press(self, keys):
        self.did.append(("press", keys))

    def move(self, x, y):
        self.did.append(("move", x, y))

    def click(self, x, y, button, clicks):
        self.did.append(("click", x, y, button, clicks))

    def scroll(self, amount):
        self.did.append(("scroll", amount))


@pytest.fixture
def fake():
    real, stand_in = desktop._backend, FakeDesktop()
    desktop.set_backend(stand_in)
    yield stand_in
    desktop.set_backend(real)


@pytest.fixture
def ctx(settings, memory):
    return ToolContext(settings=settings, memory=memory, router=FakeRouter(), registry=None, session_id="s")


def test_screen_tools_are_only_offered_when_installed():
    names = lambda gui: {t.name for t in desktop.tools(gui)}  # noqa: E731
    assert names(False) == {"open_path", "list_processes", "end_process"}
    assert {"mouse_click", "type_text", "see_screen", "list_windows", "clipboard_read"} <= names(True)


async def test_keys_and_text_reach_the_desktop(fake, ctx):
    assert "Typed 5" in await desktop.type_text({"text": "héllo", "enter": True}, ctx)
    assert await desktop.press_keys({"keys": "Ctrl + S"}, ctx) == "Pressed ctrl+s"
    assert await desktop.press_keys({"keys": ["alt", "tab"], "times": 2}, ctx) == "Pressed alt+tab 2 times"
    assert fake.did == [("type", "héllo"), ("press", ["enter"]), ("press", ["ctrl", "s"]),
                        ("press", ["alt", "tab"]), ("press", ["alt", "tab"])]
    assert (await desktop.press_keys({"keys": ""}, ctx)).startswith("Error:")


async def test_the_mouse_clicks_where_asked_and_never_off_screen(fake, ctx):
    assert await desktop.mouse_click({"x": 100.0, "y": "200", "double": True}, ctx) == "Double clicked left at 100,200."
    assert await desktop.mouse_click({"button": "right"}, ctx) == "Clicked right where the mouse is."
    assert await desktop.mouse_move({"x": 5, "y": 6}, ctx) == "Mouse is at 5,6."
    assert await desktop.mouse_scroll({"amount": -3}, ctx) == "Scrolled down by 3."
    assert fake.did == [("click", 100, 200, "left", 2), ("click", None, None, "right", 1), ("move", 5, 6), ("scroll", -3)]
    assert "off the screen" in await desktop.mouse_click({"x": 5000, "y": 10}, ctx)
    assert (await desktop.mouse_click({"x": 5}, ctx)).startswith("Error:")
    assert (await desktop.mouse_click({"x": 1, "y": 1, "button": "side"}, ctx)).startswith("Error:")
    assert len(fake.did) == 4


async def test_windows_and_clipboard(fake, ctx):
    listing = await desktop.list_windows({}, ctx)
    assert "* Notes - Notepad" in listing and "Inbox - Mail  (minimized)" in listing
    assert await desktop.focus_window({"title": "inbox"}, ctx) == "Brought to the front: Inbox - Mail"
    assert (await desktop.close_window({"title": "nothing like this"}, ctx)).startswith("Error:")
    assert await desktop.clipboard_read({}, ctx) == "old"
    assert "Copied 3" in await desktop.clipboard_write({"text": "new"}, ctx)
    assert fake.clip == "new"


async def test_a_machine_without_the_packages_says_how_to_get_them(ctx, monkeypatch):
    class Bare(desktop.Backend):
        def _gui(self):
            raise desktop.Unavailable(desktop.NEEDS)

    monkeypatch.setattr(desktop, "_backend", Bare())
    for tool, args in ((desktop.type_text, {"text": "x"}), (desktop.mouse_click, {"x": 1, "y": 1}), (desktop.screenshot, {})):
        assert "uv sync --extra desktop" in await tool(args, ctx)


async def test_see_screen_needs_a_model_that_can_see(fake, ctx):
    reply = await desktop.see_screen({"question": "what is open"}, ctx)
    assert reply.startswith("Error: no model that can see") and "vision =" in reply


async def test_see_screen_sends_the_picture_and_reports_the_scale(fake, ctx, settings):
    pytest.importorskip("PIL")
    settings.providers = [Provider("local", "http://x/v1", models={"chat": "c", "vision": "v"})]
    ctx.router = FakeRouter("The Save button is at 800,450.")
    reply = await desktop.see_screen({"question": "where is Save"}, ctx)
    sent = ctx.router.calls[0]
    assert sent["role"] == "vision"
    text_part, image_part = sent["messages"][0]["content"]
    assert "1600 by 900" in text_part["text"] and "where is Save" in text_part["text"]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert "800,450" in reply and "Multiply any x,y by 2.000" in reply and "3200x1800" in reply


def test_a_picture_only_ever_goes_to_a_model_named_for_vision(settings):
    from anexis.llm.router import Router

    settings.providers = [Provider("a", "http://a/v1", models={"chat": "talker"}),
                          Provider("b", "http://b/v1", models={"chat": "t2", "vision": "seer"})]
    router = Router(settings)
    by_name = {p.cfg.name: p for p in router.providers}
    assert router._model(by_name["a"], "vision") is None and router._model(by_name["b"], "vision") == "seer"
    assert router._model(by_name["a"], "coder") == "talker"


async def test_open_path_opens_odd_names_whole_and_never_through_a_shell(ctx, settings, monkeypatch):
    opened = []
    monkeypatch.setattr(desktop, "open_with_default_app", opened.append)
    target = settings.workspace / "my föld er" / "a b; echo pwned.txt"
    target.parent.mkdir(parents=True)
    target.write_text("x")
    assert await desktop.open_path({"target": str(target)}, ctx) == f"Opened {target}"
    assert await desktop.open_path({"target": "https://example.com/a b"}, ctx) == "Opened https://example.com/a b"
    assert opened == [str(target), "https://example.com/a b"]
    assert (await desktop.open_path({"target": "no-such-program-here"}, ctx)).startswith("Error:")
    assert (await desktop.open_path({}, ctx)).startswith("Error:")


async def test_processes_can_be_listed_and_ended_but_never_anexis_itself(ctx):
    victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert str(victim.pid) in await desktop.list_processes({"name": "python"}, ctx)
        assert f"({victim.pid})" in await desktop.end_process({"pid": victim.pid}, ctx)
        victim.wait(5)
        assert not platform.is_running(victim.pid)
    finally:
        victim.kill()
    import os

    refused = await desktop.end_process({"pid": os.getpid()}, ctx)
    assert refused.startswith("Error:") and "Anexis itself" in refused
    assert (await desktop.end_process({}, ctx)).startswith("Error:")
    assert (await desktop.end_process({"name": "no-such-program-xyz"}, ctx)).startswith("Error:")
