import json
import tomllib

import httpx

from anexis.config import load_settings, read_dotenv
from anexis.desktop import install


async def api(client, method, path, **kw):
    async with httpx.AsyncClient(base_url=client.url, timeout=30) as http:
        return await http.request(method, path, **kw)


async def test_setup_state_describes_the_machine_presets_and_keys(live, settings):
    _, client = await live()
    state = (await api(client, "GET", "/setup")).json()
    assert state["done"] is False
    assert [p["name"] for p in state["presets"]] == ["max", "balanced", "light", "cloud"]
    assert state["best"] in ("max", "balanced", "light", "cloud") and state["machine"]["ram_gb"] > 0
    nvidia = state["keys"][0]
    assert nvidia["env"] == "NVIDIA_API_KEY" and nvidia["set"] is False and nvidia["get_it"]


async def test_applying_setup_writes_settings_with_full_control(live, settings):
    _, client = await live()
    body = {"preset": "cloud", "name": "Nex", "control": "full", "voice": False,
            "keys": {"NVIDIA_API_KEY": "nvapi-abcdefghijklmnop"}}
    reply = (await api(client, "POST", "/setup", json=body)).json()
    assert reply["saved"] and reply["restart"] and reply["warnings"] == {}
    loaded = load_settings(env={"ANEXIS_HOME": str(settings.home)})
    assert loaded.control == "full" and loaded.name == "Nex"
    assert [p.name for p in loaded.active_providers()] == ["nvidia"]
    state = (await api(client, "GET", "/setup")).json()
    assert state["done"] is True and state["preset"] == "cloud"
    assert state["keys"][0]["set"] is True and state["keys"][0]["ends"] == "mnop"


async def test_applying_setup_twice_backs_up_the_old_settings(live, settings):
    _, client = await live()
    await api(client, "POST", "/setup", json={"preset": "light", "name": "One"})
    reply = (await api(client, "POST", "/setup", json={"preset": "balanced", "name": "Two", "control": "ask"})).json()
    assert reply["backup"].startswith("anexis.toml.bak-")
    assert tomllib.loads((settings.home / reply["backup"]).read_text())["name"] == "One"
    now = tomllib.loads((settings.home / "anexis.toml").read_text())
    assert now["name"] == "Two" and now["agent"]["control"] == "ask"


async def test_awkward_keys_survive_and_a_dash_removes_one(live, settings):
    _, client = await live()
    odd = 'ab"c d$e\'f#g=h\\i-long-enough'
    reply = (await api(client, "POST", "/setup", json={"keys": {"EXA_API_KEY": odd, "GITHUB_TOKEN": "ghp_abcdefghijklmnop"}})).json()
    assert "space" in reply["warnings"]["EXA_API_KEY"] and "GITHUB_TOKEN" not in reply["warnings"]
    saved = read_dotenv(settings.home / ".env")
    assert saved["EXA_API_KEY"] == odd and saved["GITHUB_TOKEN"] == "ghp_abcdefghijklmnop"
    await api(client, "POST", "/setup", json={"keys": {"EXA_API_KEY": "-"}})
    saved = read_dotenv(settings.home / ".env")
    assert "EXA_API_KEY" not in saved and saved["GITHUB_TOKEN"] == "ghp_abcdefghijklmnop"


async def test_setup_only_writes_keys_it_knows_and_real_presets(live, settings):
    _, client = await live()
    assert (await api(client, "POST", "/setup", json={"keys": {"ANEXIS_HOST": "0.0.0.0"}})).status_code == 400
    assert (await api(client, "POST", "/setup", json={"keys": {"EXA_API_KEY": "abc\nANEXIS_HOST=0.0.0.0"}})).status_code == 400
    assert (await api(client, "POST", "/setup", json={"preset": "turbo"})).status_code == 400
    assert not (settings.home / ".env").exists() and not (settings.home / "anexis.toml").exists()


def scripted(codes=None, lines=None):
    """A stand in for running programs: records each command, replays lines."""
    seen = []

    async def run(argv, on_line, env=None, cwd=None):
        seen.append(argv)
        for line in (lines or {}).get(argv[1] if len(argv) > 1 else "", []):
            on_line(line)
        return (codes or {}).get(argv[1] if len(argv) > 1 else "", 0)

    return run, seen


