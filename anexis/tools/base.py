"""What a tool is, and what a running tool gets handed."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

SAFE = "safe"      # runs
WRITE = "write"    # file access: runs inside the workspace, asks outside it
DANGER = "danger"  # always asks first

_BAD = re.compile(r"[^a-zA-Z0-9_-]+")


def clean_name(name: str) -> str:
    """Models only accept tool names made of letters, digits, _ and -, up to 64 long."""
    return _BAD.sub("_", name).strip("_")[:64] or "tool"


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, ToolContext], Awaitable[str]]
    tier: str = SAFE
    source: str = "builtin"
    core: bool = False  # always offered to the model
    vec: Any = None

    def __post_init__(self) -> None:
        self.name = clean_name(self.name)

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description[:1000],
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


async def _deny(tool: Tool, args: dict, reason: str) -> bool:
    return False


@dataclass
class ToolContext:
    settings: Any
    memory: Any
    router: Any
    registry: Any
    session_id: str
    # Asks the owner. Defaults to "no" so nothing risky runs when nobody can answer.
    confirm: Callable[[Tool, dict, str], Awaitable[bool]] = _deny
    emit: Callable[[dict], None] = lambda event: None
    # Tools the model asked for through find_tools, offered for the rest of the turn.
    extra_tools: set[str] = field(default_factory=set)


def params(required: list[str] | None = None, **props: dict) -> dict:
    """Shorthand for a JSON schema object."""
    return {"type": "object", "properties": props, "required": required or []}


def text(description: str) -> dict:
    return {"type": "string", "description": description}
