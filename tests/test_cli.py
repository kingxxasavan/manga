import io

from rich.console import Console

from greg.cli.repl import ChatSession, header, interview, parse_command, short_args
from tests.fakes import call


def test_plain_text_is_a_message_and_slash_words_are_commands():
    assert parse_command("hello there") == (None, "hello there")
    assert parse_command("/mode school") == ("mode", "school")
    assert parse_command("  /Memory  chem lab  ") == ("memory", "chem lab")
    assert parse_command("/quit") == ("quit", "")
    assert parse_command("/") == (None, "/")


def test_header_shows_model_memory_tools_and_mode():
    line = header({"name": "Greg", "providers": ["ollama", "nvidia"], "memories": 214, "tools": 162, "tools_offered": 12}, "school")
    for piece in ("greg", "ollama", "memory 214", "tools 162", "mode school"):
        assert piece in line


def test_long_tool_arguments_are_shortened_for_the_screen():
    assert short_args({"command": "ls"}) == "command=ls"
    assert len(short_args({"content": "x" * 5000})) < 120


async def test_interview_keeps_old_answers_on_enter_clears_on_dash_and_splits_lists():
    from greg.profile.about import BY_KEY

    answers = {"name": "", "age": "20", "classes": "Chem 101; Calc 2", "habits": "-", "work": ""}
    shown = {}

    async def ask(section, default):
        shown[section.key] = default
        return answers[section.key]

    current = {"name": "Sam", "age": "19", "habits": ["Runs", "Reads"]}
    result = await interview(ask, current, [BY_KEY[k] for k in answers])
    assert result == {"name": "Sam", "age": "20", "classes": ["Chem 101", "Calc 2"], "habits": []}
    assert shown["habits"] == "Runs; Reads" and shown["name"] == "Sam"


def session(client, answers=()):
    out = io.StringIO()
    queue = list(answers)

    async def yes_no(question):
        return queue.pop(0)

    return ChatSession(client, Console(file=out, force_terminal=False, width=100), yes_no), out


async def test_a_message_prints_the_reply_and_what_was_used(live):
    _, client = await live(call("calculate", expression="6*7"), "It is 42.")
    chat, out = session(client)
    await chat.send("what is 6 times 7, calculate it")
    shown = out.getvalue()
    assert "It is 42." in shown and "calculate" in shown
    assert chat.session_id


async def test_the_owner_is_asked_before_a_dangerous_tool_and_yes_runs_it(live, settings):
    _, client = await live(call("run_shell", command="touch yes.txt"), "Done.")
    chat, out = session(client, answers=[True])
    await chat.send("run the shell command")
    assert "run_shell" in out.getvalue() and "touch yes.txt" in out.getvalue()
    assert (settings.workspace / "yes.txt").exists()


async def test_answering_no_keeps_the_tool_from_running(live, settings):
    _, client = await live(call("run_shell", command="touch no.txt"), "Okay, skipped.")
    chat, out = session(client, answers=[False])
    await chat.send("run the shell command")
    assert not (settings.workspace / "no.txt").exists() and "Okay, skipped." in out.getvalue()


async def test_the_session_continues_across_messages(live):
    greg, client = await live("one", "two")
    chat, _ = session(client)
    await chat.send("first")
    first = chat.session_id
    await chat.send("second")
    assert chat.session_id == first and len(greg.memory.history(first)) == 4


async def test_a_model_outage_is_shown_as_an_error_not_a_crash(live):
    _, client = await live()
    chat, out = session(client)
    await chat.send("hi")
    assert "No model could answer" in out.getvalue()


async def test_memory_commands_work_from_the_chat(live):
    greg, client = await live()
    chat, out = session(client)
    await chat.command("remember", "Locker code is 4412")
    await chat.command("memory", "locker")
    assert "4412" in out.getvalue()
    await chat.command("forget", str(greg.memory.list()[0].id))
    assert greg.memory.count() == 0


async def test_mode_command_changes_the_mode_and_rejects_unknown_ones(live):
    _, client = await live()
    chat, out = session(client)
    await chat.command("mode", "school")
    await chat.command("mode", "party")
    assert chat.mode == "school" and "general, school, work, project" in out.getvalue()
