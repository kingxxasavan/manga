"""anexis setup: the setup window.

Four short steps: pick a preset, paste keys, pick options, pick what to
install. Enter always takes the suggestion or skips. Nothing is written until
the last question is answered with yes.

It writes three files into Anexis's home folder:
  anexis.toml    settings from the preset
  .env         keys, private to your user
  setup-plan   what setup.sh should install next
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from anexis.config import read_dotenv
from anexis.platform import memory_gb, private_file

EMBED = "nomic-embed-text"
NVIDIA_CHAT = "meta/llama-3.3-70b-instruct"
NVIDIA_EMBED = "nvidia/nv-embedqa-e5-v5"
NODE_NEEDED = 24
PLAN_LINE = re.compile(r"[A-Z_]+=[A-Za-z0-9_.:/ -]*")


@dataclass(frozen=True)
class Preset:
    name: str
    title: str
    blurb: str
    ollama: dict | None  # role -> model, or None for no local model
    memory: dict = field(default_factory=dict)
    agent: dict = field(default_factory=dict)
    voice: bool = False

    @property
    def pull(self) -> list[str]:
        """Local models to download, each once."""
        return list(dict.fromkeys(self.ollama.values())) if self.ollama else []


PRESETS = {
    p.name: p
    for p in [
        Preset(
            "max", "Max", "Biggest local models, widest memory, voice on. Wants a GPU with 16 GB or more.",
            {"chat": "qwen3:14b", "coder": "qwen2.5-coder:14b", "small": "qwen3:8b", "embed": EMBED},
            memory={"recall_k": 12, "history_messages": 40, "history_chars": 48000},
            agent={"max_steps": 12, "max_tools": 16},
            voice=True,
        ),
        Preset(
            "balanced", "Balanced", "Good local models that fit an 8 GB GPU. Nvidia as backup.",
            {"chat": "qwen3:8b", "coder": "qwen2.5-coder:7b", "small": "qwen3:4b", "embed": EMBED},
            memory={"recall_k": 8, "history_messages": 24, "history_chars": 24000},
            agent={"max_steps": 8, "max_tools": 12},
        ),
        Preset(
            "light", "Light", "Small local models for a machine with no GPU. Slower and simpler, still private.",
            {"chat": "qwen3:4b", "coder": "qwen2.5-coder:3b", "small": "qwen3:1.7b", "embed": EMBED},
            memory={"recall_k": 5, "history_messages": 12, "history_chars": 10000},
            agent={"max_steps": 6, "max_tools": 8},
        ),
        Preset(
            "cloud", "Cloud", "No local model at all. Everything runs on Nvidia's hosted models. Needs the Nvidia key.",
            None,
            memory={"recall_k": 10, "history_messages": 30, "history_chars": 40000},
            agent={"max_steps": 10, "max_tools": 16},
        ),
    ]
}

@dataclass(frozen=True)
class KeyOption:
    env: str          # name in .env
    label: str        # what the hidden prompt says
    title: str        # the option it belongs to
    turns_on: str
    get_it: str
    prefixes: tuple = ()  # what a real one starts with, for a paste check


KEY_OPTIONS = [
    KeyOption("NVIDIA_API_KEY", "Nvidia key", "Nvidia hosted models",
              "big models with no GPU needed, and the backup when Ollama is down",
              "free at build.nvidia.com", ("nvapi-",)),
    KeyOption("ANTHROPIC_API_KEY", "Anthropic key", "Claude for code",
              "Claude writes your code. Skip this if you log in by running `claude` instead",
              "console.anthropic.com", ("sk-ant-",)),
    KeyOption("GITHUB_TOKEN", "GitHub token", "GitHub",
              "code search, issues and pull requests",
              "github.com/settings/tokens", ("ghp_", "github_pat_", "gho_")),
    KeyOption("NOTION_TOKEN", "Notion token", "Notion",
              "read and write your Notion pages", "notion.so/profile/integrations", ("ntn_", "secret_")),
    KeyOption("BRAVE_API_KEY", "Brave Search key", "Brave Search",
              "web, news and image search", "brave.com/search/api"),
    KeyOption("TAVILY_API_KEY", "Tavily key", "Tavily",
              "web search tuned for AI", "tavily.com", ("tvly-",)),
    KeyOption("FIRECRAWL_API_KEY", "Firecrawl key", "Firecrawl",
              "crawl and scrape whole websites", "firecrawl.dev", ("fc-",)),
    KeyOption("EXA_API_KEY", "Exa key", "Exa",
              "meaning based web search", "exa.ai"),
]


@dataclass
class Machine:
    vram_gb: float = 0
    ram_gb: float = 0
    has_ollama: bool = False
    node_major: int = 0
    has_claude: bool = False
    has_systemd: bool = False

    def describe(self) -> str:
        gpu = f"Nvidia GPU with {self.vram_gb:.0f} GB" if self.vram_gb else "no Nvidia GPU found"
        return f"This machine: {gpu}, {self.ram_gb:.0f} GB of memory."


def _output(command: list[str]) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def find_ollama() -> str | None:
    """Ollama on PATH, or where its Windows installer puts it."""
    found = shutil.which("ollama")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    candidate = Path(local) / "Programs" / "Ollama" / "ollama.exe" if local else None
    return str(candidate) if candidate and candidate.is_file() else None


def detect_machine() -> Machine:
    sizes = [int(x) for x in re.findall(r"\d+", _output(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]))]
    ram = memory_gb()
    from anexis.tools.mcp_client import tool_path

    node = re.search(r"v(\d+)", _output([shutil.which("node", path=tool_path()) or "node", "--version"]))
    return Machine(
        vram_gb=max(sizes) / 1024 if sizes else 0,
        ram_gb=ram,
        has_ollama=bool(find_ollama()),
        node_major=int(node.group(1)) if node else 0,
        has_claude=bool(shutil.which("claude")),
        has_systemd=bool(shutil.which("systemctl")) and Path("/run/systemd/system").is_dir(),
    )


def recommend(machine: Machine, env: dict) -> str:
    if machine.vram_gb >= 16:
        return "max"
    if machine.vram_gb >= 6:
        return "balanced"
    return "cloud" if env.get("NVIDIA_API_KEY") else "light"


def build_toml(preset: Preset, name: str, control: str = "") -> str:
    lines = [
        f"# Written by `anexis setup` with the {preset.name} preset. Edit freely.",
        "# Run `anexis setup` again to redo it. Your old file is backed up first.",
        "",
        f"name = {json.dumps(name)}",
    ]
    if preset.ollama:
        lines += ["", "[[providers]]", 'name = "ollama"', 'base_url = "http://localhost:11434/v1"', "[providers.models]"]
        lines += [f'{role} = "{model}"' for role, model in preset.ollama.items()]
    lines += [
        "", "# Used when the key is in .env. A role that is not listed uses the chat model.",
        "[[providers]]", 'name = "nvidia"', 'base_url = "https://integrate.api.nvidia.com/v1"',
        'api_key_env = "NVIDIA_API_KEY"', "embed_input_type = true", "[providers.models]",
        f'chat = "{NVIDIA_CHAT}"', f'embed = "{NVIDIA_EMBED}"',
    ]
    agent: dict = dict(preset.agent)
    if control:
        agent["control"] = json.dumps(control)  # "full" or "ask", see the README
    for section, values in (("memory", preset.memory), ("agent", agent)):
        if values:
            lines += ["", f"[{section}]"] + [f"{key} = {value}" for key, value in values.items()]
    return "\n".join(lines) + "\n"


def apply_choices(
    home: Path,
    preset: str,
    name: str,
    env_changes: dict[str, str] | None = None,
    plan: dict[str, str] | None = None,
    control: str = "",
) -> Path | None:
    """Writes the settings a setup run decided on. Used by the terminal setup
    window and by setup in the desktop app. Returns the backup of the old
    settings file when there was one."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r}. Pick one of: {', '.join(PRESETS)}")
    if control not in ("", "ask", "full"):
        raise ValueError('control must be "ask" or "full"')
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    config, backup = home / "anexis.toml", None
    if config.exists():
        backup = home / f"anexis.toml.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(config, backup)
    config.write_text(build_toml(PRESETS[preset], name, control), encoding="utf-8")
    if env_changes:
        update_env_file(home / ".env", env_changes)
    if plan is not None:
        write_plan(home / "setup-plan", plan)
    return backup


