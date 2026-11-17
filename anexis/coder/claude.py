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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from anexis.config import Settings
from anexis.memory.store import Memory
from anexis.tools.builtin.system import run_process

RESTING_KEY = "claude_resting_until"
USAGE_KEY = "claude_plan_usage"
USAGE_TTL = 300  # seconds a usage reading is trusted before asking again
LIMIT_CATEGORIES = {"rate_limit", "billing_error", "overloaded"}
LIMIT = re.compile(
    r"usage limit|rate limit|rate_limit|hit your (?:[\w-]+ )?limit|limit reached|out of (extra )?usage|"
    r"credit balance|billing_error|quota exceeded|insufficient (credits|funds)",
    re.IGNORECASE,
)
AUTH = re.compile(r"invalid api key|/login|not logged in|authentication_failed|unauthorized", re.IGNORECASE)
ALLOWED_TOOLS = "Bash,Read,Edit,Write,Glob,Grep,WebFetch,WebSearch"


@dataclass
class ClaudeResult:
    ok: bool
    text: str = ""
    limited: bool = False
    missing: bool = False
    reset_at: float | None = None
    error: str = ""
    model: str = ""  # the model this run was told to use, empty for Claude's default
    note: str = ""   # why that model, when it is not the usual one


def parse_reset(text: str) -> float | None:
    """When Claude says usage comes back, as a timestamp. None if it does not say."""
    stamp = re.search(r"\|(\d{10})\b", text)
    if stamp:
        return float(stamp.group(1))
    clock = re.search(r"resets?\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)(?:\s*\(([\w/+-]+)\))?", text, re.I)
    if not clock:
        return None
    hour = int(clock.group(1)) % 12 + (12 if clock.group(3).lower() == "pm" else 0)
    zone = None  # the server's own timezone unless Claude names one, like "(UTC)"
    if clock.group(4):
        try:
            zone = ZoneInfo(clock.group(4))
        except (ZoneInfoNotFoundError, ValueError):
            zone = None
    now = datetime.now(zone) if zone else datetime.now().astimezone()
    target = now.replace(hour=hour, minute=int(clock.group(2) or 0), second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.timestamp()


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


def _find(data, key: str):
    """The first value stored under `key` anywhere inside nested JSON."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        data = list(data.values())
    if isinstance(data, list):
        for item in data:
            found = _find(item, key)
            if found is not None:
                return found
    return None


def plan_percent(report: dict) -> tuple[float, list[dict]] | None:
    """How full the Claude plan is, from the report `/usage` gives: the highest
    of the meters that count for every model (the session window and the week).
    A meter for one single model is left out, it says nothing about the rest."""
    limits = (report.get("rate_limits") or {}).get("limits")
    if not limits:
        return None
    rows = []
    for row in limits:
        if not isinstance(row, dict) or row.get("is_active") is False:
            continue
        if ((row.get("scope") or {}).get("model") or {}).get("display_name"):
            continue
        try:
            rows.append({"kind": str(row.get("kind", "")), "percent": float(row["percent"]), "resets_at": row.get("resets_at")})
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return None
    return max(r["percent"] for r in rows), rows


class ClaudeRunner:
    def __init__(self, settings: Settings, memory: Memory):
        self.settings = settings
        self.memory = memory

    def _env(self) -> dict:
        env = dict(os.environ)
        if self.settings.env.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = self.settings.env["ANTHROPIC_API_KEY"]
        return env

    async def _probe(self, args: list[str], timeout: float = 45) -> tuple[int | None, str]:
        """A quick side question to Claude Code. (None, "") when it is not installed."""
        try:
            self.settings.workspace.mkdir(parents=True, exist_ok=True)
            return await run_process([self.settings.claude_bin, *args], self.settings.workspace, timeout, env=self._env())
        except (FileNotFoundError, PermissionError, OSError):
            return None, ""

    async def auth(self) -> dict:
        """How Claude Code is signed in: with a Claude plan, an API key, or not at all."""
        code, output = await self._probe(["auth", "status"], 20)
        if code is None:
            return {"installed": False, "signed_in": False, "method": "none"}
        info = {}
        start = output.find("{")
        if start >= 0:
            try:
                info = json.loads(output[start:output.rfind("}") + 1])
            except ValueError:
                info = {}
        method = str(info.get("authMethod") or ("none" if code else "unknown"))
        return {
            "installed": True, "signed_in": code == 0 and method != "none", "method": method,
            "plan": method in ("claude.ai", "oauth_token"),
            "email": str(info.get("email") or ""), "subscription": str(info.get("subscriptionType") or ""),
        }

    async def usage(self, fresh: bool = False) -> dict | None:
        """How much of the Claude plan is used, as {"percent", "rows", "at"}.
        None when Claude Code cannot say: it runs on an API key, it is not
        signed in, or this version does not report it. Asking costs no usage."""
        cached = self.memory.kv_get(USAGE_KEY, None)
        if cached and not fresh and time.time() - cached.get("at", 0) < USAGE_TTL:
            return cached if cached.get("percent") is not None else None
        code, output = await self._probe(["-p", "/usage", "--output-format", "stream-json", "--verbose"])
        reading: dict = {"at": time.time(), "percent": None}
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("{") or "usage_report" not in line:
                continue
            try:
                report = _find(json.loads(line), "usage_report")
            except ValueError:
                continue
            found = plan_percent(report) if isinstance(report, dict) else None
            if found:
                reading.update(percent=found[0], rows=found[1])
                break
        self.memory.kv_set(USAGE_KEY, reading)
        return reading if reading["percent"] is not None else None

    async def pick_model(self) -> tuple[str, str]:
        """(model to pass to Claude Code, why). Normally the owner's usual model.
        Once the plan is nearly used up, the cheaper one, so it lasts longer."""
        usual = self.settings.claude_model
        limit, cheaper = self.settings.claude_switch_percent, self.settings.claude_switch_model
        if limit <= 0 or not cheaper or cheaper == usual:
            return usual, ""
        reading = await self.usage()
        if reading and reading["percent"] >= limit:
            return cheaper, f"your Claude plan is {reading['percent']:.0f}% used, so this ran on {cheaper} to stretch what is left"
        return usual, ""

    def available(self) -> tuple[bool, str]:
        until = self.memory.kv_get(RESTING_KEY, 0)
        if until and time.time() < until:
            return False, f"Claude is out of usage until {time.strftime('%H:%M', time.localtime(until))}"
        return True, ""

    def _command(self, task: str, guidance: str, model: str = "") -> list[str]:
        command = [
            self.settings.claude_bin, "-p", task,
            "--output-format", "json",
            "--permission-mode", "acceptEdits",
            "--allowedTools", ALLOWED_TOOLS,
        ]
        if model:
            command += ["--model", model]
        if guidance:
            command += ["--append-system-prompt", guidance]
        return command

    async def run(self, task: str, cwd: Path, guidance: str = "") -> ClaudeResult:
        model, note = await self.pick_model()
        try:
            code, output = await run_process(
                self._command(task, guidance, model), cwd, self.settings.claude_timeout, env=self._env()
            )
        except (FileNotFoundError, PermissionError):
            return ClaudeResult(False, missing=True, error="Claude Code is not installed on this computer")
        if code is None:
            return ClaudeResult(False, error=f"Claude ran longer than {self.settings.claude_timeout:g} seconds and was stopped")

        result = self._classify(code, output)
        result.model, result.note = model, note
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
                return ClaudeResult(False, error=f"Claude Code is not logged in ({said}). Sign in with your Claude plan (the Keys screen in the app, or `claude auth login` in a terminal), or set ANTHROPIC_API_KEY.")
            return ClaudeResult(False, error=f"Claude Code failed: {said[:400]}")

        # A run marked as fine whose whole answer is just the limit notice.
        if len(text) < 200 and LIMIT.search(text):
            return ClaudeResult(False, limited=True, reset_at=parse_reset(text), error=text)
        return ClaudeResult(True, text=text)
