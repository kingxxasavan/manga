"""A real Anexis server with a scripted model, for the deck's browser test.

Everything is the real thing (settings from the home folder, tools, memory,
the server, the deck files) except the model, which answers by simple rules
so the test knows what to expect.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn

from anexis.config import load_settings
from anexis.core.app import AnexisApp
from anexis.server.app import create_app
from tests.fakes import FakeRouter, call, say


class Scripted(FakeRouter):
    providers = (type("Provider", (), {"name": "scripted"})(),)

    async def chat(self, role, messages, tools=None, on_text=None):
        last = messages[-1]
        text = last.get("content") or ""
        if last["role"] == "tool":
            reply = say(f"Done. It said:\n\n```\n{text[:200]}\n```")
        elif "wait" in text:
            reply = call("run_shell", command="sleep 60")
        elif "run" in text:
            reply = call("run_shell", command="echo deck-says-hi")
        else:
            reply = say("Hey. I am **here**.\n\n- one\n- two\n\nTry `/help`.")
        if reply.content and on_text:
            for i in range(0, len(reply.content), 10):
                on_text(reply.content[i:i + 10])
                await asyncio.sleep(0.005)
        return reply


def main() -> None:
    settings = load_settings()
    settings.manifest = settings.home / "none.yaml"  # no outside tool servers here
    settings.learn = False
    settings.seed_owner = False  # the test counts memories
    settings.autonomy_minutes = 0
    app = create_app(AnexisApp(settings, router=Scripted()))
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port, log_level="warning", timeout_graceful_shutdown=2))
    app.state.server = server
    server.run()
    sys.exit(getattr(app.state, "exit_code", 0))


if __name__ == "__main__":
    main()
