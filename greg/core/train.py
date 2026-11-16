"""greg train: talk to Greg the way its owner talks, then check what stuck.

A pack (training/like_me.yaml) holds things to teach, made up practice facts,
and probes asked afterwards. Every turn goes through the real chat loop and
the real learn step. The report says what was learned, what a later sloppy
question recalled, whether standing instructions reach the model, and whether
the right tool was offered.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from greg.config import Settings
from greg.memory.consolidate import consolidate
from greg.memory.style import style_lines

GROUPS = ("learned", "reinforced", "replaced", "recall", "prompt", "tools")


@dataclass
class Check:
    group: str
    ok: bool
    label: str
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    style: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    kept: bool = False

    def counts(self) -> dict[str, tuple[int, int]]:
        out = {}
        for group in GROUPS:
            mine = [c for c in self.checks if c.group == group]
            if mine:
                out[group] = (sum(c.ok for c in mine), len(mine))
        return out

    def score(self) -> tuple[int, int]:
        return sum(c.ok for c in self.checks), len(self.checks)

    def failures(self) -> list[str]:
        return [f"{c.group}: {c.label} ({c.detail})" for c in self.checks if not c.ok] + self.errors


def load_pack(path: Path) -> dict:
    pack = yaml.safe_load(Path(path).read_text()) or {}
    pack.setdefault("teach", [])
    pack.setdefault("practice", [])
    pack.setdefault("probes", [])
    for turn in pack["teach"] + pack["practice"]:
        if not isinstance(turn, dict) or not turn.get("say"):
            raise ValueError(f"Every teach and practice entry needs a `say`: {turn}")
    for probe in pack["probes"]:
        if not isinstance(probe, dict) or not probe.get("ask"):
            raise ValueError(f"Every probe needs an `ask`: {probe}")
    return pack


def practice_settings(settings: Settings, scratch: Path) -> Settings:
    """The same models, pointed at a throwaway memory so nothing real is touched."""
    return dataclasses.replace(settings, home=Path(scratch), learn=True, consolidate_minutes=0)


def matches(expectation: str, text: str) -> bool:
    """`a b|c` means: contains both a and b, or contains c."""
    low = text.lower()
    return any(all(word in low for word in option.lower().split()) for option in str(expectation).split("|"))


def _find(memory, expectation: str) -> list:
    return [m for m in memory.list(limit=1000) if matches(expectation, m.text)]


async def run_training(greg, pack: dict, keep: bool = False, say=None) -> Report:
    say = say or (lambda line: None)
    memory = greg.memory
    report = Report(kept=keep)
    add = report.checks.append
    turns = pack.get("teach", []) + ([] if keep else pack.get("practice", []))

    session = None
    for turn in turns:
        before = {m.id: m.confidence for e in turn.get("reinforces", []) for m in _find(memory, e)}
        say(f"you   {turn['say']}")
        result = await greg.agent.run_turn(session, turn["say"])
        session = result["session_id"]
        await greg.agent.drain()  # let the learn step finish before checking
        if result.get("error"):
            report.errors.append(result["error"])
            say("      no model answered")
            continue
        for expected in turn.get("learns", []):
            rows = _find(memory, expected)
            add(Check("learned", bool(rows), expected, rows[0].text if rows else "nothing like it was saved"))
        for expected in turn.get("reinforces", []):
            rows = _find(memory, expected)
            surer = bool(before) and len(rows) == len(before) and all(r.confidence > before.get(r.id, 2) for r in rows)
            detail = f"confidence {rows[0].confidence:.2f}" if surer else "expected the same memory to get more sure, with no second copy"
            add(Check("reinforced", surer, expected, detail))
        for expected in turn.get("gone", []):
            rows = _find(memory, expected)
            add(Check("replaced", not rows, expected, "old version is history" if not rows else f"still live: {rows[0].text}"))

    for failure in memory.events(50):
        if failure["kind"] == "learn_failed" and failure.get("error") not in report.errors:
            report.errors.append(f"learning failed: {failure.get('error')}")

    await consolidate(memory, greg.router)

    stats = memory.tool_stats()
    for probe in pack.get("probes", []):
        if keep and probe.get("practice"):
            continue
        ask = probe["ask"]
        try:
            embedded = await greg.router.embed([ask], "query")
        except Exception:
            embedded = None
        tag, vec = (embedded[0], embedded[1][0]) if embedded else (None, None)
        if probe.get("recall"):
            rows = memory.search(ask, greg.settings.recall_k, vec, tag)
            hit = next((r for r in rows if matches(probe["recall"], r.text)), None)
            add(Check("recall", bool(hit), ask, hit.text if hit else "the memory was not brought up"))
        if probe.get("prompt"):
            ok = matches(probe["prompt"], await greg.agent.system_for(ask))
            add(Check("prompt", ok, ask, f"model is told about: {probe['prompt']}" if ok else f"model was not told about: {probe['prompt']}"))
        if probe.get("tool"):
            offered = [t.name for t in greg.registry.pick(ask, greg.settings.max_tools, vec, stats)]
            ok = probe["tool"] in offered
            add(Check("tools", ok, ask, probe["tool"] if ok else f"{probe['tool']} was not offered"))

    report.style = style_lines(memory)
    return report


class OfflineRouter:
    """Stands in for the model when there is none. The chat model says "ok" and
    the learn step gets the `offline` answers written in the pack, so everything
    around the model is exercised for real. It does not test the model."""

    def __init__(self, pack: dict):
        self.providers: list = []
        self.answers = {t["say"]: t.get("offline", []) for t in pack.get("teach", []) + pack.get("practice", [])}
        self.last_errors: dict = {}

    async def chat(self, role, messages, tools=None, on_text=None):
        from greg.llm.provider import ChatResult

        text = "ok"
        if role == "small":
            content = messages[-1]["content"]
            said = next((s for s in self.answers if content.startswith(f"Owner said:\n{s}")), None)
            text = json.dumps({"ops": self._resolve(self.answers[said], content)}) if said else "Offline practice run."
        if on_text:
            on_text(text)
        return ChatResult(content=text, provider="offline", model="stand in")

    @staticmethod
    def _resolve(ops: list[dict], content: str) -> list[dict]:
        """`match: words` on a replace becomes the id of the listed memory containing them."""
        listed = re.findall(r"^#(\d+) \[\w+\] (.*)$", content, re.M)
        out = []
        for op in ops:
            op = dict(op)
            wanted = op.pop("match", None)
            if wanted:
                found = next((int(i) for i, text in listed if wanted.lower() in text.lower()), None)
                if found is None:
                    continue
                op["id"] = found
            out.append(op)
        return out

    async def embed(self, texts, kind="passage"):
        return None

    async def status(self):
        return [{"name": "offline", "ok": True, "models": {}, "missing": []}]

    async def close(self):
        pass
