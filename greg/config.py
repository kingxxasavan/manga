"""Settings: defaults, then greg.toml, then .env files, then the real environment.

Secrets only ever come from the environment or a .env file, never from greg.toml,
so the config file is safe to share.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# Model roles: chat (talking and tools), coder (fallback code writing),
# small (memory extraction and summaries), embed (meaning search).
DEFAULT_PROVIDERS = [
    {
        "name": "ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "",
        "models": {
            "chat": "qwen3:8b",
            "coder": "qwen2.5-coder:7b",
            "small": "qwen3:4b",
            "embed": "nomic-embed-text",
        },
    },
    {
        "name": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "embed_input_type": True,
        # One model known to support tool calling does every job here. A role
        # that is not listed uses the chat model. Swap in others in greg.toml.
        "models": {
            "chat": "meta/llama-3.3-70b-instruct",
            "embed": "nvidia/nv-embedqa-e5-v5",
        },
    },
]


@dataclass
class Provider:
    name: str
    base_url: str
    api_key_env: str = ""
    api_key: str = ""
    models: dict[str, str] = field(default_factory=dict)
    # Nvidia embedding models want to know if text is a stored passage or a query.
    embed_input_type: bool = False

    @property
    def active(self) -> bool:
        """A provider that needs a key is only used once the key is present."""
        return bool(self.api_key) or not self.api_key_env


@dataclass
class Settings:
    name: str = "Greg"
    home: Path = Path("~/.greg")
    workspace: Path = Path("~/greg/workspace")
    manifest: Path = REPO_ROOT / "tools" / "manifest.yaml"

    host: str = "127.0.0.1"
    port: int = 8765
    token: str = ""

    providers: list[Provider] = field(default_factory=list)
    request_timeout: float = 300.0
    provider_cooldown: float = 60.0

    recall_k: int = 8
    history_messages: int = 24
    history_chars: int = 24000  # about 6000 tokens of past conversation
    learn: bool = True
    consolidate_minutes: int = 60

    max_steps: int = 8
    max_tools: int = 12
    tool_output_chars: int = 6000
    confirm_timeout: float = 300.0
    # tool name -> "allow" or "ask", to loosen or tighten one tool
    permissions: dict[str, str] = field(default_factory=dict)

    claude_bin: str = "claude"
    claude_model: str = ""
    claude_timeout: float = 1800.0
    claude_backoff_minutes: int = 30
    fallback_rounds: int = 12

    stt_model: str = "base"
    tts_voice: str = "en_US-lessac-medium"
    piper_bin: str = "piper"

    env: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.home = Path(self.home).expanduser()
        self.workspace = Path(self.workspace).expanduser()
        self.manifest = Path(self.manifest).expanduser()
        if not self.providers:
            self.providers = [_provider(p, self.env) for p in DEFAULT_PROVIDERS]

    @property
    def db_path(self) -> Path:
        return self.home / "greg.db"

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}"

    def active_providers(self) -> list[Provider]:
        return [p for p in self.providers if p.active]

    def problems(self) -> list[str]:
        """Config mistakes that must stop the server from starting."""
        out = []
        if self.host not in LOOPBACK and not self.token:
            out.append(
                "No token set. Listening beyond localhost needs GREG_TOKEN so strangers "
                "cannot talk to your assistant."
            )
        if not self.active_providers():
            out.append("No model provider is usable. Start Ollama or set NVIDIA_API_KEY.")
        return out


def _provider(raw: Mapping, env: Mapping[str, str]) -> Provider:
    key_env = raw.get("api_key_env", "")
    return Provider(
        name=raw["name"],
        base_url=raw["base_url"].rstrip("/"),
        api_key_env=key_env,
        api_key=env.get(key_env, "") if key_env else "",
        models=dict(raw.get("models", {})),
        embed_input_type=bool(raw.get("embed_input_type", False)),
    )


def read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip().removeprefix("export ").strip()] = value
    return out


_UNSET = object()


def find_config(home: Path) -> Path | None:
    for candidate in (Path.cwd() / "greg.toml", home / "greg.toml"):
        if candidate.is_file():
            return candidate
    return None


def load_settings(env: Mapping[str, str] | None = None, config_path=_UNSET) -> Settings:
    real = dict(os.environ if env is None else env)
    home = Path(real.get("GREG_HOME", "~/.greg")).expanduser()

    merged: dict[str, str] = {}
    dotenvs = [home / ".env"] + ([REPO_ROOT / ".env", Path.cwd() / ".env"] if env is None else [])
    for path in dotenvs:
        merged.update(read_dotenv(path))
    merged.update(real)  # the real environment always wins

    if config_path is _UNSET:
        explicit = merged.get("GREG_CONFIG")
        config_path = Path(explicit) if explicit else find_config(home)
    cfg = tomllib.loads(Path(config_path).read_text()) if config_path else {}

    def section(name: str) -> dict:
        return cfg.get(name, {})

    flat: dict = {"home": home, "env": merged}
    for key in ("name", "workspace", "manifest"):
        if key in cfg:
            flat[key] = cfg[key]
    flat.update({k: v for k, v in section("server").items() if k in ("host", "port")})
    for name in ("memory", "agent", "coder", "voice", "llm"):
        flat.update(section(name))
    flat["permissions"] = dict(section("permissions"))
    if "providers" in cfg:
        flat["providers"] = [_provider(p, merged) for p in cfg["providers"]]

    if "GREG_WORKSPACE" in merged:
        flat["workspace"] = merged["GREG_WORKSPACE"]
    if "GREG_HOST" in merged:
        flat["host"] = merged["GREG_HOST"]
    if "GREG_PORT" in merged:
        flat["port"] = int(merged["GREG_PORT"])
    flat["token"] = merged.get("GREG_TOKEN", "")

    known = Settings.__dataclass_fields__
    unknown = sorted(k for k in flat if k not in known)
    if unknown:
        raise ValueError(f"Unknown settings in config: {', '.join(unknown)}")
    return Settings(**flat)
