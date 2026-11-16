"""Upkeep that runs when Greg is idle: summaries, vectors, merging, decay."""

from __future__ import annotations

from greg.memory.store import Memory
from greg.memory.style import distill_style

SUMMARY_PROMPT = (
    "Summarize this conversation between the owner and their assistant in at most four "
    "sentences. Keep decisions, plans, open questions and anything the owner will want "
    "picked up later. Reply with the summary only."
)


async def consolidate(memory: Memory, router) -> dict:
    report = {"summaries": 0, "embedded": 0, "merged": 0, "decayed": 0, "style": 0}
    report["style"] = int(await distill_style(memory, router))

    for session in memory.sessions_needing_summary():
        fresh = memory.history(session["id"], limit=60, after_id=session["summarized_upto"])
        transcript = "\n".join(f"{m['role']}: {m['content'][:800]}" for m in fresh)
        if session["summary"]:
            transcript = f"Summary so far: {session['summary']}\n\n{transcript}"
        try:
            reply = await router.chat(
                "small",
                [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": transcript}],
            )
        except Exception:
            break  # no model right now, try again next round
        if reply.content.strip():
            memory.set_summary(session["id"], reply.content.strip(), fresh[-1]["id"])
            report["summaries"] += 1

    # Give vectors to memories that have none for the current embedding model.
    try:
        probe = await router.embed(["probe"])
    except Exception:
        probe = None
    if probe:
        tag = probe[0]
        while True:
            missing = memory.missing_vectors(tag)
            if not missing:
                break
            result = await router.embed([m.text for m in missing])
            if not result or result[0] != tag:
                break
            for row, vec in zip(missing, result[1]):
                memory.set_vector(row.id, tag, vec)
            report["embedded"] += len(missing)

    for row in memory.list(limit=500):
        current = memory.get(row.id)
        if current is None or current.superseded_by is not None:
            continue  # already folded into another one this round
        twin_id = memory.find_duplicate(current.text, exclude=current.id)
        if twin_id is None:
            continue
        twin = memory.get(twin_id)
        weak, strong = sorted((current, twin), key=lambda m: (m.pinned, m.confidence, m.use_count))
        memory.merge(weak.id, strong.id)
        memory.log("merge", {"kept": strong.id, "folded": weak.id})
        report["merged"] += 1

    report["decayed"] = memory.decay()
    return report
