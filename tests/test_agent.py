
import numpy as np

from anexis.core.agent import Agent
from anexis.memory.learn import Learner
from anexis.tools.base import Tool
from anexis.tools.builtin import register_builtin
from anexis.tools.registry import Registry
from tests.fakes import FakeRouter, call


def build(settings, memory, *script, **kw):
    settings.workspace.mkdir(parents=True, exist_ok=True)
    settings.learn = False
    registry = Registry()
    register_builtin(registry)
    router = FakeRouter(*script, **kw)
    return Agent(settings, memory, router, registry), router, registry


async def turn(agent, text, session=None, confirm=None, **kw):
    events = []
    result = await agent.run_turn(session, text, emit=events.append, confirm=confirm, **kw)
    return result, events


async def test_reply_is_streamed_stored_and_returned(settings, memory):
    agent, _, _ = build(settings, memory, "Hello there")
    result, events = await turn(agent, "hi")
    assert result["text"] == "Hello there"
    assert [e["delta"] for e in events if e["type"] == "text"] == ["Hello there"]
    assert [m["role"] for m in memory.history(result["session_id"])] == ["user", "assistant"]
    assert events[-1]["type"] == "done"


async def test_second_turn_shows_the_model_the_first_one(settings, memory):
    agent, router, _ = build(settings, memory, "Blue.", "You said blue.")
    first, _ = await turn(agent, "my favorite color is blue")
    await turn(agent, "what did I say?", session=first["session_id"])
    contents = [m["content"] for m in router.calls[-1]["messages"]]
    assert "my favorite color is blue" in contents and "Blue." in contents


async def test_relevant_memories_and_about_me_reach_the_model(settings, memory):
    memory.add("fact", "Age is 19", pinned=True, source="about_me")
    memory.add("class", "Chemistry lab is on Thursday afternoons")
    memory.add("fact", "Favorite pizza topping is mushroom")
    agent, router, _ = build(settings, memory, "Thursday.")
    result, _ = await turn(agent, "when is chemistry lab?")
    system = router.system()
    assert "Age is 19" in system and "Chemistry lab is on Thursday" in system
    assert "mushroom" not in system
    assert len(result["memories_used"]) == 1


async def test_memories_that_were_used_get_counted(settings, memory):
    mid = memory.add("class", "Chemistry lab is on Thursday afternoons")
    agent, _, _ = build(settings, memory, "Thursday.")
    await turn(agent, "when is chemistry lab?")
    assert memory.get(mid).use_count == 1


async def test_tool_call_runs_and_its_result_goes_back_to_the_model(settings, memory):
    agent, router, _ = build(settings, memory, call("calculate", expression="6*7"), "It is 42.")
    result, _ = await turn(agent, "calculate 6 times 7")
    tool_msg = router.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "42" in tool_msg["content"]
    assert result["text"] == "It is 42." and result["tools_used"] == ["calculate"]
    assert memory.tool_stats()["calculate"]["calls"] == 1


async def test_dangerous_tool_does_not_run_when_the_owner_says_no(settings, memory):
    agent, router, _ = build(settings, memory, call("run_shell", command="touch made.txt"), "Ok, I did not run it.")
    asked = []

    async def confirm(tool, args, reason):
        asked.append((tool.name, args))
        return False

    await turn(agent, "run the shell command touch made.txt", confirm=confirm)
    assert asked == [("run_shell", {"command": "touch made.txt"})]
    assert not (settings.workspace / "made.txt").exists()
    assert "declined" in router.calls[1]["messages"][-1]["content"].lower()


async def test_dangerous_tool_runs_when_the_owner_says_yes(settings, memory):
    agent, _, _ = build(settings, memory, call("run_shell", command="touch made.txt"), "Done.")

    async def confirm(tool, args, reason):
        return True

    await turn(agent, "run the shell command touch made.txt", confirm=confirm)
    assert (settings.workspace / "made.txt").exists()


async def test_with_nobody_to_ask_a_dangerous_tool_is_refused(settings, memory):
    agent, _, _ = build(settings, memory, call("run_shell", command="touch made.txt"), "Could not.")
    await turn(agent, "run the shell command touch made.txt")
    assert not (settings.workspace / "made.txt").exists()


async def test_a_crashing_tool_is_reported_to_the_model_not_the_owner(settings, memory):
    agent, router, registry = build(settings, memory, call("boom"), "That tool is broken.")

    async def boom(args, ctx):
        raise RuntimeError("kaput")

    registry.add(Tool("boom", "explode loudly", {}, boom, core=True))
    result, _ = await turn(agent, "explode")
    assert "kaput" in router.calls[1]["messages"][-1]["content"]
    assert result["text"] == "That tool is broken."
    assert memory.tool_stats()["boom"]["failures"] == 1


async def test_calling_a_tool_that_does_not_exist_gets_a_helpful_error(settings, memory):
    agent, router, _ = build(settings, memory, call("teleport"), "No such tool.")
    await turn(agent, "teleport me")
    assert "find_tools" in router.calls[1]["messages"][-1]["content"]


