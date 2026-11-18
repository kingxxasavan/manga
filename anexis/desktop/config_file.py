"""Changes single values in anexis.toml and leaves the rest of the file,
comments included, exactly as the owner wrote it."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


def _value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))  # a JSON string is a valid TOML string


def set_values(path: Path, values: dict[str, object]) -> None:
    """`values` maps "key" (top of the file) or "section.key" to a new value.
    The result is checked before it replaces the file, so a bad edit can never
    leave Anexis with settings it cannot read."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    for dotted, value in values.items():
        section, _, key = dotted.rpartition(".")
        line = f"{key} = {_value(value)}"
        is_key = re.compile(rf"^\s*{re.escape(key)}\s*=")
        headers = [i for i, text in enumerate(lines) if text.strip().startswith("[")]
        if section:
            start = next((i for i in headers if lines[i].strip() == f"[{section}]"), None)
            if start is None:
                lines += ["", f"[{section}]", line]
                continue
            end = next((i for i in headers if i > start), len(lines))
            first, last = start + 1, end
        else:
            first, last = 0, headers[0] if headers else len(lines)
        found = next((i for i in range(first, last) if is_key.match(lines[i])), None)
        if found is not None:
            lines[found] = line
        elif section:
            lines.insert(first, line)
        else:  # top level keys must sit above the first [section]
            at = last
            while at > 0 and not lines[at - 1].strip():
                at -= 1
            lines[at:at] = [line] if at else [line, ""]
    text = "\n".join(lines) + "\n"
    tomllib.loads(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _table(values: dict) -> list[str]:
    return [f"{key} = {_value(value)}" for key, value in values.items() if not isinstance(value, (dict, list))]


def dump(data: dict) -> str:
    """A settings dict as TOML, in the shape anexis.toml has: plain values on
    top, then the providers in the order they are tried, then the sections."""
    lines = ["# Written by Anexis. Edit freely, or change it from the app.", ""]
    lines += _table(data)
    for provider in data.get("providers", []):
        lines += ["", "[[providers]]", *_table(provider)]
        if provider.get("models"):
            lines += ["[providers.models]", *_table(provider["models"])]
    for name, section in data.items():
        if isinstance(section, dict) and section:
            lines += ["", f"[{name}]", *_table(section)]
    text = "\n".join(lines) + "\n"
    tomllib.loads(text)  # never write a file Anexis could not read back
    return text
