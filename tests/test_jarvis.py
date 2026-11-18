import asyncio
import json
import sys
from pathlib import Path

import httpx

from anexis.cli.jarvis import greeting
from tests.fakes import call

ROOT = Path(__file__).resolve().parent.parent


async def talk(client, home: Path, *lines: str, token: str = "") -> str:
    """Runs the one file jarvis.py the way someone at school would, typing lines."""
    home.mkdir(parents=True, exist_ok=True)
    (home / ".jarvis.json").write_text(json.dumps({"url": client.url, "token": token}))
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(ROOT / "jarvis.py"), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, env={"HOME": str(home), "USERPROFILE": str(home), "PATH": "/usr/bin:/bin"},
    )
    out, _ = await asyncio.wait_for(proc.communicate(("\n".join(lines) + "\n").encode()), 60)
    return out.decode()


async def test_jarvis_from_any_computer_chats_and_remembers_the_chat(live, settings, tmp_path):
    settings.token = "school-token"
    anexis, client = await live("Hey. The chem lab is due Thursday.", "Sure thing.")
    said = await talk(client, tmp_path / "home", "whats due", "and after that?", "/quit", token="school-token")
    assert "jarvis online" in said and "The chem lab is due Thursday." in said and "Sure thing." in said
    chats = anexis.memory.list_sessions()
    assert len(chats) == 1 and chats[0]["messages"] == 4    # both turns in one chat
    assert "later." in said


async def test_jarvis_asks_before_a_risky_tool_and_clear_deletes_the_chat(live, settings, tmp_path):
    _, client = await live(call("run_shell", command="echo from-school"), "Done.")
    said = await talk(client, tmp_path / "home", "run it", "y", "/clear", "/quit")
    assert "it wants to run run_shell" in said and "Done." in said and "cleared" in said
    assert (settings.workspace).exists()
    async with httpx.AsyncClient(base_url=client.url) as http:
        assert (await http.get("/sessions")).json() == []


async def test_jarvis_says_plainly_when_the_token_is_wrong(live, settings, tmp_path):
    settings.token = "school-token"
    _, client = await live()
    said = await talk(client, tmp_path / "home", "/quit", token="wrong")
    assert "refused the token" in said


def test_the_greeting_names_the_model_and_whats_due():
    lines = greeting({"providers": ["nvidia"], "chat_models": {"nvidia": "meta/llama-4"}, "memories": 12, "control": "ask",
                      "due": ["Chem lab (due 2026-11-20)"]})
    assert lines[0].startswith("jarvis online") and "nvidia · meta/llama-4" in lines[0] and "12 memories" in lines[0]
    assert lines[1] == "due soon: Chem lab (due 2026-11-20)"


async def test_a_server_without_the_deck_still_chats(live, settings):
    settings.ui = False
    _, client = await live("hello")
    async with httpx.AsyncClient(base_url=client.url) as http:
        assert (await http.get("/ui/")).status_code == 404
        assert (await http.get("/health")).status_code == 200
