"""Which model does which job, picked from what each provider really has.

Model names go out of date: providers retire models, and a name that worked
last month answers "gone" today. So nothing here trusts a fixed name. The
list of models comes live from the provider, the owner picks from it in the
app, and a pick can be tried before it is saved.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
import tomllib
from pathlib import Path

from anexis.config import DEFAULT_PROVIDERS, Provider, find_config
from anexis.desktop.config_file import dump
from anexis.llm.provider import OpenAIProvider, ProviderError

ROLES = ("chat", "coder", "small", "embed", "vision")
ROLE_ABOUT = {
    "chat": "talking and using tools. The one that matters most",
    "coder": "writing code when Claude cannot. Empty uses the chat model",
    "small": "quick background jobs like learning from what you say. Empty uses the chat model",
    "embed": "meaning search in memory. Empty turns that off for this provider",
    "vision": "looking at the screen. Empty means it cannot see",
}

# The providers Anexis knows how to reach. All of them speak the same API, so
# anything else that does can be added by hand in anexis.toml and shows up too.
CATALOG = [
    {"name": "ollama", "title": "Ollama on this computer", "kind": "local",
     "about": "Free and private. Runs on your own GPU or CPU.",
     "base_url": "http://localhost:11434/v1", "api_key_env": ""},
    {"name": "nvidia", "title": "Nvidia", "kind": "cloud",
     "about": "Big hosted models. Free key at build.nvidia.com.",
     "base_url": "https://integrate.api.nvidia.com/v1", "api_key_env": "NVIDIA_API_KEY", "embed_input_type": True},
    {"name": "ollama-cloud", "title": "Ollama cloud", "kind": "cloud",
     "about": "Ollama's hosted models. Key at ollama.com/settings/keys.",
     "base_url": "https://ollama.com/v1", "api_key_env": "OLLAMA_API_KEY"},
]
BY_NAME = {entry["name"]: entry for entry in CATALOG}

# Models worth offering to download for Ollama on this computer, small to big.
OLLAMA_STARTERS = [
    "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen2.5-coder:3b", "qwen2.5-coder:7b", "qwen2.5-coder:14b",
    "llama3.2:3b", "gemma3:4b", "gemma3:12b", "deepseek-r1:8b", "llava:7b", "nomic-embed-text",
]

# Used only to SUGGEST a model when the saved one is gone. The owner decides.
NOT_FOR_CHAT = re.compile(r"embed|rerank|guard|safety|whisper|tts|asr|ocr|parse|retriev|clip|nv-|bge|e5|diffusion|flux|sdxl", re.I)
PREFER = {
    "chat": [r"llama-?[4-9]", r"llama-3\.[3-9]", r"qwen-?3", r"deepseek", r"mistral-(large|medium)", r"gpt-oss", r"instruct", r"chat"],
    "embed": [r"nv-embed", r"embedqa", r"e5", r"bge", r"arctic", r"embed"],
    "vision": [r"vision", r"vlm", r"-vl\b", r"llava", r"pixtral"],
}


def suggest(available: list[str], role: str) -> str:
    """A reasonable model for a job out of what the provider has, or ""."""
    role = role if role in PREFER else "chat"
    pool = [m for m in available if not NOT_FOR_CHAT.search(m)] if role == "chat" else list(available)
    for pattern in PREFER[role]:
        hits = sorted(m for m in pool if re.search(pattern, m, re.I))
        if hits:
            # Among lookalikes take the biggest "70b" style size, a fair stand in for the best.
            def size(name: str) -> float:
                found = re.search(r"(\d+(?:\.\d+)?)b\b", name, re.I)
                return float(found.group(1)) if found else 0.0

            return max(hits, key=size)
    return ""


def config_path(settings) -> Path:
    return find_config(settings.home) or settings.home / "anexis.toml"


def read_config(settings) -> dict:
    path = config_path(settings)
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if "providers" not in data:
        data["providers"] = [dict(p, models=dict(p["models"])) for p in DEFAULT_PROVIDERS]
    return data


def _entry(name: str, saved: dict | None) -> dict:
    """What is known about one provider: the catalog's facts, overridden by
    whatever the settings file says."""
    known = BY_NAME.get(name, {"name": name, "title": name, "kind": "cloud", "about": "Added by hand in anexis.toml."})
    merged = {**known, **{k: v for k, v in (saved or {}).items() if k != "models"}}
    merged["models"] = dict((saved or {}).get("models", {}))
    return merged


def _client(entry: dict, env) -> OpenAIProvider:
    key_env = entry.get("api_key_env", "")
    cfg = Provider(
        name=entry["name"], base_url=entry["base_url"].rstrip("/"), api_key_env=key_env,
        api_key=env.get(key_env, "") if key_env else "", models=dict(entry.get("models", {})),
        embed_input_type=bool(entry.get("embed_input_type", False)),
    )
    return OpenAIProvider(cfg, timeout=60.0)


async def _look(entry: dict, enabled: bool, env) -> dict:
    """One provider as the Models screen shows it."""
    key_env = entry.get("api_key_env", "")
    has_key = bool(env.get(key_env)) if key_env else True
    out = {
        "name": entry["name"], "title": entry["title"], "kind": entry["kind"], "about": entry.get("about", ""),
        "enabled": enabled, "key_env": key_env, "has_key": has_key, "models": entry["models"],
        "reachable": False, "error": "", "available": [], "missing": [], "suggested": {},
    }
    if entry["name"] == "ollama":
        out["installed"] = bool(shutil.which("ollama")) or _ollama_on_windows()
        out["starters"] = OLLAMA_STARTERS
    if not has_key:
        out["error"] = f"Needs a key. Add {key_env} in Keys."
        return out
    client = _client(entry, env)
    try:
        out["available"] = sorted(m for m in await client.models() if m)
        out["reachable"] = True
    except ProviderError as e:
        said = str(e)
        if entry["name"] == "ollama":
            said = "Ollama is not running on this computer." if out.get("installed") else "Ollama is not installed on this computer."
        out["error"] = said[:300]
    finally:
        await client.close()
    if out["reachable"]:
        known = set(out["available"]) | {m.removesuffix(":latest") for m in out["available"]}
        out["missing"] = sorted({m for m in entry["models"].values() if m and m not in known})
        gone = {role for role, model in entry["models"].items() if model in out["missing"]}
        wanted = gone | ({"chat"} if not entry["models"].get("chat") else set())
        out["suggested"] = {role: pick for role in wanted if (pick := suggest(out["available"], role))}
    return out


def _ollama_on_windows() -> bool:
    from anexis.cli.setup import find_ollama

    return bool(find_ollama())


async def state(settings, env=None) -> dict:
    """Every provider, saved ones first in the order they are tried, each
    with the models it really has right now. `env` is for keys that were
    just saved and are not loaded into the running settings yet."""
    env = settings.env if env is None else env
    saved = read_config(settings)["providers"]
    names = [p["name"] for p in saved]
    entries = [(_entry(p["name"], p), True) for p in saved]
    entries += [(_entry(c["name"], None), False) for c in CATALOG if c["name"] not in names]
    looked = await asyncio.gather(*(_look(entry, enabled, env) for entry, enabled in entries))
    return {"roles": [{"name": r, "about": ROLE_ABOUT[r]} for r in ROLES], "providers": list(looked)}


async def heal(settings, env=None) -> dict:
    """Swaps models the provider no longer has for its closest current ones,
    and saves. A retired model otherwise leaves Anexis unable to answer at
    all. Returns {provider: {role: [old, new]}}, empty when nothing was wrong
    or nothing could be suggested."""
    now = await state(settings, env)
    changed: dict = {}
    wanted = []
    for p in now["providers"]:
        models = dict(p["models"])
        for role, pick in p["suggested"].items():
            if p["enabled"] and models.get(role) != pick:
                changed.setdefault(p["name"], {})[role] = [models.get(role, ""), pick]
                models[role] = pick
        # a job whose model is gone and has no stand in is left empty, which falls back to the chat model
        for role, model in list(models.items()):
            if model in p["missing"] and role not in p["suggested"] and p["enabled"]:
                changed.setdefault(p["name"], {})[role] = [model, ""]
                models[role] = ""
        wanted.append({"name": p["name"], "enabled": p["enabled"], "models": models})
    if changed:
        save(settings, wanted)
    return changed


def save(settings, wanted: list[dict]) -> Path | None:
    """Writes the providers part of the settings. `wanted` is the list from
    the Models screen: [{name, enabled, models: {role: model}}] in the order
    to try them. Returns the backup of the old file when there was one."""
    data = read_config(settings)
    before = {p["name"]: p for p in data["providers"]}
    providers = []
    for item in wanted:
        name = str(item.get("name", ""))
        if not item.get("enabled") or not (name in before or name in BY_NAME):
            continue
        entry = _entry(name, before.get(name))
        models = {role: str(model).strip() for role, model in (item.get("models") or {}).items()
                  if role in ROLES and str(model or "").strip()}
        for model in models.values():
            if len(model) > 200 or any(c in model for c in "\n\r\"'"):
                raise ValueError(f"That is not a model name: {model[:60]}")
        block = {"name": name, "base_url": entry["base_url"]}
        if entry.get("api_key_env"):
            block["api_key_env"] = entry["api_key_env"]
        if entry.get("embed_input_type"):
            block["embed_input_type"] = True
        block["models"] = models
        providers.append(block)
    if not providers:
        raise ValueError("Turn on at least one provider, or Anexis has nothing to think with.")
    data["providers"] = providers
    path = config_path(settings)
    backup = None
    if path.is_file():
        backup = path.with_name(f"anexis.toml.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(data), encoding="utf-8")
    return backup


async def test(settings, name: str, model: str, role: str = "chat") -> dict:
    """Tries one model for real, before it is saved: a one word chat, or a
    one word embedding. Says how long it took, or what went wrong."""
    saved = {p["name"]: p for p in read_config(settings)["providers"]}
    if name not in saved and name not in BY_NAME:
        return {"ok": False, "error": "No provider with that name."}
    client = _client(_entry(name, saved.get(name)), settings.env)
    started = time.monotonic()
    try:
        if role == "embed":
            vectors = await client.embed(model, ["hello"], "query")
            said = f"{len(vectors[0])} numbers per text"
        else:
            reply = await client.chat(model, [{"role": "user", "content": "Reply with one word: ok"}], stream=False)
            said = reply.content.strip()[:80] or "(it answered with nothing)"
        return {"ok": True, "said": said, "ms": round((time.monotonic() - started) * 1000)}
    except ProviderError as e:
        return {"ok": False, "error": str(e)[:400]}
    finally:
        await client.close()