async def fetch_nothing(url, dest, on_percent):
    on_percent(100)


async def test_install_runs_the_chosen_steps_in_order_and_reports_each(settings, monkeypatch):
    monkeypatch.setattr(install, "find_ollama", lambda: "/usr/bin/ollama")

    async def up():
        return True

    monkeypatch.setattr(install, "_ollama_up", up)
    run, seen = scripted(lines={"pull": ["pulling manifest", "pulling 6a0746a1ec1a  42% ▕██   ▏ 2.0 GB/4.7 GB"]})
    events = []
    ok = await install.install(settings, {"tools": True, "models": ["qwen3:8b", "nomic-embed-text"], "ollama": True},
                               events.append, run, fetch_nothing)
    assert ok is True
    assert [(e.get("step"), e["state"]) for e in events if e["state"] != "progress"] == [
        ("ollama", "start"), ("ollama", "done"), ("models", "start"), ("models", "done"),
        ("tools", "start"), ("tools", "done"), (None, "finished"),
    ]
    assert [argv[1:] for argv in seen[:2]] == [["pull", "qwen3:8b"], ["pull", "nomic-embed-text"]]
    assert seen[2][1:] == ["-m", "anexis", "tools", "sync"]
    assert any(e.get("percent") == 42 for e in events)


async def test_a_failed_step_is_reported_and_the_rest_still_run(settings, monkeypatch):
    monkeypatch.setattr(install, "find_ollama", lambda: "/usr/bin/ollama")

    async def up():
        return True

    monkeypatch.setattr(install, "_ollama_up", up)
    run, _ = scripted(codes={"pull": 1})
    events = []
    ok = await install.install(settings, {"models": ["qwen3:8b"], "tools": True}, events.append, run, fetch_nothing)
    states = {e.get("step"): e["state"] for e in events if e["state"] in ("done", "failed", "skipped")}
    assert ok is False and states == {"models": "failed", "tools": "done"}
    assert "qwen3:8b" in next(e["message"] for e in events if e["state"] == "failed")
    assert events[-1] == {"state": "finished", "ok": False}


async def test_models_are_skipped_when_ollama_could_not_be_installed(settings, monkeypatch):
    monkeypatch.setattr(install, "find_ollama", lambda: None)
    monkeypatch.setattr(install, "IS_WINDOWS", False)
    run, seen = scripted()
    events = []
    await install.install(settings, {"ollama": True, "models": ["qwen3:8b"]}, events.append, run, fetch_nothing)
    states = {e.get("step"): e["state"] for e in events if e["state"] in ("done", "failed", "skipped")}
    assert states == {"ollama": "failed", "models": "skipped"} and seen == []


async def test_a_model_name_is_never_passed_on_unless_it_looks_like_one(settings, monkeypatch):
    monkeypatch.setattr(install, "find_ollama", lambda: "/usr/bin/ollama")
    run, seen = scripted()
    events = []
    await install.install(settings, {"models": ["qwen3:8b; rm -rf ~"]}, events.append, run, fetch_nothing)
    assert seen == [] and events[1]["state"] == "failed"


async def test_run_lines_splits_progress_bars_into_lines(tmp_path):
    import sys

    script = "import sys; sys.stdout.write('one\\rtwo 50%\\rthree\\nfour'); sys.stdout.flush()"
    lines = []
    assert await install.run_lines([sys.executable, "-c", script], lines.append) == 0
    assert lines == ["one", "two 50%", "three", "four"]


async def test_the_install_route_streams_progress(live, monkeypatch):
    async def fake_install(settings, wanted, emit, run=None, fetch=None):
        emit({"step": "tools", "state": "start"})
        emit({"step": "tools", "state": "done", "message": "downloaded"})
        emit({"state": "finished", "ok": True})
        return True

    monkeypatch.setattr(install, "install", fake_install)
    _, client = await live()
    reply = await api(client, "POST", "/setup/install", json={"tools": True})
    events = [json.loads(line) for line in reply.text.splitlines() if line.strip()]
    assert [e["state"] for e in events] == ["start", "done", "finished"]