def _env_line(key: str, value: str) -> str:
    plain = re.fullmatch(r"[A-Za-z0-9_.:/@+=-]*", value)
    return f"{key}={value}" if plain else f'{key}="{value}"'


def update_env_file(path: Path, changes: dict[str, str]) -> None:
    """Set keys in a .env file. An empty value removes the key. Comments and
    every other line stay exactly as they were. The file is readable only by
    its owner."""
    lines = path.read_text().splitlines() if path.is_file() else []
    left = dict(changes)
    out = []
    for line in lines:
        name = line.strip().removeprefix("export ").split("=", 1)[0].strip()
        if "=" in line and not line.strip().startswith("#") and name in left:
            value = left.pop(name)
            if value:
                out.append(_env_line(name, value))
            continue
        out.append(line)
    out += [_env_line(name, value) for name, value in left.items() if value]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(out) + "\n" if out else "")
    private_file(path)


def key_warning(name: str, value: str) -> str:
    """A hint when a pasted key looks off. Never blocks: formats change."""
    if any(c.isspace() for c in value):
        return "That has a space in it. Keys never do, so it may be a bad paste."
    prefixes = next((o.prefixes for o in KEY_OPTIONS if o.env == name), ())
    if prefixes and not value.startswith(prefixes):
        return f"Heads up: these usually start with {' or '.join(prefixes)}. Saved anyway."
    if len(value) < 12:
        return "That looks short for a key. Saved anyway."
    return ""


