import pytest

from greg.tools.base import DANGER, SAFE, WRITE, Tool, ToolContext
from greg.tools.builtin import register_builtin
from greg.tools.permissions import decide
from greg.tools.registry import Registry


async def noop(args, ctx):
    return "ok"


def tool(name, desc="", tier=SAFE, **kw):
    return Tool(name, desc, {"type": "object", "properties": {}}, noop, tier=tier, **kw)


@pytest.fixture
def registry(settings, memory):
    r = Registry()
    register_builtin(r)
    return r


@pytest.fixture
def ctx(settings, memory, registry):
    settings.workspace.mkdir(parents=True, exist_ok=True)
    return ToolContext(settings=settings, memory=memory, router=None, registry=registry, session_id="s")


async def run(registry, ctx, name, **args):
    return await registry.get(name).handler(args, ctx)


# ---- permissions ----------------------------------------------------------


def test_safe_tools_run_without_asking(settings):
    assert decide(tool("t"), {}, settings)[0] == "allow"


def test_dangerous_tools_always_ask(settings):
    assert decide(tool("t", tier=DANGER), {}, settings)[0] == "ask"


def test_file_tools_run_freely_inside_the_workspace(settings):
    inside = str(settings.workspace / "notes" / "a.txt")
    assert decide(tool("t", tier=WRITE), {"path": inside}, settings)[0] == "allow"
    assert decide(tool("t", tier=WRITE), {"path": "notes/a.txt"}, settings)[0] == "allow"


def test_file_tools_ask_outside_the_workspace(settings):
    assert decide(tool("t", tier=WRITE), {"path": "/etc/passwd"}, settings)[0] == "ask"


def test_dot_dot_cannot_sneak_out_of_the_workspace(settings):
    sneaky = str(settings.workspace / ".." / ".." / "etc" / "passwd")
    assert decide(tool("t", tier=WRITE), {"path": sneaky}, settings)[0] == "ask"
    assert decide(tool("t", tier=WRITE), {"path": "../outside.txt"}, settings)[0] == "ask"


def test_a_symlink_pointing_outside_the_workspace_asks(settings, tmp_path):
    settings.workspace.mkdir(parents=True)
    (settings.workspace / "link").symlink_to(tmp_path)
    assert decide(tool("t", tier=WRITE), {"path": "link/secret.txt"}, settings)[0] == "ask"


def test_owner_can_loosen_or_tighten_one_tool(settings):
    settings.permissions = {"run_shell": "allow", "web_search": "ask"}
    assert decide(tool("run_shell", tier=DANGER), {}, settings)[0] == "allow"
    assert decide(tool("web_search"), {}, settings)[0] == "ask"


# ---- picking tools --------------------------------------------------------


def test_picker_offers_matching_tools_plus_the_core_ones():
    r = Registry()
    r.add(tool("weather_now", "Get the weather forecast for a city"))
    r.add(tool("spreadsheet_read", "Read cells from an excel spreadsheet"))
    r.add(tool("find_tools", "Search for more tools", core=True))
    names = [t.name for t in r.pick("whats the weather in Denver", k=5)]
    assert "weather_now" in names and "find_tools" in names and "spreadsheet_read" not in names


def test_picker_never_offers_more_than_k_tools():
    r = Registry()
    for i in range(30):
        r.add(tool(f"file_tool_{i}", "read a file from disk"))
    assert len(r.pick("read the file", k=6)) == 6


def test_a_tool_that_keeps_failing_drops_below_a_working_twin():
    r = Registry()
    r.add(tool("search_a", "search the web for pages"))
    r.add(tool("search_b", "search the web for pages"))
    stats = {"search_a": {"calls": 10, "failures": 9}, "search_b": {"calls": 10, "failures": 0}}
    assert [t.name for t in r.pick("search the web", k=1, stats=stats)] == ["search_b"]


def test_a_name_that_is_not_valid_for_models_is_cleaned(registry):
    r = Registry()
    r.add(tool("my server/tool.name!" + "x" * 80))
    name = r.all()[0].name
    assert len(name) <= 64 and all(c.isalnum() or c in "_-" for c in name)


# ---- built in tools -------------------------------------------------------


async def test_write_then_read_a_file_relative_to_the_workspace(registry, ctx):
    await run(registry, ctx, "write_file", path="essay/draft.txt", content="hello")
    assert (ctx.settings.workspace / "essay" / "draft.txt").read_text() == "hello"
    assert "hello" in await run(registry, ctx, "read_file", path="essay/draft.txt")


async def test_reading_a_missing_file_says_so_instead_of_crashing(registry, ctx):
    assert "not found" in (await run(registry, ctx, "read_file", path="nope.txt")).lower()


async def test_shell_returns_output_and_exit_code(registry, ctx):
    out = await run(registry, ctx, "run_shell", command="echo hi && exit 3")
    assert "hi" in out and "exit code 3" in out


async def test_shell_stops_a_command_that_runs_too_long(registry, ctx):
    out = await run(registry, ctx, "run_shell", command="sleep 5", timeout=1)
    assert "timed out" in out.lower()


async def test_calculate_does_math_and_refuses_code(registry, ctx):
    assert "14" in await run(registry, ctx, "calculate", expression="2 + 3 * 4")
    assert "error" in (await run(registry, ctx, "calculate", expression="__import__('os').system('ls')")).lower()


async def test_assignments_are_listed_soonest_first_and_can_be_finished(registry, ctx):
    await run(registry, ctx, "add_item", type="assignment", title="History essay", due="2030-05-09")
    await run(registry, ctx, "add_item", type="assignment", title="Chem lab", due="2030-05-02")
    await run(registry, ctx, "add_item", type="note", title="Random idea")
    listed = await run(registry, ctx, "list_items", type="assignment")
    assert listed.index("Chem lab") < listed.index("History essay") and "Random idea" not in listed
    first_id = int(listed.split("#")[1].split()[0])
    await run(registry, ctx, "complete_item", id=first_id)
    assert "Chem lab" not in await run(registry, ctx, "list_items", type="assignment")


async def test_a_bad_due_date_is_rejected_with_a_hint(registry, ctx):
    out = await run(registry, ctx, "add_item", type="todo", title="x", due="next blursday")
    assert "date" in out.lower() and "Nothing" in await run(registry, ctx, "list_items", type="todo")


async def test_remember_saves_a_memory_the_recall_tool_can_find(registry, ctx):
    await run(registry, ctx, "remember", text="Locker code is 4412", kind="fact")
    assert "4412" in await run(registry, ctx, "recall", query="locker code")


async def test_find_tools_lists_tools_by_what_they_do(registry, ctx):
    out = await run(registry, ctx, "find_tools", query="run a shell command")
    assert "run_shell" in out


async def test_cancelling_a_running_command_kills_it(tmp_path):
    import asyncio
    import os

    from greg.tools.builtin.system import run_process

    task = asyncio.create_task(run_process("echo $$ > pid; sleep 30", tmp_path, 60))
    while not (tmp_path / "pid").exists() or not (tmp_path / "pid").read_text().strip():
        await asyncio.sleep(0.02)
    pid = int((tmp_path / "pid").read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.02)
    pytest.fail("the command kept running after it was cancelled")