async def test_long_tool_output_is_cut_before_the_model_sees_it(settings, memory):
    settings.tool_output_chars = 100
    agent, router, registry = build(settings, memory, call("flood"), "ok")

    async def flood(args, ctx):
        return "x" * 5000

    registry.add(Tool("flood", "print a lot", {}, flood, core=True))
    await turn(agent, "flood")
    assert len(router.calls[1]["messages"][-1]["content"]) < 300


async def test_the_loop_stops_after_the_step_limit(settings, memory):
    settings.max_steps = 3
    agent, router, _ = build(settings, memory, *[call("time_now") for _ in range(10)])
    result, _ = await turn(agent, "what time is it")
    assert len(router.calls) == 3 and "step limit" in result["text"].lower()


async def test_only_a_few_tools_are_offered_and_find_tools_adds_more(settings, memory):
    settings.max_tools = 6
    agent, router, registry = build(
        settings, memory, call("find_tools", query="run a shell command"), "found"
    )
    await turn(agent, "hello")
    assert len(router.tool_names(0)) <= 6 and "run_shell" not in router.tool_names(0)
    assert "run_shell" in router.tool_names(1)
    assert len(registry) > 6


async def test_the_mode_is_told_to_the_model_and_kept_for_the_session(settings, memory):
    agent, router, _ = build(settings, memory, "ok", "ok")
    first, _ = await turn(agent, "hi", mode="school")
    await turn(agent, "hi again", session=first["session_id"])
    assert "school" in router.system(0) and "school" in router.system(1)


async def test_things_due_soon_are_shown_to_the_model(settings, memory):
    memory.db.execute(
        "INSERT INTO items (type, title, due_at, created_at) VALUES ('assignment','Chem lab writeup', date('now'), 0)"
    )
    agent, router, _ = build(settings, memory, "ok")
    await turn(agent, "hi")
    assert "Chem lab writeup" in router.system()


async def test_when_no_model_answers_the_owner_gets_a_clear_error(settings, memory):
    agent, _, _ = build(settings, memory)  # empty script: every call fails
    result, events = await turn(agent, "hi")
    assert events[-1]["type"] == "error" and "model" in events[-1]["message"].lower()
    assert [m["role"] for m in memory.history(result["session_id"])] == ["user"]


async def test_meaning_search_is_used_when_embeddings_exist(settings, memory):
    mid = memory.add("habit", "Runs five miles before breakfast")
    memory.set_vector(mid, "fake:emb", np.array([1.0, 0.0]))
    agent, router, _ = build(settings, memory, "ok", embedder=lambda t: np.array([1.0, 0.0]))
    await turn(agent, "any ideas for my morning jog?")
    assert "Runs five miles" in router.system()


async def test_learning_runs_after_the_turn_without_blocking_the_reply(settings, memory):
    agent, router, _ = build(
        settings, memory, "Nice.",
        roles={"small": [{"ops": [{"op": "add", "kind": "fact", "text": "Has a dog named Biscuit"}]}]},
    )
    settings.learn = True
    agent.learner = Learner(memory, router)
    await turn(agent, "my dog Biscuit chewed my shoe again")
    await agent.drain()
    assert [m.text for m in memory.search("dog")] == ["Has a dog named Biscuit"]


async def test_a_crash_while_learning_is_logged_and_never_reaches_the_owner(settings, memory):
    agent, _, _ = build(settings, memory, "Nice.")
    settings.learn = True

    class BrokenLearner:
        async def learn(self, user_text, reply):
            raise RuntimeError("disk full")

    agent.learner = BrokenLearner()
    result, events = await turn(agent, "my dog Biscuit chewed my shoe again")
    await agent.drain()
    assert result["text"] == "Nice." and events[-1]["type"] == "done"
    assert memory.events()[0]["kind"] == "learn_failed" and "disk full" in memory.events()[0]["error"]


async def test_standing_instructions_reach_the_model_even_when_the_message_is_unrelated(settings, memory):
    memory.add("lesson", "Never use dashes when writing to them")
    memory.add("fact", "Favorite pizza topping is mushroom")
    agent, router, _ = build(settings, memory, "Dogs are great.")
    await turn(agent, "write me a paragraph about dogs")
    assert "Never use dashes" in router.system() and "mushroom" not in router.system()
    assert router.system().count("Never use dashes") == 1


async def test_only_the_strongest_instructions_fit_when_there_are_too_many(settings, memory):
    for i in range(60):
        memory.add("lesson", f"Weak instruction number {i} " + "x" * 80, confidence=0.3)
    memory.add("lesson", "The one that matters most", confidence=1.0, importance=1.0)
    agent, router, _ = build(settings, memory, "ok")
    await turn(agent, "hello")
    assert "The one that matters most" in router.system()
    assert router.system().count("Weak instruction") < 30
