import numpy as np

from anexis.memory.consolidate import consolidate
from anexis.memory.learn import Learner, parse_json
from tests.fakes import FakeRouter


def learner(memory, *replies, **kw):
    router = FakeRouter(roles={"small": list(replies)}, **kw)
    return Learner(memory, router), router


def live(memory):
    return [m.text for m in memory.list()]


async def test_a_new_fact_is_added(memory):
    learn, _ = learner(memory, {"ops": [{"op": "add", "kind": "preference", "text": "Prefers tea over coffee", "importance": 0.4}]})
    await learn.learn("I always drink tea, never coffee", "Noted!")
    row = memory.list()[0]
    assert (row.kind, row.text, row.source) == ("preference", "Prefers tea over coffee", "learned")


async def test_saying_the_same_thing_again_makes_anexis_more_sure_not_duplicated(memory):
    mid = memory.add("preference", "Prefers tea over coffee", confidence=0.6)
    learn, _ = learner(memory, {"ops": [{"op": "add", "kind": "preference", "text": "prefers tea over coffee."}]})
    await learn.learn("tea please, you know I prefer it over coffee", "Sure")
    assert memory.count() == 1 and memory.get(mid).confidence > 0.6


async def test_the_model_can_reinforce_a_memory_it_was_shown(memory):
    mid = memory.add("habit", "Goes to the gym on Mondays", confidence=0.5)
    learn, router = learner(memory, lambda msgs: {"ops": [{"op": "reinforce", "id": mid}]})
    await learn.learn("heading to the gym, its Monday after all", "Have fun")
    assert f"#{mid}" in router.calls[0]["messages"][-1]["content"]  # it was shown the memory
    assert memory.get(mid).confidence > 0.5


async def test_a_changed_fact_replaces_the_old_one_and_keeps_history(memory):
    old = memory.add("fact", "Lives in Austin")
    learn, _ = learner(memory, {"ops": [{"op": "replace", "id": old, "text": "Lives in Denver"}]})
    await learn.learn("I moved, I live in Denver now not Austin", "Got it")
    assert live(memory) == ["Lives in Denver"]
    assert memory.get(old).superseded_by is not None


async def test_a_correction_is_saved_as_a_lesson_with_high_confidence(memory):
    learn, _ = learner(memory, {"ops": [{"op": "add", "kind": "lesson", "text": "Keep answers short, no long intros"}]})
    await learn.learn("no, stop writing such long intros, keep it short", "Understood.")
    row = memory.list()[0]
    assert row.kind == "lesson" and row.confidence >= 0.8


async def test_replace_with_an_id_the_model_made_up_becomes_a_plain_add(memory):
    learn, _ = learner(memory, {"ops": [{"op": "replace", "id": 9999, "text": "Drives a red truck"}]})
    await learn.learn("I drive a red truck these days", "Cool")
    assert live(memory) == ["Drives a red truck"]


async def test_garbage_from_the_model_changes_nothing(memory):
    memory.add("fact", "Lives in Austin")
    learn, _ = learner(memory, "Sure! Here are some thoughts, no JSON though.")
    assert await learn.learn("I think I like my town a lot honestly", "Nice") == []
    assert live(memory) == ["Lives in Austin"]


async def test_reply_wrapped_in_a_code_fence_and_chatter_still_parses(memory):
    learn, _ = learner(memory, 'Here you go:\n```json\n{"ops": [{"op": "add", "kind": "fact", "text": "Plays bass guitar"}]}\n```\nDone!')
    await learn.learn("I play bass guitar in a band", "Cool")
    assert live(memory) == ["Plays bass guitar"]


async def test_tiny_messages_are_skipped_without_calling_the_model(memory):
    learn, router = learner(memory)
    assert await learn.learn("ok thanks", "np") == []
    assert router.calls == []


async def test_a_model_outage_does_not_break_anything(memory):
    learn, _ = learner(memory)  # no scripted replies, the call raises
    assert await learn.learn("I started a new job at the bike shop", "Congrats") == []


async def test_new_memories_get_meaning_vectors_when_possible(memory):
    learn, _ = learner(
        memory, {"ops": [{"op": "add", "kind": "fact", "text": "Has a sister named Ana"}]},
        embedder=lambda t: np.array([1.0, 0.0]),
    )
    await learn.learn("my sister Ana is visiting this weekend", "Fun")
    assert memory.missing_vectors("fake:emb") == []


async def test_every_change_is_logged_so_it_can_be_explained(memory):
    learn, _ = learner(memory, {"ops": [{"op": "add", "kind": "fact", "text": "Has a sister named Ana"}]})
    await learn.learn("my sister Ana is visiting this weekend", "Fun")
    event = memory.events()[0]
    assert event["kind"] == "learn" and event["op"] == "add"


def test_parse_json_finds_the_object_inside_noise():
    assert parse_json('blah {"a": {"b": 1}} trailing') == {"a": {"b": 1}}
    assert parse_json("no json") is None


async def test_consolidate_summarizes_long_sessions_once(memory):
    sid = memory.ensure_session(None)
    for i in range(10):
        memory.add_message(sid, "user" if i % 2 == 0 else "assistant", f"message {i}")
    router = FakeRouter(roles={"small": ["Talked about ten messages."]})
    report = await consolidate(memory, router)
    assert memory.session(sid)["summary"] == "Talked about ten messages."
    assert report["summaries"] == 1
    assert (await consolidate(memory, router))["summaries"] == 0  # nothing new to summarize


async def test_consolidate_backfills_missing_vectors(memory):
    memory.add("fact", "Has a sister named Ana")
    router = FakeRouter(embedder=lambda t: np.array([0.5, 0.5]))
    report = await consolidate(memory, router)
    assert report["embedded"] == 1 and memory.missing_vectors("fake:emb") == []


async def test_consolidate_merges_duplicates_into_the_stronger_one(memory):
    a = memory.add("fact", "Favorite band is Radiohead", confidence=0.5)
    b = memory.add("fact", "favorite band is radiohead!", confidence=0.9)
    report = await consolidate(memory, FakeRouter())
    assert report["merged"] == 1 and [m.id for m in memory.list()] == [b]
    assert memory.get(a).superseded_by == b
