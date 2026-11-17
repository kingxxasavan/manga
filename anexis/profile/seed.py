"""What Anexis knows about its owner from the very first start.

The owner already told Anexis plenty while it was being built: how to talk to
them, how they code, what they use. That lives in training/like_me.yaml under
`teach`. Without this, a fresh install (like a new PC) starts knowing nothing
and the owner has to say it all again.

On first start the `teach` facts go into memory, and the About Me sections
those facts answer are filled in. Sections the owner already filled are never
touched, and it runs once per memory database.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from anexis.config import REPO_ROOT
from anexis.profile.about import export_profile, import_profile

DONE_KEY = "owner_seeded"
PACK = REPO_ROOT / "training" / "like_me.yaml"

# The About Me answers that follow from what the owner said. Only these
# sections, and only when they are still empty. The rest (name, school,
# classes, work...) only the owner knows, so they stay blank for them.
ABOUT = {
    "talk_style": "Casual and less formal. Small grammar mistakes are fine. Never any dashes.",
    "avoid": [
        "Dashes of any kind when writing to me",
        "Asking a bunch of questions before starting. Make the call and tell me after",
        "Handing me the basic version of anything",
    ],
    "tools": [
        "Windows PC with Anexis as a desktop app",
        "Claude Pro plan for code, through Claude Code",
        "Nvidia and Ollama for models",
        "Canvas for school",
    ],
    "interests": ["Futuristic interfaces like eDEX UI, on a black background"],
}


def _key(text: str) -> str:
    return "told:" + hashlib.sha1(text.strip().lower().encode()).hexdigest()[:12]


def seed_owner(memory, pack: Path = PACK) -> dict:
    """Puts what the owner already said into memory. Safe to call on every
    start: it does its work once, and never twice for the same fact."""
    if memory.kv_get(DONE_KEY):
        return {"memories": 0, "about": 0, "skipped": True}
    added = 0
    try:
        teach = (yaml.safe_load(Path(pack).read_text(encoding="utf-8")) or {}).get("teach", [])
    except (OSError, yaml.YAMLError):
        teach = []
    for item in teach:
        for op in item.get("offline", []) or []:
            if op.get("op") != "add" or not op.get("text"):
                continue
            key = _key(op["text"])
            if memory.by_key(key):
                continue
            kind = op.get("kind", "fact")
            # Things about how to behave are the strongest kind of memory.
            memory.add(kind, op["text"], confidence=0.95, importance=float(op.get("importance", 0.7 if kind == "lesson" else 0.6)),
                       source="told", key=key)
            added += 1
    have = export_profile(memory)
    fill = {section: value for section, value in ABOUT.items() if not have.get(section)}
    report = import_profile(memory, fill) if fill else {"added": 0}
    memory.kv_set(DONE_KEY, True)
    return {"memories": added, "about": report.get("added", 0), "skipped": False}
