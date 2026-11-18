import json
from datetime import datetime

import pytest

from anexis.core.initiative import INBOX, Initiative, quiet
from anexis.profile.about import import_profile
from tests.conftest import make_app


def said(action, text="", task="", why="test"):
    return json.dumps({"action": action, "text": text, "task": task, "why": why})


NOON = datetime(2026, 11, 18, 12, 0)


@pytest.fixture
def app(settings):
    def build(*script, autonomy="ask"):
        settings.autonomy = autonomy
        anexis, _ = make_app(settings, *script)
        seen = []
        anexis.events.publish = seen.append
        anexis.seen = seen
        return anexis
    return build


def inbox(anexis):
    return [m["content"] for m in anexis.memory.history(INBOX, 20)]


async def test_a_heads_up_goes_to_its_own_chat_with_a_notification(app):
    anexis = app(said("say", "Your chem lab is due tomorrow."))
    result = await Initiative(anexis).check_in(NOON)
    assert result == {"action": "say", "text": "Your chem lab is due tomorrow."}
    assert inbox(anexis) == ["Your chem lab is due tomorrow."]
    assert anexis.seen[-1] == {"type": "initiative", "action": "say", "text": "Your chem lab is due tomorrow.", "session_id": INBOX}
    assert anexis.memory.list_sessions()[0]["title"].startswith("From Anexis")


async def test_it_asks_about_what_it_does_not_know_yet(app):
    anexis = app(said("ask", "What classes are you taking this term?"))
    import_profile(anexis.memory, {"name": "Sam"})
    await Initiative(anexis).check_in(NOON)
    context = anexis.router.calls[0]["messages"][0]["content"]
    assert '"classes"' in context and '"name"' not in context.split("what you do not know")[1].split("]")[0]
    assert inbox(anexis) == ["What classes are you taking this term?"]


async def test_what_it_looks_at_includes_due_work_overdue_work_and_health(app):
    anexis = app(said("none"))
    anexis.memory.db.execute("INSERT INTO items (type, title, due_at, created_at) VALUES ('assignment', 'Old essay', '2020-01-01', 0)")
    anexis.memory.db.commit()
    anexis.mcp.status = {"chart": {"state": "failed"}}
    assert (await Initiative(anexis).check_in(NOON))["action"] == "none"
    context = anexis.router.calls[0]["messages"][0]["content"]
    assert "Old essay (was due 2020-01-01)" in context and "tool servers that failed: chart" in context
    assert inbox(anexis) == []


async def test_in_ask_mode_a_task_is_offered_not_done(app):
    anexis = app(said("do", "New slides are up in chem.", "download the new chemistry slides"))
    result = await Initiative(anexis).check_in(NOON)
    assert result["action"] == "offer"
    assert "I can do this for you: download the new chemistry slides" in inbox(anexis)[0]
    assert len(anexis.router.calls) == 1                     # it did not start working


async def test_in_act_mode_it_does_the_task_and_reports(app):
    anexis = app(said("do", "", "check what is due this week"), "Nothing is due this week.", autonomy="act")
    result = await Initiative(anexis).check_in(NOON)
    assert result["action"] == "did" and result["text"] == "Nothing is due this week."
    assert inbox(anexis)[0].startswith("I did this on my own: check what is due this week.")
    assert {"type": "task_done", "text": "check what is due this week. Nothing is due this week."} in anexis.seen


async def test_on_its_own_nothing_that_needs_a_yes_runs(app, settings):
    from tests.fakes import call

    anexis = app(said("do", "", "clean up old files"), call("run_shell", command="rm -rf stuff"), "Skipped it.", autonomy="act")
    await Initiative(anexis).check_in(NOON)
    tool_result = next(m for m in anexis.router.calls[-1]["messages"] if m["role"] == "tool")["content"]
    assert "declined" in tool_result


async def test_it_never_says_the_same_thing_twice(app):
    anexis = app(said("say", "Your chem lab is due tomorrow."), said("say", "your chem lab is due tomorrow!"))
    await Initiative(anexis).check_in(NOON)
    assert (await Initiative(anexis).check_in(NOON)) == {"action": "none", "why": "already said"}
    assert len(inbox(anexis)) == 1


async def test_off_quiet_hours_and_the_daily_limit_hold_it_back(app, settings):
    anexis = app(said("say", "one"), said("say", "two"), autonomy="off")
    assert (await Initiative(anexis).check_in(NOON))["why"] == "autonomy is off"
    settings.autonomy = "ask"
    assert (await Initiative(anexis).check_in(datetime(2026, 11, 18, 23, 30)))["why"] == "quiet hours"
    settings.autonomy_daily = 1
    await Initiative(anexis).check_in(NOON)
    assert (await Initiative(anexis).check_in(NOON))["why"] == "enough for today"
    assert anexis.router.calls and len(anexis.router.calls) == 1


async def test_an_answer_it_cannot_read_does_nothing(app):
    anexis = app("Sure! I think I will say hi.")
    assert (await Initiative(anexis).check_in(NOON))["action"] == "none"
    assert inbox(anexis) == []


def test_quiet_hours_wrap_past_midnight():
    assert quiet(datetime(2026, 1, 1, 23, 0), "22:00-07:00") and quiet(datetime(2026, 1, 1, 6, 59), "22:00-07:00")
    assert not quiet(datetime(2026, 1, 1, 7, 0), "22:00-07:00") and not quiet(datetime(2026, 1, 1, 12, 0), "22:00-07:00")
    assert quiet(datetime(2026, 1, 1, 13, 0), "12:00-14:00") and not quiet(datetime(2026, 1, 1, 13, 0), "nonsense")


async def test_the_app_screen_can_change_autonomy_and_check_in_now(live, settings):
    import httpx

    _, client = await live(said("say", "Hello from me."))
    async with httpx.AsyncClient(base_url=client.url) as http:
        assert (await http.post("/settings", json={"autonomy": "act"})).json()["autonomy"] == "act"
        assert (await http.post("/settings", json={"autonomy": "always"})).status_code == 400
        now = (await http.post("/initiative/now")).json()
        if now["action"] == "skipped":  # the test may run during quiet hours
            assert now["why"] == "quiet hours"
        else:
            assert now == {"action": "say", "text": "Hello from me."}
            assert (await http.get("/sessions/inbox/messages")).json()["messages"][0]["content"] == "Hello from me."