def write_plan(path: Path, plan: dict[str, str]) -> None:
    """The plan is read by a shell script, so only plain, known safe values go in."""
    lines = [f"{key}={value}" for key, value in plan.items()]
    for line in lines:
        if not PLAN_LINE.fullmatch(line):
            raise ValueError(f"Refusing to write an unsafe plan line: {line!r}")
    path.write_text("\n".join(lines) + "\n")


def read_plan(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in Path(path).read_text().splitlines() if "=" in line)


def window(title: str, lines: list[str], width: int = 70) -> str:
    """A boxed block of text, the "window" each setup step is shown in."""
    inner = width - 4
    body = []
    for line in lines:
        while len(line) > inner:
            cut = line.rfind(" ", 0, inner + 1)
            cut = cut if cut > 0 else inner
            body.append(line[:cut])
            line = "   " + line[cut:].lstrip()
        body.append(line)
    top = f"╭ {title} " + "─" * max(0, width - len(title) - 4) + "╮"
    return "\n".join(["", top, *(f"│ {line:<{inner}} │" for line in body), "╰" + "─" * (width - 2) + "╯"])


@dataclass
class Result:
    preset: str = ""
    cancelled: bool = False
    home: Path | None = None
    plan: dict = field(default_factory=dict)


def run_wizard(
    home: Path,
    env: dict,
    machine: Machine,
    ask: Callable[..., str],
    say: Callable[[str], None],
    preset: str | None = None,
    yes: bool = False,
) -> Result:
    """The choices: preset, options, what to install. No keys here, those are
    asked by run_keys once everything is downloaded.

    `ask(question, default, secret)` gets an answer and `say(text)` shows text.
    With `yes` nothing is asked and every suggestion is taken."""
    if preset is not None and preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r}. Pick one of: {', '.join(PRESETS)}")
    home = Path(home)
    saved = read_dotenv(home / ".env")

    def question(text: str, default: str = "", secret: bool = False) -> str:
        return default if yes else (ask(text, default, secret).strip() or default)

    def yes_no(text: str, default: bool) -> bool:
        if yes:
            return default
        answer = ask(f"{text} [{'Y/n' if default else 'y/N'}] ", "", False).strip().lower()
        return default if not answer else answer in ("y", "yes")

    # ---- step 1: preset ----------------------------------------------------
    names = list(PRESETS)
    best = recommend(machine, {**env, **saved})
    if preset is None:
        rows = [machine.describe(), ""]
        for number, name in enumerate(names, 1):
            star = "   <- best fit for this machine" if name == best else ""
            rows.append(f"{number}  {PRESETS[name].title}{star}")
            rows.append(f"   {PRESETS[name].blurb}")
        say(window("Anexis setup   step 1 of 3   Pick a preset", rows))
        preset = best
        for _ in range(3):
            answer = question(f"Which preset? Number or name [Enter = {names.index(best) + 1}] ").lower()
            if not answer:
                break
            if answer.isdigit() and 1 <= int(answer) <= len(names):
                preset = names[int(answer) - 1]
                break
            if answer in PRESETS:
                preset = answer
                break
            say(f"  That is not one of them. Type 1 to {len(names)}, or a name.")
    chosen = PRESETS[preset]
    say(f"  Preset: {chosen.title}")

    env_changes: dict[str, str] = {}  # only the remote access settings, keys come later

    # ---- step 2: options ---------------------------------------------------
    say(window("Anexis setup   step 2 of 3   Options", ["Enter takes the suggestion in [brackets]."]))
    name = question("What do you want to call it? [Anexis] ", "Anexis")[:40].strip() or "Anexis"
    voice = yes_no("Install voice, so you can talk and it can talk back?", chosen.voice)
    was_open = saved.get("ANEXIS_HOST", "") not in ("", "127.0.0.1", "localhost")
    remote = yes_no("Reach it from other machines, like your laptop?", was_open)
    service = machine.has_systemd and yes_no("Keep it running in the background and after reboots?", False)
    if remote:
        env_changes["ANEXIS_HOST"] = "0.0.0.0"
        if not saved.get("ANEXIS_TOKEN"):
            env_changes["ANEXIS_TOKEN"] = secrets.token_urlsafe(32)
    elif was_open:
        env_changes["ANEXIS_HOST"] = ""

    # ---- step 3: what to install -------------------------------------------
    say(window("Anexis setup   step 3 of 3   What to install", [
        "Say n to skip anything. You can run the installer again later.",
    ]))
    install_ollama, pull = False, []
    if chosen.pull:
        models = ", ".join(chosen.pull)
        if machine.has_ollama:
            say("  Ollama: already installed")
            if yes_no(f"Pull the models now? ({models})", True):
                pull = chosen.pull
        elif yes_no(f"Install Ollama and pull the models? ({models})", True):
            install_ollama, pull = True, chosen.pull
    install_node = False
    if machine.node_major >= NODE_NEEDED:
        say(f"  Node {machine.node_major}: already installed")
    else:
        have = f"you have {machine.node_major}" if machine.node_major else "not installed"
        install_node = yes_no(f"Install Node {NODE_NEEDED} into your home folder? Half the tool servers need it ({have}).", True)
    install_claude = False
    if machine.has_claude:
        say("  Claude Code: already installed")
    elif machine.node_major or install_node:
        install_claude = yes_no("Install Claude Code, so Claude can write your code?", True)
    else:
        say("  Claude Code: skipped, it needs Node")
    sync_tools = yes_no("Download the tool servers now? If you skip, they download the first time Anexis starts.", True)

    plan = {
        "PRESET": preset,
        "INSTALL_OLLAMA": str(int(install_ollama)),
        "PULL_MODELS": " ".join(pull),
        "INSTALL_NODE": str(int(install_node)),
        "INSTALL_CLAUDE": str(int(install_claude)),
        "INSTALL_VOICE": str(int(voice)),
        "SYNC_TOOLS": str(int(sync_tools)),
        "ENABLE_SERVICE": str(int(service)),
    }

    # ---- confirm, then write -----------------------------------------------
    say(window("Anexis setup   Summary", [
        f"Name      {name}",
        f"Preset    {chosen.title}",
        "Keys      asked for after everything is downloaded",
        f"Models    {', '.join(pull) or ('none to download' if chosen.pull else 'hosted by Nvidia')}",
        f"Install   {', '.join(what for what, on in [('Ollama', install_ollama), ('Node', install_node), ('Claude Code', install_claude), ('voice', voice), ('tool servers', sync_tools)] if on) or 'nothing new'}",
        f"Remote    {'yes, with a token' if remote else 'no, this machine only'}",
        f"Service   {'yes' if service else 'no, it starts when you open the chat'}",
    ]))
    if not yes_no("This looks right? Nothing is saved until you say yes.", True):
        say("  Cancelled. Nothing was changed.")
        return Result(preset=preset, cancelled=True, home=home)

    backup = apply_choices(home, preset, name, env_changes, plan)
    if backup:
        say(f"  Your old settings are backed up as {backup.name}")
    say(f"  Saved to {home}")
    if remote:
        say(f"  On the other machine put ANEXIS_URL=http://<this server>:8765 and the same ANEXIS_TOKEN "
            f"in its .env. Your ANEXIS_TOKEN is in {home / '.env'}.")
    return Result(preset=preset, home=home, plan=plan)


