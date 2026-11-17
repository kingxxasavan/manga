import json
import tomllib

import httpx
import pytest

from anexis.config import Provider, load_settings
from anexis.desktop import models
from anexis.llm.provider import OpenAIProvider

HAS = ["meta/llama-4-70b-instruct", "meta/llama-4-8b-instruct", "nvidia/nv-embed-v2", "nvidia/llama-guard", "qwen/qwen3-vision-32b"]


def fake_provider(monkeypatch, have=HAS, fail=None):
    """Stands in for the provider's website: a model list, chat and embeddings."""
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append((request.url.path, request.headers.get("authorization", "")))
        if fail and request.url.host in fail:
            return httpx.Response(503, text="down for maintenance")
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in have]})
        body = json.loads(request.content)
        if body["model"] not in have:
            return httpx.Response(410, json={"title": "Gone", "detail": f"The model '{body['model']}' has reached its end of life"})
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"embedding": [0.1] * 8}]})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    def client(entry, env):
        key_env = entry.get("api_key_env", "")
        cfg = Provider(entry["name"], entry["base_url"], key_env, env.get(key_env, "") if key_env else "", dict(entry.get("models", {})))
        return OpenAIProvider(cfg, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(models, "_client", client)
    return asked


@pytest.fixture
def cloud(settings):
    """A setup like the cloud preset made: Nvidia only, with the model that got retired."""
    settings.home.mkdir(parents=True, exist_ok=True)
    (settings.home / "anexis.toml").write_text(
        'name = "Nex"\n\n[[providers]]\nname = "nvidia"\nbase_url = "https://integrate.api.nvidia.com/v1"\n'
        'api_key_env = "NVIDIA_API_KEY"\nembed_input_type = true\n[providers.models]\n'
        'chat = "meta/llama-3.3-70b-instruct"\nembed = "nvidia/nv-embedqa-e5-v5"\n\n[agent]\ncontrol = "full"\nmax_steps = 10\n'
    )
    settings.env = {"NVIDIA_API_KEY": "nvapi-test"}
    return settings


def test_a_suggestion_fits_the_job_and_skips_models_that_cannot_chat():
    assert models.suggest(HAS, "chat") == "meta/llama-4-70b-instruct"   # the bigger of the two, never the guard or embed one
    assert models.suggest(HAS, "embed") == "nvidia/nv-embed-v2"
    assert models.suggest(HAS, "vision") == "qwen/qwen3-vision-32b"
    assert models.suggest(["nvidia/nv-embed-v2"], "chat") == "" and models.suggest([], "chat") == ""


async def test_a_retired_model_is_flagged_with_something_to_use_instead(cloud, monkeypatch):
    asked = fake_provider(monkeypatch)
    state = await models.state(cloud)
    nvidia, ollama, ollama_cloud = state["providers"]
    assert nvidia["enabled"] and nvidia["reachable"] and nvidia["available"] == sorted(HAS)
    assert nvidia["missing"] == ["meta/llama-3.3-70b-instruct", "nvidia/nv-embedqa-e5-v5"]
    assert nvidia["suggested"] == {"chat": "meta/llama-4-70b-instruct", "embed": "nvidia/nv-embed-v2"}
    assert ("/v1/models", "Bearer nvapi-test") in asked
    # the ones not turned on are offered too
    assert (ollama["name"], ollama["enabled"], ollama["kind"]) == ("ollama", False, "local")
    assert ollama_cloud["enabled"] is False and "OLLAMA_API_KEY" in ollama_cloud["error"] and not ollama_cloud["reachable"]
    assert [r["name"] for r in state["roles"]] == ["chat", "coder", "small", "embed", "vision"]


async def test_a_provider_that_is_down_says_so_and_the_rest_still_load(cloud, monkeypatch):
    fake_provider(monkeypatch, fail={"integrate.api.nvidia.com"})
    nvidia, ollama, _ = (await models.state(cloud))["providers"]
    assert nvidia["reachable"] is False and "503" in nvidia["error"]
    assert ollama["reachable"] is True


def test_saving_sets_models_and_order_and_keeps_every_other_setting(cloud):
    backup = models.save(cloud, [
        {"name": "ollama", "enabled": True, "models": {"chat": "qwen3:8b", "embed": "nomic-embed-text", "coder": ""}},
        {"name": "nvidia", "enabled": True, "models": {"chat": "meta/llama-4-70b-instruct", "vision": "qwen/qwen3-vision-32b"}},
        {"name": "ollama-cloud", "enabled": False, "models": {"chat": "x"}},
    ])
    assert backup.name.startswith("anexis.toml.bak-") and "llama-3.3" in backup.read_text()
    saved = tomllib.loads((cloud.home / "anexis.toml").read_text())
    assert saved["name"] == "Nex" and saved["agent"] == {"control": "full", "max_steps": 10}
    assert [p["name"] for p in saved["providers"]] == ["ollama", "nvidia"]
    assert saved["providers"][0]["models"] == {"chat": "qwen3:8b", "embed": "nomic-embed-text"}
    loaded = load_settings(env={"ANEXIS_HOME": str(cloud.home), "NVIDIA_API_KEY": "nvapi-test"})
    assert [p.name for p in loaded.active_providers()] == ["ollama", "nvidia"] and loaded.control == "full"
    nvidia = loaded.providers[1]
    assert nvidia.models == {"chat": "meta/llama-4-70b-instruct", "vision": "qwen/qwen3-vision-32b"} and nvidia.embed_input_type is True


def test_saving_refuses_to_leave_no_provider_or_write_a_strange_name(cloud):
    before = (cloud.home / "anexis.toml").read_text()
    with pytest.raises(ValueError, match="at least one provider"):
        models.save(cloud, [{"name": "nvidia", "enabled": False, "models": {}}])
    with pytest.raises(ValueError, match="not a model name"):
        models.save(cloud, [{"name": "nvidia", "enabled": True, "models": {"chat": 'a"\nname = "x'}}])
    with pytest.raises(ValueError, match="at least one provider"):
        models.save(cloud, [{"name": "made-up", "enabled": True, "models": {"chat": "x"}}])
    assert (cloud.home / "anexis.toml").read_text() == before


async def test_a_model_can_be_tried_before_it_is_saved(cloud, monkeypatch):
    fake_provider(monkeypatch)
    good = await models.test(cloud, "nvidia", "meta/llama-4-70b-instruct")
    assert good["ok"] and good["said"] == "ok" and good["ms"] >= 0
    gone = await models.test(cloud, "nvidia", "meta/llama-3.3-70b-instruct")
    assert gone["ok"] is False and "end of life" in gone["error"]
    assert (await models.test(cloud, "nvidia", "nvidia/nv-embed-v2", "embed"))["said"] == "8 numbers per text"
    assert (await models.test(cloud, "nope", "x"))["ok"] is False


async def test_the_models_routes(live, settings, monkeypatch):
    fake_provider(monkeypatch)
    _, client = await live()
    async with httpx.AsyncClient(base_url=client.url) as http:
        state = (await http.get("/models")).json()
        assert [p["name"] for p in state["providers"]] == ["ollama", "nvidia", "ollama-cloud"]
        saved = await http.post("/models", json={"providers": [{"name": "ollama", "enabled": True, "models": {"chat": "qwen3:8b"}}]})
        assert saved.json()["saved"] and saved.json()["restart"]
        assert (await http.post("/models", json={"providers": []})).status_code == 400
        assert (await http.post("/models/test", json={"provider": "ollama", "model": ""})).status_code == 400
        tried = (await http.post("/models/test", json={"provider": "ollama", "model": "meta/llama-4-8b-instruct"})).json()
        assert tried["ok"] is True
    assert tomllib.loads((settings.home / "anexis.toml").read_text())["providers"][0]["models"] == {"chat": "qwen3:8b"}


async def test_the_claude_route_reports_sign_in_usage_and_the_switch(live, settings, monkeypatch, tmp_path):
    from tests.test_coder import FAKE

    settings.claude_bin = FAKE
    monkeypatch.setenv("FAKE_CLAUDE_USAGE", "91")
    _, client = await live()
    async with httpx.AsyncClient(base_url=client.url, timeout=30) as http:
        state = (await http.get("/claude")).json()
        assert state["signed_in"] and state["plan"] and state["usage"]["percent"] == 91
        assert state["model"] == "opus" and "91% used" in state["note"] and state["switch_percent"] == 85
        changed = (await http.post("/claude", json={"switch_percent": 95, "switch_model": "sonnet"})).json()
        assert changed["switch_percent"] == 95 and changed["model"] == "its best model"
        assert (await http.post("/claude", json={"switch_percent": 150})).status_code == 400
    coder = tomllib.loads((settings.home / "anexis.toml").read_text())["coder"]
    assert coder == {"claude_switch_percent": 95, "claude_switch_model": "sonnet"}
