"""Runs Claude Code in headless mode and works out how the run really ended.

Claude Code must be installed on the server and either logged in or given
ANTHROPIC_API_KEY. Exit codes alone are not trusted: a usage limit can come
back as a failed run, as a "successful" run flagged is_error, or as plain text.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from greg.config import Settings
from greg.memory.store import Memory
from greg.tools.builtin.system import run_process

RESTING_KEY = "claude_resting_until"
LIMIT_CATEGORIES = {"rate_limit", "billing_error", "overloaded"}
LIMIT = re.compile(
    r"usage limit|rate limit|rate_limit|hit your limit|limit reached|out of (extra )?usage|"
    r"credit balance|billing_error|quota exceeded|insufficient (credits|funds)",
    re.I,
)
AUTH = re.compile(r"invalid api key|/login|not logged in|authentication_failed|unauthorized", re.I)
ALLOWED_TOOLS = "Bash,Read,Edit,Write,Glob,Grep,WebFetch,WebSearch"


@dataclass
class ClaudeResult:
    ok: bool
    text: str = ""
    limited: bool = False
    missing: bool = False
    reset_at: float | None = None
    error: str = ""


def parse_reset(text: str) -> float | None:
    """When Claude says usage comes back, as a timestamp. None if it does not say."""
    stamp = re.search(r"\|(\d{10})\b", text)
    if stamp:
        return float(stamp.group(1))
    clock = re.search(r"resets?\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text, re.I)
    if not clock:
        return None
    hour = int(clock.group(1)) % 12 + (12 if clock.group(3).lower() == "pm" else 0)
    now = time.localtime()
    target = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, int(clock.group(2) or 0), 0, 0, 0, -1))
    return target if target > time.time() else target + 86400


def _envelope(output: str) -> dict | None:
    """The result object Claude prints, found even with other lines around it."""
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict) and ("result" in data or data.get("type") == "result"):
                return data
    return None


class ClaudeRunner:
    def __init__(self, settings: Settings, memory: Memory):
        self.settings = settings
        self.memory = memory

    def available(self) -> tuple[bool, str]:
        until = self.memory.kv_get(RESTING_KEY, 0)
        if until and time.time() < until:
            return False, f"Claude is out of usage until {time.strftime('%H:%M', time.localtime(until))}"
        return True, ""

    def _command(self, task: str, guidance: str) -> list[str]:
        command = [
            self.settings.claude_bin, "-p", task,
            "--output-format", "json",
            "--permission-mode", "acceptEdits",
            "--allowedTools", ALLOWED_TOOLS,
        ]
        if self.settings.claude_model:
            command += ["--model", self.settings.claude_model]
        if guidance:
            command += ["--append-system-prompt", guidance]
        return command

    async def run(self, task: str, cwd: Path, guidance: str = "") -> ClaudeResult:
        env = dict(os.environ)
        if self.settings.env.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = self.settings.env["ANTHROPIC_API_KEY"]
        try:
            code, output = await run_process(
                self._command(task, guidance), cwd, self.settings.claude_timeout, env=env
            )
        except (FileNotFoundError, PermissionError):
            return ClaudeResult(False, missing=True, error="Claude Code is not installed on this server")
        if code is None:
            return ClaudeResult(False, error=f"Claude ran longer than {self.settings.claude_timeout:g} seconds and was stopped")

        result = self._classify(code, output)
        if result.limited:
            if result.reset_at is None:
                result.reset_at = time.time() + self.settings.claude_backoff_minutes * 60
            self.memory.kv_set(RESTING_KEY, result.reset_at)
            self.memory.log("claude_limit", {"until": result.reset_at, "said": result.error[:200]})
        return result

    def _classify(self, code: int, output: str) -> ClaudeResult:
        envelope = _envelope(output)
        if envelope is None:
            said = output.strip()[-400:] or f"exit code {code}"
            if LIMIT.search(said):
                return ClaudeResult(False, limited=True, reset_at=parse_reset(said), error=said)
            return ClaudeResult(False, error=f"Claude Code failed: {said}")

        text = str(envelope.get("result") or "")
        category = str(envelope.get("error") or "")
        subtype = str(envelope.get("subtype") or "")
        failed = code != 0 or bool(envelope.get("is_error")) or subtype.startswith("error")

        if failed:
            said = text or category or subtype or f"exit code {code}"
            if category in LIMIT_CATEGORIES or LIMIT.search(f"{text} {category}"):
                return ClaudeResult(False, limited=True, reset_at=parse_reset(text), error=said)
            if AUTH.search(f"{text} {category}"):
                return ClaudeResult(False, error=f"Claude Code is not logged in ({said}). Run `claude` once on the server to log in, or set ANTHROPIC_API_KEY.")
            return ClaudeResult(False, error=f"Claude Code failed: {said[:400]}")

        # A run marked as fine whose whole answer is just the limit notice.
        if len(text) < 200 and LIMIT.search(text):
            return ClaudeResult(False, limited=True, reset_at=parse_reset(text), error=text)
        return ClaudeResult(True, text=text)
