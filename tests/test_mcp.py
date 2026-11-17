import sys
from pathlib import Path

import pytest

from anexis.tools.base import DANGER, SAFE, WRITE, ToolContext
from anexis.tools.mcp_client import MCPManager, launch_command, load_manifest
from anexis.tools.registry import Registry

SERVER = str(Path(__file__).parent / "mcp_echo_server.py")


def manifest(settings, text):
    settings.home.mkdir(parents=True, exist_ok=True)
    settings.manifest = settings.home / "manifest.yaml"
    settings.manifest.write_text(text)
    return settings


def echo_entry(name="echo", extra="", args=""):
    return (
        f"  - name: {name}\n    type: command\n    command: ['{sys.executable}', '{SERVER}'{args}]\n"
        f"    risk: write\n{extra}"
    )


@pytest.fixture
async def running(settings, memory):
    manifest(settings, "servers:\n" + echo_entry(extra="    env: [PASS_ME]\n"))
    settings.env = {"PASS_ME": "yes", "SECRET_OTHER": "no"}
    registry = Registry()
    manager = MCPManager(settings, registry)
    await manager.start()
    ctx = ToolContext(settings=settings, memory=memory, router=None, registry=registry, session_id="s")
    yield manager, registry, ctx
    await manager.stop()


def test_manifest_builds_pinned_launch_commands(settings):
    manifest(settings, """servers:
  - {name: fs, type: npm, package: "@scope/server-fs", version: "2.3.0", args: ["{workspace}"]}
  - {name: git, type: pypi, package: mcp-server-git, version: "2026.11.11"}
  - {name: word, type: pypi, package: office-word-mcp-server, version: "1.1.11", bin: word_mcp_server}
""")
    fs, git, word = load_manifest(settings)
    npx, *rest = launch_command(fs, settings)
    assert Path(npx).name == "npx" and rest == ["-y", "@scope/server-fs@2.3.0", str(settings.workspace)]
    assert launch_command(git, settings) == ["uvx", "--from", "mcp-server-git==2026.11.11", "mcp-server-git"]
    assert launch_command(word, settings)[-1] == "word_mcp_server"


def test_an_entry_without_a_pinned_version_is_rejected(settings):
    manifest(settings, "servers:\n  - {name: fs, type: npm, package: some-server}\n")
    with pytest.raises(ValueError, match="version"):
        load_manifest(settings)


def test_a_server_waits_for_its_key_and_turns_on_once_the_key_exists(settings):
    manifest(settings, "servers:\n  - {name: notion, type: npm, package: n, version: '1', needs: [NOTION_TOKEN]}\n")
    assert load_manifest(settings)[0].state(settings) == "needs key"
    settings.env = {"NOTION_TOKEN": "x"}
    assert load_manifest(settings)[0].state(settings) == "ready"


def test_a_server_switched_off_stays_off_even_with_its_key(settings):
    manifest(settings, "servers:\n  - {name: n, type: npm, package: n, version: '1', enabled: false}\n")
    assert load_manifest(settings)[0].state(settings) == "off"


def test_the_repo_manifest_is_valid_and_every_entry_names_its_source(settings):
    from anexis.config import Settings

    specs = load_manifest(Settings(home=settings.home))
    assert len(specs) >= 20
    assert len({s.name for s in specs}) == len(specs)
    for spec in specs:
        assert spec.source.startswith("https://"), spec.name
        assert spec.license, spec.name
        assert spec.risk in (SAFE, WRITE, DANGER), spec.name


async def test_server_tools_show_up_prefixed_and_can_be_called(running):
    manager, registry, ctx = running
    assert manager.status["echo"]["state"] == "running" and manager.status["echo"]["tools"] == 4
    assert await registry.get("echo_echo").handler({"text": "hi"}, ctx) == "echo: hi"


async def test_read_only_tools_are_safe_and_the_rest_use_the_manifest_risk(running):
    _, registry, _ = running
    assert registry.get("echo_echo").tier == SAFE
    assert registry.get("echo_save_note").tier == WRITE


async def test_a_failing_tool_call_comes_back_as_an_error_string(running):
    _, registry, ctx = running
    out = await registry.get("echo_explode").handler({}, ctx)
    assert out.startswith("Error:") and "explode" in out


async def test_servers_only_get_the_env_vars_the_manifest_names(running):
    _, registry, ctx = running
    show = registry.get("echo_show_env").handler
    assert await show({"name": "PASS_ME"}, ctx) == "yes"
    assert await show({"name": "SECRET_OTHER"}, ctx) == "unset"


async def test_a_server_that_fails_to_start_is_reported_and_does_not_block_others(settings):
    manifest(settings, "servers:\n" + echo_entry("bad", args=", '--crash'") + echo_entry("good"))
    registry = Registry()
    manager = MCPManager(settings, registry, start_timeout=20)
    await manager.start()
    try:
        assert manager.status["bad"]["state"] == "failed" and manager.status["bad"]["error"]
        assert manager.status["good"]["state"] == "running"
        assert registry.get("good_echo") and not registry.get("bad_echo")
    finally:
        await manager.stop()


async def test_stopping_removes_the_tools(settings):
    manifest(settings, "servers:\n" + echo_entry())
    registry = Registry()
    manager = MCPManager(settings, registry)
    await manager.start()
    await manager.stop()
    assert registry.get("echo_echo") is None


def test_tool_servers_prefer_the_node_the_installer_put_in_the_home_folder(settings, tmp_path, monkeypatch):
    from anexis.tools.mcp_client import _server_env, node_dir

    monkeypatch.setenv("HOME", str(tmp_path))
    manifest(settings, "servers:\n  - {name: fs, type: npm, package: p, version: '1'}\n")
    spec = load_manifest(settings)[0]
    assert str(node_dir()) not in _server_env(spec, settings)["PATH"]  # not there yet
    node_dir().mkdir(parents=True)
    (node_dir() / "npx").write_text("#!/bin/sh\n")
    (node_dir() / "npx").chmod(0o755)
    assert _server_env(spec, settings)["PATH"].startswith(str(node_dir()) + ":")
    assert launch_command(spec, settings)[0] == str(node_dir() / "npx")


async def test_with_outside_tools_off_no_tool_server_is_started(settings):
    import asyncio

    from anexis.core.app import AnexisApp
    from tests.fakes import FakeRouter

    manifest(settings, "servers:\n" + echo_entry())
    settings.outside_tools = False
    settings.consolidate_minutes = 0
    anexis = AnexisApp(settings, router=FakeRouter())
    await anexis.start()
    await asyncio.sleep(0.3)
    assert anexis.mcp.status == {} and anexis.registry.get("echo_echo") is None
    await anexis.stop()
