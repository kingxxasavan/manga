"""Keeps two copies of Anexis in step: the school server and the PC app.

Each side keeps its own memory, so either one works on its own. When the PC
starts (and every so often after), it sends the school server what changed on
the PC since last time, and gets back what changed at school. Both apply what
they got, and then both know the same things.

What travels: memories (About Me included), assignments and other items,
chats, and the About Me answers. A row is the same row on both sides through
its `uid`. When both sides changed the same row, the newer change wins. A
deleted row leaves a note (a tombstone) so it is deleted on the other side too.
"""

from __future__ import annotations

import json
import time

import httpx

from anexis.profile.about import STORE_KEY

LOCAL_CURSOR = "sync_sent_upto"      # our own clock: changes before this were sent
REMOTE_CURSOR = "sync_received_upto"  # the other side's clock: changes before this were received
LAST_SYNC = "sync_last"
KV_SYNCED = (STORE_KEY,)  # kv values worth carrying across: the About Me answers

MEMORY_FIELDS = ("uid", "kind", "text", "confidence", "importance", "source", "key", "pinned", "created_at", "updated_at")
ITEM_FIELDS = ("uid", "type", "title", "body", "due_at", "done", "created_at", "updated_at")


def export(memory, since: float) -> dict:
    """Everything that changed here after `since` (this side's clock)."""
    db = memory.db
    uid_of = {r["id"]: r["uid"] for r in db.execute("SELECT id, uid FROM memories")}
    memories = []
    for r in db.execute(f"SELECT id, superseded_by, {', '.join(MEMORY_FIELDS)} FROM memories WHERE updated_at > ?", (since,)):
        row = {f: r[f] for f in MEMORY_FIELDS}
        row["superseded_by"] = uid_of.get(r["superseded_by"]) if r["superseded_by"] else None
        memories.append(row)
    items = [{f: r[f] for f in ITEM_FIELDS} for r in db.execute(f"SELECT {', '.join(ITEM_FIELDS)} FROM items WHERE updated_at > ?", (since,))]
    sessions = [dict(r) for r in db.execute(
        "SELECT id, mode, summary, started_at, updated_at FROM sessions WHERE updated_at > ?", (since,))]
    messages = [dict(r) for r in db.execute(
        "SELECT uid, session_id, role, content, meta, created_at FROM messages WHERE created_at > ? ORDER BY id", (since,))]
    tombstones = [dict(r) for r in db.execute("SELECT uid, kind, at FROM tombstones WHERE at > ?", (since,))]
    kv = [{"key": r["key"], "value": json.loads(r["value"]), "at": r["at"]} for r in db.execute(
        f"SELECT kv.key, kv.value, kv_times.at FROM kv JOIN kv_times USING (key) WHERE kv_times.at > ? AND kv.key IN ({','.join('?' * len(KV_SYNCED))})",
        (since, *KV_SYNCED))]
    return {"memories": memories, "items": items, "sessions": sessions, "messages": messages, "tombstones": tombstones, "kv": kv}


def _memory_row(db, uid: str):
    return db.execute("SELECT * FROM memories WHERE uid=?", (uid,)).fetchone()