def run_keys(
    home: Path,
    env: dict,
    ask: Callable[..., str],
    say: Callable[[str], None],
    yes: bool = False,
) -> dict[str, str]:
    """The key step, run after everything is downloaded. Every option that
    needs a key is asked about on its own. Returns what changed, by name,
    without the key values.

    Enter skips an option or keeps its saved key. A single - removes it. A key
    already in the environment is filled in without typing. With `yes` nothing
    is asked and only the environment is used.
    """
    home = Path(home)
    saved = read_dotenv(home / ".env")
    changes: dict[str, str] = {}
    total = len(KEY_OPTIONS)
    if not yes:
        say(window("Anexis setup   Keys", [
            "Everything is downloaded. Now the keys, one option at a time.",
            "Paste a key and press Enter. What you type stays hidden.",
            "Enter alone skips the option, or keeps the key it already has.",
            "A single - removes a saved key.",
        ]))

    for number, option in enumerate(KEY_OPTIONS, 1):
        in_file, in_env = saved.get(option.env, ""), env.get(option.env, "")
        if in_env and not in_file:
            changes[option.env] = in_env  # into the file, so a background Anexis has it too
        if yes:
            continue
        if in_file:
            now = f"saved already, ends in ...{in_file[-4:]}"
        elif in_env:
            now = f"found in your environment, ends in ...{in_env[-4:]}. Filled in for you."
        else:
            now = "not set"
        say(f"\n  {number} of {total}  {option.title}\n"
            f"          Turns on: {option.turns_on}\n"
            f"          Get one:  {option.get_it}\n"
            f"          Now:      {now}")
        answer = ask(f"         {option.label}: ", "", True).strip()
        if answer == "-":
            changes[option.env] = ""
            say("          removed")
        elif answer:
            changes[option.env] = answer
            warning = key_warning(option.env, answer)
            say(f"          saved, ends in ...{answer[-4:]}" + (f"\n          {warning}" if warning else ""))
        elif not (in_file or in_env):
            say("          skipped")

    if changes:
        update_env_file(home / ".env", changes)
    final = {**saved, **changes}
    say(f"\n  Keys saved to {home / '.env'}, readable only by you." if changes else "\n  No keys changed.")
    for option in KEY_OPTIONS:
        say(f"    {'on ' if final.get(option.env) else 'off'}   {option.title}")
    say("  Add or change a key any time with: anexis setup --keys")

    plan = home / "setup-plan"
    preset = read_plan(plan).get("PRESET", "") if plan.is_file() else ""
    if preset == "cloud" and not final.get("NVIDIA_API_KEY"):
        say(f"  The cloud preset runs on Nvidia. Anexis cannot talk until NVIDIA_API_KEY is in {home / '.env'}.")
    return {name: ("set" if value else "removed") for name, value in changes.items()}
