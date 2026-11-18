import tomllib

import httpx

from anexis.desktop.config_file import set_values


async def api(client, method, path, **kw):
    async with httpx.AsyncClient(base_url=client.url, timeout=30) as http:
        return await http.request(method, path, **kw)


async def test_system_stats_has_every_number_the_panel_shows(live):
    _, client = await live()
    stats = (await api(client, "GET", "/system/stats")).json()
    assert 0 <= stats["cpu"] <= 100 and len(stats["cores"]) >= 1
    assert 0 < stats["memory"]["used"] <= stats["memory"]["total"]
    assert stats["disks"] and stats["disks"][0]["total"] > 0
    assert set(stats["net"]) >= {"up", "down"} and stats["uptime"] > 0
    assert stats["processes"] and {"pid", "name", "cpu", "memory"} <= set(stats["processes"][0])
    assert stats["host"] and stats["os"]


async def test_files_lists_folders_first_and_handles_odd_names(live, settings):
    _, client = await live()
    odd = settings.workspace / "my föld er"
    odd.mkdir(parents=True)
    (odd / "notes ünï.txt").write_text("hello")
    (odd / "inner").mkdir()
    top = (await api(client, "GET", "/files")).json()
    assert top["path"] == str(settings.workspace.resolve())
    assert [e["name"] for e in top["entries"]] == ["my föld er"]
    inside = (await api(client, "GET", "/files", params={"path": str(odd)})).json()
    assert [(e["name"], e["dir"], e["size"]) for e in inside["entries"]] == [("inner", True, 0), ("notes ünï.txt", False, 5)]
    assert inside["parent"] == str(settings.workspace.resolve())


async def test_files_says_so_when_the_folder_is_missing_or_a_file(live, settings):
    _, client = await live()
    settings.workspace.mkdir(parents=True, exist_ok=True)
    (settings.workspace / "a.txt").write_text("x")
    assert (await api(client, "GET", "/files", params={"path": str(settings.workspace / "nope")})).status_code == 404
    assert (await api(client, "GET", "/files", params={"path": str(settings.workspace / "a.txt")})).status_code == 404
    assert (await api(client, "POST", "/files/open", json={"path": str(settings.workspace / "nope")})).status_code == 404


async def test_file_roots_start_with_the_workspace(live, settings):
    _, client = await live()
    roots = (await api(client, "GET", "/files/roots")).json()
    assert roots[0] == {"name": "Workspace", "path": str(settings.workspace)}


async def test_open_hands_the_path_over_whole(live, settings, monkeypatch):
    from anexis.desktop import routes

    opened = []
    monkeypatch.setattr(routes, "open_with_default_app", opened.append)
    _, client = await live()
    target = settings.workspace / "my föld er" / "a b;rm -rf.txt"
    target.parent.mkdir(parents=True)
    target.write_text("x")
    assert (await api(client, "POST", "/files/open", json={"path": str(target)})).status_code == 200
    assert opened == [str(target)]


async def test_control_can_be_switched_live_and_is_saved(live, settings):
    anexis, client = await live()
    (settings.home / "anexis.toml").write_text('# mine\nname = "Anexis"\n\n[[providers]]\nname = "ollama"\nbase_url = "http://x/v1"\n')
    reply = (await api(client, "POST", "/settings", json={"control": "full", "name": "Nex"})).json()
    assert reply["control"] == "full" and reply["name"] == "Nex"
    assert anexis.settings.control == "full"
    saved = tomllib.loads((settings.home / "anexis.toml").read_text())
    assert saved["agent"]["control"] == "full" and saved["name"] == "Nex"
    assert saved["providers"][0]["name"] == "ollama"
    assert (settings.home / "anexis.toml").read_text().startswith("# mine\n")
    assert (await api(client, "POST", "/settings", json={"control": "everything"})).status_code == 400
    assert (await api(client, "GET", "/health")).json()["control"] == "full"


def test_set_values_edits_in_place_and_keeps_the_rest(tmp_path):
    path = tmp_path / "anexis.toml"
    path.write_text('name = "A"\n\n[agent]\nmax_steps = 8\ncontrol = "ask"  # old\n\n[memory]\nrecall_k = 5\n')
    set_values(path, {"agent.control": "full", "name": "B", "voice.stt_model": "small", "agent.max_tools": 16})
    data = tomllib.loads(path.read_text())
    assert data == {"name": "B", "agent": {"max_steps": 8, "control": "full", "max_tools": 16},
                    "memory": {"recall_k": 5}, "voice": {"stt_model": "small"}}


def test_set_values_puts_a_top_key_above_the_first_section(tmp_path):
    path = tmp_path / "anexis.toml"
    path.write_text('[[providers]]\nname = "ollama"\nbase_url = "http://x/v1"\n')
    set_values(path, {"name": 'Say "hi"'})
    data = tomllib.loads(path.read_text())
    assert data["name"] == 'Say "hi"' and data["providers"][0]["name"] == "ollama"


async def test_a_new_conversation_can_be_read_back(live):
    _, client = await live("Hello there")
    sid = (await api(client, "POST", "/sessions/new", json={"mode": "school"})).json()["session_id"]
    async for _ in client.chat("hi", session_id=sid):
        pass
    back = (await api(client, "GET", f"/sessions/{sid}/messages")).json()
    assert back["mode"] == "school"
    assert [(m["role"], m["content"]) for m in back["messages"]] == [("user", "hi"), ("assistant", "Hello there")]
    assert (await api(client, "GET", "/sessions/nope/messages")).status_code == 404


async def test_app_info_and_restart_without_a_supervisor(live, monkeypatch):
    monkeypatch.delenv("ANEXIS_SUPERVISED", raising=False)
    _, client = await live()
    info = (await api(client, "GET", "/app")).json()
    assert info["version"] and info["folder"] and info["supervised"] is False
    assert (await api(client, "POST", "/app/restart")).json()["restarting"] is False


async def test_about_me_sections_are_listed_for_the_form(live):
    _, client = await live()
    sections = (await api(client, "GET", "/aboutme/sections")).json()
    assert sections[0]["key"] == "name" and all({"key", "label", "question", "many"} <= set(s) for s in sections)
