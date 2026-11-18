import time

import pytest

from anexis.memory.store import Memory
from anexis.memory.sync import answer, apply, export, sync_with
from anexis.profile.about import export_profile, import_profile


@pytest.fixture
def two(tmp_path):
    """The school server's memory and the PC's memory."""
    school, pc = Memory(tmp_path / "school.db"), Memory(tmp_path / "pc.db")
    yield school, pc
    school.close()
    pc.close()


def swap(school, pc):
    """One sync the way the PC does it, without the network in between."""
    sent_upto = time.time()
    reply = answer(school, pc.kv_get("received", 0.0), export(pc, pc.kv_get("sent", 0.0)))
    got = apply(pc, reply["changes"])
    pc.kv_set("sent", sent_upto)
    pc.kv_set("received", reply["now"])
    return got


def texts(memory):
    return sorted(m.text for m in memory.list(None, 500))


def test_what_each_side_learned_ends_up_on_both(two):
    school, pc = two
    school.add("fact", "Has a chem lab on Thursday")
    pc.add("preference", "Likes the black theme")
    swap(school, pc)
    assert texts(school) == texts(pc) == ["Has a chem lab on Thursday", "Likes the black theme"]
    assert swap(school, pc) == {"memories": 0, "items": 0, "messages": 0, "sessions": 0, "deleted": 0}  # nothing twice
    assert len(school.list(None, 500)) == 2


def test_the_same_fact_made_on_both_sides_is_one_memory(two):
    from anexis.profile.seed import seed_owner

    school, pc = two
    seed_owner(school)
    seed_owner(pc)
    count = school.count()
    swap(school, pc)
    swap(school, pc)
    assert school.count() == pc.count() == count
    assert sorted(m.text for m in school.list(None, 500)) == sorted(m.text for m in pc.list(None, 500))
    uids = lambda mem: {r["uid"] for r in mem.db.execute("SELECT uid FROM memories")}  # noqa: E731
    assert uids(school) == uids(pc)


def test_a_change_replaces_the_old_fact_on_the_other_side_too(two):
    school, pc = two
    old = pc.add("task", "History essay due Friday")
    swap(school, pc)
    time.sleep(0.01)
    pc.supersede(old, "History essay due Monday")
    swap(school, pc)
    live = [m.text for m in school.list(None, 500) if not school.db.execute("SELECT superseded_by FROM memories WHERE id=?", (m.id,)).fetchone()[0]]
    assert "History essay due Monday" in live and "History essay due Friday" not in live
    assert school.search("essay monday", 3)[0].text == "History essay due Monday"  # the search index followed


def test_forgetting_on_one_side_forgets_on_both(two):
    school, pc = two
    memory_id = school.add("fact", "Secret crush on someone")
    swap(school, pc)
    assert "Secret crush on someone" in texts(pc)
    school.forget(memory_id)
    swap(school, pc)
    assert "Secret crush on someone" not in texts(pc)
    swap(school, pc)  # and it does not come back from the PC
    assert "Secret crush on someone" not in texts(school)


def test_chats_from_school_show_up_on_the_pc_and_clearing_one_clears_both(two):
    school, pc = two
    sid = school.ensure_session(None, "school")
    school.add_message(sid, "user", "whats due tomorrow")
    school.add_message(sid, "assistant", "The chem lab.")
    swap(school, pc)
    assert [m["content"] for m in pc.history(sid, 10)] == ["whats due tomorrow", "The chem lab."]
    assert pc.list_sessions()[0]["title"] == "whats due tomorrow"
    pc.delete_session(sid)
    swap(school, pc)
    assert school.session(sid) is None and school.history(sid, 10) == []


def test_assignments_sync_and_the_newer_change_wins(two):
    school, pc = two
    pc.db.execute("INSERT INTO items (type, title, due_at, created_at) VALUES ('assignment', 'Lab 3', '2026-11-20', ?)", (time.time(),))
    pc.db.commit()
    swap(school, pc)
    assert [tuple(r) for r in school.db.execute("SELECT title, done FROM items")] == [("Lab 3", 0)]
    time.sleep(0.01)
    school.db.execute("UPDATE items SET done=1 WHERE title='Lab 3'")
    school.db.commit()
    swap(school, pc)
    assert pc.db.execute("SELECT done FROM items WHERE title='Lab 3'").fetchone()[0] == 1


def test_canvas_assignments_read_on_both_sides_are_one_row(two):
    school, pc = two
    for mem in two:  # both read the same Canvas assignment on their own
        mem.db.execute("INSERT INTO items (uid, type, title, created_at) VALUES ('canvas:assignment:501', 'assignment', 'Lab 3', ?)", (time.time(),))
        mem.db.commit()
    swap(school, pc)
    assert school.db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == pc.db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_about_me_answers_given_at_school_show_on_the_pc(two):
    school, pc = two
    import_profile(school, {"name": "Sam", "classes": ["Chem 101"]})
    swap(school, pc)
    assert export_profile(pc) == {"name": "Sam", "classes": ["Chem 101"]}
    assert "Name: Sam" in texts(pc)


def test_older_changes_never_win(two):
    school, pc = two
    mid = school.add("fact", "Works at the bike shop")
    swap(school, pc)
    stale = export(school, 0.0)
    time.sleep(0.01)
    row = pc.db.execute("SELECT id FROM memories WHERE text='Works at the bike shop'").fetchone()
    pc.supersede(row[0], "Works at the bookstore now")
    apply(pc, stale)  # an old copy arriving late changes nothing
    assert "Works at the bookstore now" in texts(pc)
    assert school.get(mid).text == "Works at the bike shop"


async def test_the_pc_syncs_with_a_real_school_server_and_both_learn(live, settings, tmp_path):
    school_app, client = await live()
    school_app.memory.add("fact", "Said at school: likes physics")
    pc = Memory(tmp_path / "pc.db")
    try:
        pc.add("fact", "Said at home: plays guitar")
        report = await sync_with(pc, client.url, settings.token)
        assert report["ok"] and report["received"]["memories"] == 1 and report["sent"]["memories"] == 1
        assert "Said at school: likes physics" in texts(pc)
        assert "Said at home: plays guitar" in texts(school_app.memory)
        again = await sync_with(pc, client.url, settings.token)
        assert again["received"]["memories"] == 0 and not again["sent"]
    finally:
        pc.close()


async def test_a_wrong_school_token_is_explained(live, settings, tmp_path):
    settings.token = "school-secret"
    _, client = await live()
    pc = Memory(tmp_path / "pc.db")
    try:
        with pytest.raises(PermissionError, match="school server token"):
            await sync_with(pc, client.url, "wrong")
    finally:
        pc.close()


async def test_sync_now_reports_a_school_server_that_cannot_be_reached(live, settings):
    anexis, _ = await live()
    anexis.settings.env = {"ANEXIS_SYNC_URL": "http://127.0.0.1:9"}
    report = await anexis.sync_now()
    assert report["ok"] is False and "Connect" in report["error"]
    anexis.settings.env = {}
    assert "No school server" in (await anexis.sync_now())["error"]


def test_an_older_database_gets_the_sync_columns(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE items (id INTEGER PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', "
                      "due_at TEXT, done INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);"
                      "INSERT INTO items (type, title, created_at) VALUES ('todo', 'old one', 1.0);")
    old.commit()
    old.close()
    upgraded = Memory(path)
    try:
        row = upgraded.db.execute("SELECT uid, updated_at FROM items").fetchone()
        assert row["uid"] and row["updated_at"] == 1.0
    finally:
        upgraded.close()
