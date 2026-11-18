import time

import numpy as np

from anexis.memory.store import DAY


def texts(results):
    return [r.text for r in results]


def test_search_finds_a_memory_by_its_words(memory):
    memory.add("fact", "Chemistry lab is on Thursday afternoons")
    memory.add("fact", "Favorite food is ramen")
    assert texts(memory.search("when is chemistry lab")) [0] == "Chemistry lab is on Thursday afternoons"


def test_search_survives_quotes_and_punctuation(memory):
    memory.add("fact", "The essay is due Friday")
    assert texts(memory.search('what\'s "due"? (AND) OR NOT *')) == ["The essay is due Friday"]


def test_search_with_no_matching_words_returns_nothing(memory):
    memory.add("fact", "Favorite food is ramen")
    assert memory.search("quantum physics") == []


def test_more_confident_memory_ranks_first(memory):
    memory.add("fact", "Gym days are Monday", confidence=0.3)
    memory.add("fact", "Gym days are Tuesday", confidence=0.9)
    assert texts(memory.search("gym days"))[0] == "Gym days are Tuesday"


def test_a_correction_outranks_a_plain_fact(memory):
    memory.add("fact", "Code style uses tabs sometimes")
    memory.add("lesson", "Code style: always use spaces")
    assert texts(memory.search("code style"))[0] == "Code style: always use spaces"


def test_reinforce_raises_confidence_but_never_past_one(memory):
    mid = memory.add("fact", "Works at the bike shop", confidence=0.6)
    memory.reinforce(mid)
    once = memory.get(mid).confidence
    for _ in range(50):
        memory.reinforce(mid)
    assert 0.6 < once < 1.0
    assert memory.get(mid).confidence <= 1.0


def test_supersede_hides_the_old_memory_and_keeps_it_linked(memory):
    old = memory.add("fact", "Lives in Austin", pinned=True, source="about_me")
    new = memory.supersede(old, "Lives in Denver")
    assert texts(memory.search("lives")) == ["Lives in Denver"]
    assert memory.get(old).superseded_by == new
    assert memory.get(new).pinned and memory.get(new).source == "about_me"


def test_forget_removes_a_memory(memory):
    mid = memory.add("fact", "Secret crush is Sam")
    assert memory.forget(mid) is True
    assert memory.search("crush") == [] and memory.get(mid) is None
    assert memory.forget(mid) is False


def test_vector_search_finds_meaning_without_shared_words(memory):
    a = memory.add("fact", "Enjoys long distance running")
    b = memory.add("fact", "Allergic to peanuts")
    memory.set_vector(a, "m", np.array([1.0, 0.0, 0.0]))
    memory.set_vector(b, "m", np.array([0.0, 1.0, 0.0]))
    found = memory.search("marathon training", query_vec=np.array([0.9, 0.1, 0.0]), model="m")
    assert texts(found)[0] == "Enjoys long distance running"


def test_vectors_from_another_embedding_model_are_ignored(memory):
    a = memory.add("fact", "Enjoys long distance running")
    memory.set_vector(a, "old-model", np.array([1.0, 0.0]))
    assert memory.search("marathon", query_vec=np.array([1.0, 0.0, 0.0]), model="new-model") == []


def test_using_a_memory_makes_it_rank_above_an_unused_twin(memory):
    a = memory.add("fact", "Study spot is the library")
    b = memory.add("fact", "Study spot is the cafe")
    for _ in range(5):
        memory.mark_used([b])
    assert memory.search("study spot")[0].id == b
    assert memory.get(b).use_count == 5 and memory.get(a).use_count == 0


def test_decay_lowers_stale_memories_and_spares_pinned_and_fresh_ones(memory):
    old = time.time() - 90 * DAY
    stale = memory.add("fact", "Stale thing", confidence=0.8, now=old)
    pinned = memory.add("fact", "Pinned thing", confidence=0.8, pinned=True, now=old)
    fresh = memory.add("fact", "Fresh thing", confidence=0.8)
    assert memory.decay() == 1
    assert memory.get(stale).confidence < 0.8
    assert memory.get(pinned).confidence == 0.8 and memory.get(fresh).confidence == 0.8


def test_decay_never_drops_a_memory_below_the_floor(memory):
    mid = memory.add("fact", "Old thing", confidence=0.25, now=time.time() - 400 * DAY)
    for _ in range(100):
        memory.decay()
    assert memory.get(mid).confidence >= 0.2


def test_pinned_lists_only_live_pinned_memories(memory):
    memory.add("fact", "Age is 19", pinned=True, source="about_me")
    memory.add("fact", "Random thing")
    assert texts(memory.pinned()) == ["Age is 19"]


def test_find_duplicate_matches_same_words_in_a_different_order_or_case(memory):
    mid = memory.add("preference", "Prefers dark mode in every editor")
    assert memory.find_duplicate("prefers Dark Mode in every editor.") == mid
    assert memory.find_duplicate("Prefers tea over coffee") is None


def test_messages_come_back_oldest_first_and_limited(memory):
    sid = memory.ensure_session(None, "school")
    for i in range(5):
        memory.add_message(sid, "user", f"m{i}")
    assert [m["content"] for m in memory.history(sid, limit=3)] == ["m2", "m3", "m4"]
    assert memory.session(sid)["mode"] == "school"


def test_tool_stats_count_calls_and_failures(memory):
    memory.record_tool("shell", ok=True, ms=10)
    memory.record_tool("shell", ok=False, ms=30)
    s = memory.tool_stats()["shell"]
    assert (s["calls"], s["failures"]) == (2, 1)


def test_data_survives_reopening_the_database(settings):
    from anexis.memory.store import Memory

    m = Memory(settings.db_path)
    m.add("fact", "Persists across restarts")
    m.kv_set("k", {"a": 1})
    m.close()
    m2 = Memory(settings.db_path)
    assert texts(m2.search("persists")) == ["Persists across restarts"]
    assert m2.kv_get("k") == {"a": 1}
    m2.close()


def test_a_change_made_by_another_process_is_seen_without_a_restart(settings):
    from anexis.memory.store import Memory

    server, trainer = Memory(settings.db_path), Memory(settings.db_path)
    server.add("fact", "Favorite food is ramen")
    assert server.search("discrod") == []  # warms the server's word list
    trainer.add("project", "Building a Discord bot in Python")
    assert [m.text for m in server.search("my discrod bot")] == ["Building a Discord bot in Python"]
    server.close()
    trainer.close()
