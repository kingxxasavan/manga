"""Learns how the owner talks and thinks from their own messages.

Two parts. The first is plain counting over what they actually typed, so it
needs no model and cannot be talked into anything. The second is a short note
on how they think, written by the small model during upkeep. Both are shown to
the chat model every turn so Anexis answers in a way that fits its owner.
"""

from __future__ import annotations

import re

from anexis.memory.store import Memory

MIN_MESSAGES = 5
REDO_AFTER = 20  # new messages before the thinking note is rewritten
THINKING_KEY = "style.thinking"

CASUAL = re.compile(
    r"\b(gonna|wanna|gotta|kinda|tho|cuz|idk|lol|ur|u|im|dont|cant|wont|didnt|doesnt|isnt|whats|"
    r"thats|ive|ill|aint|ya|yeah|nah|bro|tmrw|rn|alot|plz|pls)\b",
    re.I,
)
QUESTION = re.compile(
    r"\?|^\s*(what|whats|when|whens|where|wheres|why|how|hows|who|whos|which|can you|could you|"
    r"would you|is|are|does|did|should)\b",
    re.I,
)
LONG = 25  # words

THINKING_PROMPT = (
    "Below are messages one person wrote to their assistant. In at most three short "
    "sentences, describe how this person thinks and what they value when they ask for "
    "things: their pace, their quality bar, how much detail they want, how they make "
    "decisions. Describe only what the messages show. Reply with the description only."
)


def analyze(messages: list[str]) -> dict:
    """Plain counts over the owner's messages."""
    messages = [m.strip() for m in messages if m and m.strip()]
    count = len(messages)
    if not count:
        return {"count": 0}
    lengths = [len(m.split()) for m in messages]
    return {
        "count": count,
        "words": sum(lengths) / count,
        "ends_with_punctuation": sum(m[-1] in ".?!" for m in messages) / count,
        "casual_words": sum(bool(CASUAL.search(m)) for m in messages) / count,
        "questions": sum(bool(QUESTION.search(m)) for m in messages) / count,
        "long": sum(n >= LONG for n in lengths) / count,
    }


def describe(stats: dict) -> list[str]:
    """Turns the counts into instructions for the chat model. Empty until
    there is enough to go on."""
    if stats.get("count", 0) < MIN_MESSAGES:
        return []
    lines = []
    if stats["ends_with_punctuation"] < 0.3 or stats["casual_words"] >= 0.3:
        lines.append(
            "Writes fast and casual with little punctuation and some misspelled words. Read past "
            "the spelling, never correct it, and answer the same relaxed way. No formal tone."
        )
    if stats["long"] >= 0.3:
        lines.append(
            "Often packs several requests into one long message. Pull out every single one and "
            "handle each, do not answer only the first."
        )
    elif stats["words"] < 12:
        lines.append("Keeps messages short. Keep replies short too.")
    if stats["questions"] < 0.25:
        lines.append(
            "Gives instructions more than questions. Act on them. When something is unclear make "
            "the call yourself and say what you decided, instead of asking a question back."
        )
    return lines


def style_lines(memory: Memory) -> list[str]:
    lines = describe(analyze(memory.owner_messages(200)))
    thinking = memory.by_key(THINKING_KEY)
    if thinking:
        lines.append(f"How they think: {thinking.text}")
    return lines


async def distill_style(memory: Memory, router) -> bool:
    """Has the small model write down how the owner thinks. True when the note
    was written or rewritten. It is a normal memory, so /memory shows it and
    /forget removes it."""
    count = memory.owner_message_count()
    if count < REDO_AFTER or count - memory.kv_get("style_thinking_at", 0) < REDO_AFTER:
        return False
    sample = "\n".join(f"- {m[:400]}" for m in memory.owner_messages(60))
    try:
        reply = await router.chat(
            "small", [{"role": "system", "content": THINKING_PROMPT}, {"role": "user", "content": sample}]
        )
    except Exception:
        return False  # no model right now, try again next round
    note = " ".join(reply.content.split())[:500]
    if len(note) < 10:
        return False
    existing = memory.by_key(THINKING_KEY)
    if existing:
        memory.supersede(existing.id, note)
    else:
        memory.add("lesson", note, confidence=0.8, importance=0.9, source="style", key=THINKING_KEY)
    memory.kv_set("style_thinking_at", count)
    memory.log("style", {"note": note})
    return True