def apply(memory, changes: dict) -> dict:
    """Takes in what changed on the other side. Safe to run twice with the same
    changes: nothing is added twice and older changes never win."""
    db = memory.db
    report = {"memories": 0, "items": 0, "messages": 0, "sessions": 0, "deleted": 0}
    gone = {t["uid"] for t in changes.get("tombstones", [])}

    # ---- memories -------------------------------------------------------------
    links = []
    for m in changes.get("memories", []):
        if m["uid"] in gone:
            continue
        here = _memory_row(db, m["uid"])
        if here is None and m.get("key"):
            # The same fact made on both sides on its own (About Me, what the
            # owner said). It is one memory: both sides settle on the smaller uid.
            twin = db.execute("SELECT * FROM memories WHERE key=? AND superseded_by IS NULL", (m["key"],)).fetchone()
            if twin is not None:
                if m["uid"] < twin["uid"]:
                    db.execute("UPDATE memories SET uid=? WHERE id=?", (m["uid"], twin["id"]))
                here = _memory_row(db, min(m["uid"], twin["uid"]))
                m = {**m, "uid": here["uid"]}
        if here is None:
            db.execute(
                f"INSERT INTO memories ({', '.join(MEMORY_FIELDS)}) VALUES ({', '.join('?' * len(MEMORY_FIELDS))})",
                tuple(m.get(f) for f in MEMORY_FIELDS))
            report["memories"] += 1
        elif m["updated_at"] > here["updated_at"]:
            if m["text"] != here["text"]:
                # The search index follows the text by hand: it has no update trigger.
                db.execute("INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', ?, ?)", (here["id"], here["text"]))
                db.execute("INSERT INTO memories_fts(rowid, text) VALUES (?, ?)", (here["id"], m["text"]))
                db.execute("DELETE FROM memory_vectors WHERE memory_id=?", (here["id"],))  # embedded again later
            sets = [f for f in MEMORY_FIELDS if f != "uid"]
            db.execute(f"UPDATE memories SET {', '.join(f + '=?' for f in sets)} WHERE id=?",
                       (*(m.get(f) for f in sets), here["id"]))
            report["memories"] += 1
        links.append((m, None))
    for m, _ in links:  # second pass: "replaced by" points at a row that may have just arrived
        if not m.get("superseded_by"):
            continue
        target = _memory_row(db, m["superseded_by"])
        own = _memory_row(db, m["uid"])
        if target is not None and own is not None and own["updated_at"] <= m["updated_at"]:
            db.execute("UPDATE memories SET superseded_by=?, updated_at=? WHERE id=?", (target["id"], m["updated_at"], own["id"]))

    # ---- items: assignments, todos, notes, reminders ----------------------------
    for item in changes.get("items", []):
        if item["uid"] in gone:
            continue
        here = db.execute("SELECT * FROM items WHERE uid=?", (item["uid"],)).fetchone()
        if here is None:
            db.execute(f"INSERT INTO items ({', '.join(ITEM_FIELDS)}) VALUES ({', '.join('?' * len(ITEM_FIELDS))})",
                       tuple(item.get(f) for f in ITEM_FIELDS))
            report["items"] += 1
        elif item["updated_at"] > (here["updated_at"] or 0):
            sets = [f for f in ITEM_FIELDS if f != "uid"]
            db.execute(f"UPDATE items SET {', '.join(f + '=?' for f in sets)} WHERE uid=?",
                       (*(item.get(f) for f in sets), item["uid"]))
            report["items"] += 1

    # ---- chats ------------------------------------------------------------------
    for session in changes.get("sessions", []):
        if session["id"] in gone:
            continue
        here = db.execute("SELECT * FROM sessions WHERE id=?", (session["id"],)).fetchone()
        if here is None:
            db.execute("INSERT INTO sessions (id, started_at, updated_at, mode, summary) VALUES (?,?,?,?,?)",
                       (session["id"], session["started_at"], session["updated_at"], session["mode"], session["summary"]))
            report["sessions"] += 1
        elif session["updated_at"] > here["updated_at"]:
            db.execute("UPDATE sessions SET updated_at=?, mode=?, summary=CASE WHEN ?<>'' THEN ? ELSE summary END WHERE id=?",
                       (session["updated_at"], session["mode"], session["summary"], session["summary"], session["id"]))
    for message in changes.get("messages", []):
        if message["session_id"] in gone or db.execute("SELECT 1 FROM messages WHERE uid=?", (message["uid"],)).fetchone():
            continue
        if not db.execute("SELECT 1 FROM sessions WHERE id=?", (message["session_id"],)).fetchone():
            db.execute("INSERT INTO sessions (id, started_at, updated_at) VALUES (?,?,?)",
                       (message["session_id"], message["created_at"], message["created_at"]))
        db.execute("INSERT INTO messages (uid, session_id, role, content, meta, created_at) VALUES (?,?,?,?,?,?)",
                   (message["uid"], message["session_id"], message["role"], message["content"], message["meta"], message["created_at"]))
        report["messages"] += 1

    # ---- deletes ------------------------------------------------------------------
    for tomb in changes.get("tombstones", []):
        uid, kind = tomb["uid"], tomb["kind"]
        if kind == "memory":
            row = _memory_row(db, uid)
            if row is not None:
                db.execute("UPDATE memories SET superseded_by=NULL WHERE superseded_by=?", (row["id"],))
                db.execute("DELETE FROM memories WHERE id=?", (row["id"],))
                report["deleted"] += 1
        elif kind == "item":
            report["deleted"] += db.execute("DELETE FROM items WHERE uid=?", (uid,)).rowcount
        elif kind == "session":
            db.execute("DELETE FROM messages WHERE session_id=?", (uid,))
            report["deleted"] += db.execute("DELETE FROM sessions WHERE id=?", (uid,)).rowcount
        db.execute("INSERT OR IGNORE INTO tombstones (uid, kind, at) VALUES (?,?,?)", (uid, kind, tomb["at"]))

    # ---- About Me answers ---------------------------------------------------------
    for entry in changes.get("kv", []):
        if entry["key"] not in KV_SYNCED:
            continue
        here = db.execute("SELECT at FROM kv_times WHERE key=?", (entry["key"],)).fetchone()
        if here is None or entry["at"] > here["at"]:
            db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?,?)", (entry["key"], json.dumps(entry["value"])))
            db.execute("INSERT OR REPLACE INTO kv_times (key, at) VALUES (?,?)", (entry["key"], entry["at"]))
    db.commit()
    memory._vec_cache.clear()        # rows and texts may have changed under the caches
    memory._words_cache = None
    return report


def answer(memory, since: float, changes: dict) -> dict:
    """The school server's side of one sync: take the PC's changes, send back
    its own. `now` is read first, so nothing that happens meanwhile is missed."""
    now = time.time()
    outgoing = export(memory, since)
    report = apply(memory, changes or {})
    return {"now": now, "changes": outgoing, "applied": report}


async def sync_with(memory, url: str, token: str, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """The PC's side: send what changed here, take in what changed there."""
    started = time.time()
    outgoing = export(memory, memory.kv_get(LOCAL_CURSOR, 0.0))
    body = {"since": memory.kv_get(REMOTE_CURSOR, 0.0), "changes": outgoing}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10), transport=transport) as http:
        resp = await http.post(url.rstrip("/") + "/sync", json=body, headers=headers)
    if resp.status_code == 401:
        raise PermissionError("The school server refused the token. Check the school server token in Keys.")
    resp.raise_for_status()
    reply = resp.json()
    received = apply(memory, reply["changes"])
    memory.kv_set(LOCAL_CURSOR, started)
    memory.kv_set(REMOTE_CURSOR, reply["now"])
    sent = {k: len(v) for k, v in outgoing.items() if v}
    report = {"at": time.time(), "sent": sent, "received": received, "ok": True}
    memory.kv_set(LAST_SYNC, report)
    return report
