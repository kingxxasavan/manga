"""Greg's memory: one SQLite file holding conversations and everything learned.

Nothing here talks to a model. Extraction lives in learn.py, upkeep in
consolidate.py. This file is storage, search and ranking.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DAY = 86400.0
KINDS = ("fact", "preference", "habit", "project", "class", "person", "task", "lesson")
CONFIDENCE_FLOOR = 0.2
STALE_AFTER_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  started_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  mode TEXT NOT NULL DEFAULT 'general',
  summary TEXT NOT NULL DEFAULT '',
  summarized_upto INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  meta TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_session ON messages (session_id, id);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  confidence REAL NOT NULL,
  importance REAL NOT NULL,
  source TEXT NOT NULL,
  key TEXT,
  pinned INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  last_used_at REAL,
  use_count INTEGER NOT NULL DEFAULT 0,
  superseded_by INTEGER
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  text, content='memories', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TABLE IF NOT EXISTS memory_vectors (
  memory_id INTEGER PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  vec BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_stats (
  tool TEXT PRIMARY KEY,
  calls INTEGER NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0,
  total_ms REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  at REAL NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  due_at TEXT,
  done INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

STOPWORDS = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "does", "for", "from", "had", "has", "have", "how", "i", "if", "in", "is", "it", "its", "me", "my", "of", "on", "or", "so", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to", "was", "we", "were", "what", "when", "where", "which", "who", "why", "will", "with", "you", "your", "not", "no", "can", "could", "should", "would", "s", "t", "im"]
)
_WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> list[str]:
    """Meaningful lowercase words of a text, used for search and duplicate checks."""
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]


@dataclass
class MemoryRow:
    id: int
    kind: str
    text: str
    confidence: float
    importance: float
    source: str
    key: str | None
    pinned: bool
    created_at: float
    updated_at: float
    last_used_at: float | None
    use_count: int
    superseded_by: int | None
    score: float = 0.0

    def public(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "pinned": self.pinned,
            "use_count": self.use_count,
        }


def quality(row: MemoryRow, now: float) -> float:
    """How much to trust and prefer a memory, apart from how well it matches.

    Sure, important, recently useful and often useful memories rank higher.
    Corrections ("lesson") get a boost because the owner said them on purpose.
    """
    seen = row.last_used_at or row.updated_at
    age_days = max(0.0, (now - seen) / DAY)
    recency = 0.75 + 0.25 * math.exp(-age_days / 30)
    usage = 1 + 0.15 * math.log1p(row.use_count)
    kind = 1.3 if row.kind == "lesson" else 1.0
    return (0.4 + 0.6 * row.confidence) * (0.7 + 0.3 * row.importance) * recency * usage * kind


class Memory:
    def __init__(self, path: Path | str, readonly: bool = False):
        self.path = Path(path)
        if readonly:
            self.db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, check_same_thread=False)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript(SCHEMA)
            self.db.commit()
        self.db.row_factory = sqlite3.Row
        self._vec_cache: dict[str, tuple[list[int], np.ndarray]] = {}

    def close(self) -> None:
        self.db.close()

    # ---- sessions and messages -------------------------------------------

    def ensure_session(self, session_id: str | None, mode: str | None = None) -> str:
        now = time.time()
        sid = session_id or uuid.uuid4().hex[:12]
        self.db.execute(
            "INSERT OR IGNORE INTO sessions (id, started_at, updated_at, mode) VALUES (?,?,?,?)",
            (sid, now, now, mode or "general"),
        )
        if mode:
            self.db.execute("UPDATE sessions SET mode=? WHERE id=?", (mode, sid))
        self.db.commit()
        return sid

    def session(self, session_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def add_message(self, session_id: str, role: str, content: str, meta: dict | None = None) -> int:
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO messages (session_id, role, content, meta, created_at) VALUES (?,?,?,?,?)",
            (session_id, role, content, json.dumps(meta or {}), now),
        )
        self.db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
        self.db.commit()
        return cur.lastrowid

    def history(self, session_id: str, limit: int = 24, after_id: int = 0) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, role, content, meta FROM messages WHERE session_id=? AND id>? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, after_id, limit),
        ).fetchall()
        return [
            {"id": r["id"], "role": r["role"], "content": r["content"], "meta": json.loads(r["meta"])}
            for r in reversed(rows)
        ]

    def last_message(self, session_id: str, role: str) -> dict | None:
        row = self.db.execute(
            "SELECT id, content, meta FROM messages WHERE session_id=? AND role=? "
            "ORDER BY id DESC LIMIT 1",
            (session_id, role),
        ).fetchone()
        return {"id": row["id"], "content": row["content"], "meta": json.loads(row["meta"])} if row else None

    def sessions_needing_summary(self, min_new: int = 8) -> list[dict]:
        rows = self.db.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id "
            "AND m.id>s.summarized_upto) AS fresh FROM sessions s"
        ).fetchall()
        return [dict(r) for r in rows if r["fresh"] >= min_new]

    def set_summary(self, session_id: str, summary: str, upto: int) -> None:
        self.db.execute(
            "UPDATE sessions SET summary=?, summarized_upto=? WHERE id=?", (summary, upto, session_id)
        )
        self.db.commit()

    # ---- memories ---------------------------------------------------------

    def add(
        self,
        kind: str,
        text: str,
        *,
        confidence: float = 0.6,
        importance: float = 0.5,
        source: str = "learned",
        pinned: bool = False,
        key: str | None = None,
        now: float | None = None,
    ) -> int:
        if kind not in KINDS:
            kind = "fact"
        now = now or time.time()
        cur = self.db.execute(
            "INSERT INTO memories (kind, text, confidence, importance, source, key, pinned, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (kind, text.strip(), _clamp(confidence), _clamp(importance), source, key, int(pinned), now, now),
        )
        self.db.commit()
        return cur.lastrowid

    def get(self, memory_id: int) -> MemoryRow | None:
        row = self.db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return _row(row) if row else None

    def list(self, kind: str | None = None, limit: int = 50, source: str | None = None) -> list[MemoryRow]:
        sql = "SELECT * FROM memories WHERE superseded_by IS NULL"
        args: list = []
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if source:
            sql += " AND source=?"
            args.append(source)
        rows = self.db.execute(sql + " ORDER BY updated_at DESC LIMIT ?", (*args, limit)).fetchall()
        return [_row(r) for r in rows]

    def count(self) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM memories WHERE superseded_by IS NULL"
        ).fetchone()[0]

    def pinned(self) -> list[MemoryRow]:
        rows = self.db.execute(
            "SELECT * FROM memories WHERE pinned=1 AND superseded_by IS NULL ORDER BY id"
        ).fetchall()
        return [_row(r) for r in rows]

    def by_key(self, key: str) -> MemoryRow | None:
        row = self.db.execute(
            "SELECT * FROM memories WHERE key=? AND superseded_by IS NULL", (key,)
        ).fetchone()
        return _row(row) if row else None

    def reinforce(self, memory_id: int) -> None:
        """Seeing the same thing again closes 30 percent of the gap to certain."""
        self.db.execute(
            "UPDATE memories SET confidence=MIN(1.0, confidence + (1.0-confidence)*0.3), "
            "updated_at=? WHERE id=?",
            (time.time(), memory_id),
        )
        self.db.commit()

    def supersede(self, old_id: int, text: str, kind: str | None = None) -> int:
        """Replace a memory that changed. The old row is kept and points at the new one."""
        old = self.get(old_id)
        if old is None:
            raise KeyError(old_id)
        new_id = self.add(
            kind or old.kind,
            text,
            confidence=max(old.confidence, 0.7),
            importance=old.importance,
            source=old.source,
            pinned=old.pinned,
            key=old.key,
        )
        self.db.execute("UPDATE memories SET superseded_by=?, key=NULL WHERE id=?", (new_id, old_id))
        self.db.commit()
        self._vec_cache.clear()
        return new_id

    def forget(self, memory_id: int) -> bool:
        """Owner asked for it to be gone, so it is really deleted."""
        cur = self.db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        self.db.execute("UPDATE memories SET superseded_by=NULL WHERE superseded_by=?", (memory_id,))
        self.db.commit()
        self._vec_cache.clear()
        return cur.rowcount > 0

    def mark_used(self, ids: list[int]) -> None:
        now = time.time()
        self.db.executemany(
            "UPDATE memories SET use_count=use_count+1, last_used_at=? WHERE id=?",
            [(now, i) for i in ids],
        )
        self.db.commit()

    def decay(self) -> int:
        """Lower confidence a little on memories nobody has needed for a month.

        Pinned memories never decay and nothing drops below the floor, so decay
        only ever changes ranking. It never removes anything.
        """
        cutoff = time.time() - STALE_AFTER_DAYS * DAY
        cur = self.db.execute(
            "UPDATE memories SET confidence=MAX(?, confidence*0.97) "
            "WHERE pinned=0 AND superseded_by IS NULL AND confidence>? "
            "AND COALESCE(last_used_at, updated_at) < ?",
            (CONFIDENCE_FLOOR, CONFIDENCE_FLOOR, cutoff),
        )
        self.db.commit()
        return cur.rowcount

    def find_duplicate(
        self, text: str, vec: np.ndarray | None = None, model: str | None = None, exclude: int | None = None
    ) -> int | None:
        """Id of a live memory that says the same thing, if there is one."""
        target = set(words(text))
        if not target:
            return None
        for row in self._fts(text, 8):
            other = set(words(row.text))
            if row.id != exclude and other and len(target & other) / len(target | other) >= 0.8:
                return row.id
        if vec is not None and model:
            for memory_id, similarity in self._nearest(vec, model, 2):
                if memory_id != exclude and similarity >= 0.92:
                    return memory_id
        return None

    def merge(self, weak_id: int, strong_id: int) -> None:
        """Fold a duplicate into the stronger copy. The weak row is kept as history."""
        self.db.execute("UPDATE memories SET superseded_by=? WHERE id=?", (strong_id, weak_id))
        self.db.commit()
        self._vec_cache.clear()
        self.reinforce(strong_id)

    # ---- vectors ----------------------------------------------------------

    def set_vector(self, memory_id: int, model: str, vec) -> None:
        arr = np.asarray(vec, dtype=np.float32)
        self.db.execute(
            "INSERT OR REPLACE INTO memory_vectors (memory_id, model, vec) VALUES (?,?,?)",
            (memory_id, model, arr.tobytes()),
        )
        self.db.commit()
        self._vec_cache.pop(model, None)

    def missing_vectors(self, model: str, limit: int = 64) -> list[MemoryRow]:
        rows = self.db.execute(
            "SELECT m.* FROM memories m LEFT JOIN memory_vectors v "
            "ON v.memory_id=m.id AND v.model=? "
            "WHERE v.memory_id IS NULL AND m.superseded_by IS NULL LIMIT ?",
            (model, limit),
        ).fetchall()
        return [_row(r) for r in rows]

    def _matrix(self, model: str) -> tuple[list[int], np.ndarray]:
        if model not in self._vec_cache:
            rows = self.db.execute(
                "SELECT v.memory_id, v.vec FROM memory_vectors v JOIN memories m ON m.id=v.memory_id "
                "WHERE v.model=? AND m.superseded_by IS NULL",
                (model,),
            ).fetchall()
            ids = [r["memory_id"] for r in rows]
            if rows:
                mat = np.vstack([np.frombuffer(r["vec"], dtype=np.float32) for r in rows])
                mat = mat / np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)
            else:
                mat = np.zeros((0, 0), dtype=np.float32)
            self._vec_cache[model] = (ids, mat)
        return self._vec_cache[model]

    def _nearest(self, vec, model: str, k: int) -> list[tuple[int, float]]:
        ids, mat = self._matrix(model)
        query = np.asarray(vec, dtype=np.float32)
        if not ids or mat.shape[1] != query.shape[0]:
            return []
        sims = mat @ (query / max(float(np.linalg.norm(query)), 1e-9))
        order = np.argsort(-sims)[:k]
        return [(ids[i], float(sims[i])) for i in order]

    # ---- search -----------------------------------------------------------

    def _fts(self, query: str, k: int) -> list[MemoryRow]:
        terms = list(dict.fromkeys(words(query)))[:24]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        rows = self.db.execute(
            "SELECT m.* FROM memories_fts f JOIN memories m ON m.id=f.rowid "
            "WHERE memories_fts MATCH ? AND m.superseded_by IS NULL ORDER BY bm25(memories_fts) LIMIT ?",
            (match, k),
        ).fetchall()
        return [_row(r) for r in rows]

    def search(
        self,
        query: str,
        k: int = 8,
        query_vec=None,
        model: str | None = None,
        min_similarity: float = 0.3,
    ) -> list[MemoryRow]:
        """Best matching memories: word match and meaning match fused, then
        weighted by how trustworthy and useful each memory has been."""
        relevance: dict[int, float] = {}
        found: dict[int, MemoryRow] = {}
        for rank, row in enumerate(self._fts(query, k * 3)):
            relevance[row.id] = relevance.get(row.id, 0.0) + 1.0 / (10 + rank)
            found[row.id] = row
        if query_vec is not None and model:
            hits = [h for h in self._nearest(query_vec, model, k * 3) if h[1] >= min_similarity]
            for rank, (memory_id, _) in enumerate(hits):
                relevance[memory_id] = relevance.get(memory_id, 0.0) + 1.0 / (10 + rank)
                if memory_id not in found:
                    row = self.get(memory_id)
                    if row:
                        found[memory_id] = row
        now = time.time()
        for memory_id, row in found.items():
            row.score = relevance[memory_id] * quality(row, now)
        return sorted(found.values(), key=lambda r: -r.score)[:k]

    # ---- tool stats, events, key value ------------------------------------

    def record_tool(self, tool: str, ok: bool, ms: float) -> None:
        self.db.execute(
            "INSERT INTO tool_stats (tool, calls, failures, total_ms) VALUES (?,1,?,?) "
            "ON CONFLICT(tool) DO UPDATE SET calls=calls+1, failures=failures+excluded.failures, "
            "total_ms=total_ms+excluded.total_ms",
            (tool, 0 if ok else 1, ms),
        )
        self.db.commit()

    def tool_stats(self) -> dict[str, dict]:
        return {r["tool"]: dict(r) for r in self.db.execute("SELECT * FROM tool_stats")}

    def log(self, kind: str, detail: dict) -> None:
        self.db.execute(
            "INSERT INTO events (at, kind, detail) VALUES (?,?,?)",
            (time.time(), kind, json.dumps(detail)),
        )
        self.db.commit()

    def events(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        # The event's own kind wins over any "kind" field inside the detail.
        return [{**json.loads(r["detail"]), "at": r["at"], "kind": r["kind"]} for r in rows]

    def kv_get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def kv_set(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?,?)", (key, json.dumps(value)))
        self.db.commit()


def _clamp(value) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _row(r: sqlite3.Row) -> MemoryRow:
    return MemoryRow(
        id=r["id"],
        kind=r["kind"],
        text=r["text"],
        confidence=r["confidence"],
        importance=r["importance"],
        source=r["source"],
        key=r["key"],
        pinned=bool(r["pinned"]),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        last_used_at=r["last_used_at"],
        use_count=r["use_count"],
        superseded_by=r["superseded_by"],
    )
