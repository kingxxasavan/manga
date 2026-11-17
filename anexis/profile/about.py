"""About Me: what the owner tells Anexis about themselves up front.

Each answer becomes a pinned memory, so it is always in front of the model and
never fades. The answers also stay searchable like any other memory.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from anexis.memory.store import Memory
from anexis.platform import private_file

PREFIX = "about_me."
STORE_KEY = "about_me"


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    question: str
    kind: str = "fact"
    many: bool = False


SECTIONS = [
    Section("name", "Name", "What should I call you?"),
    Section("age", "Age", "How old are you?"),
    Section("location", "Lives in", "Where do you live? City is enough."),
    Section("areas", "Area they spend time in", "What areas do you move around in? Neighborhoods, campus, commute.", many=True),
    Section("school", "School", "What school are you at, what year, and what are you studying?"),
    Section("classes", "Class this term", "Your classes this term, with days and times if you know them.", "class", True),
    Section("work", "Work", "Where do you work and what do you do there?"),
    Section("schedule", "Regular schedule", "Your normal week: work shifts, practice, anything fixed.", "habit", True),
    Section("projects", "Project", "Projects you are working on or want to start.", "project", True),
    Section("habits", "Habit", "Habits and routines, good or bad.", "habit", True),
    Section("goals", "Goal", "What are you trying to get done this year?", many=True),
    Section("interests", "Interest", "What are you into?", many=True),
    Section("people", "Person in their life", "People I should know about: name and who they are to you.", "person", True),
    Section("tools", "Uses", "Languages, apps and devices you use.", many=True),
    Section("talk_style", "How to talk to them", "How do you want me to talk to you?", "preference"),
    Section("avoid", "Never do", "Anything I should never do or bring up?", "lesson", True),
    Section("other", "Also", "Anything else I should know?", many=True),
]
BY_KEY = {s.key: s for s in SECTIONS}


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def _items(key: str, value) -> list[tuple[str, str, str]]:
    """One section's answer as (memory key, text, kind) rows."""
    section = BY_KEY.get(key) or Section(key, key.replace("_", " ").capitalize(), "")
    base = PREFIX + key
    if isinstance(value, dict):
        rows = []
        for sub, inner in value.items():
            joined = ", ".join(_clean(v) for v in inner) if isinstance(inner, list) else _clean(inner)
            if joined:
                rows.append((f"{base}.{sub}", f"{section.label} {str(sub).replace('_', ' ')}: {joined}", section.kind))
        return rows
    if isinstance(value, list):
        rows = []
        for entry in value:
            body = _clean(entry)
            if body:
                # Keyed by content, so reordering a list changes nothing.
                digest = hashlib.sha1(body.encode()).hexdigest()[:10]
                rows.append((f"{base}:{digest}", f"{section.label}: {body}", section.kind))
        return rows
    body = _clean(value)
    return [(base, f"{section.label}: {body}", section.kind)] if body else []


def _owned(memory: Memory, key: str) -> dict[str, int]:
    """Live About Me memories belonging to one section, by memory key."""
    base = PREFIX + key
    rows = memory.db.execute(
        "SELECT id, key FROM memories WHERE source='about_me' AND superseded_by IS NULL "
        "AND (key=? OR key LIKE ? OR key LIKE ?)",
        (base, base + ".%", base + ":%"),
    ).fetchall()
    return {r["key"]: r["id"] for r in rows}


def import_profile(memory: Memory, data: dict) -> dict:
    """Apply answers. Sections not in `data` are left alone.

    A section whose answer is the same as last time is skipped completely, so
    something Anexis has since learned in conversation (for example a move) is
    not overwritten by an old answer being sent again.
    """
    previous = memory.kv_get(STORE_KEY, {})
    report = {"added": 0, "changed": 0, "same": 0, "removed": 0}
    for key, value in data.items():
        key = str(key)
        rows = _items(key, value)
        if key in previous and previous[key] == value:
            report["same"] += len(rows)
            continue
        existing = _owned(memory, key)
        for memory_key, text, kind in rows:
            if memory_key in existing:
                current = memory.get(existing.pop(memory_key))
                if current.text == text:
                    report["same"] += 1
                else:
                    memory.supersede(current.id, text, kind)
                    report["changed"] += 1
            else:
                memory.add(kind, text, confidence=1.0, importance=0.8, source="about_me", pinned=True, key=memory_key)
                report["added"] += 1
        for leftover in existing.values():
            memory.forget(leftover)
            report["removed"] += 1
        if rows:
            previous[key] = value
        else:
            previous.pop(key, None)
    memory.kv_set(STORE_KEY, previous)
    return report


def export_profile(memory: Memory) -> dict:
    """The answers as last given, in section order."""
    stored = memory.kv_get(STORE_KEY, {})
    ordered = {s.key: stored[s.key] for s in SECTIONS if s.key in stored}
    ordered.update({k: v for k, v in stored.items() if k not in ordered})
    return ordered


def save_profile_file(home: Path, data: dict) -> Path:
    """A readable copy next to the database, private to the owner's user."""
    path = home / "about_me.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    private_file(path)
    return path


def load_profile_file(path: Path) -> dict:
    data = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("The About Me file must be a list of sections, like the example file.")
    return data
