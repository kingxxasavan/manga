import asyncio

import pytest
import uvicorn

from greg.config import Settings
from greg.memory.store import Memory


def _lazy():
    from greg.cli.client import GregClient
    from greg.core.app import GregApp
    from greg.server.app import create_app
    from tests.fakes import FakeRouter

    return GregClient, GregApp, create_app, FakeRouter


@pytest.fixture
def settings(tmp_path):
    return Settings(home=tmp_path / "home", workspace=tmp_path / "workspace")


@pytest.fixture
def memory(settings):
    m = Memory(settings.db_path)
    yield m
    m.close()


def make_app(settings, *script, **kw):
    settings.home.mkdir(parents=True, exist_ok=True)
    settings.manifest = settings.home / "none.yaml"  # no outside tool servers in these tests
    settings.learn = False
    _, GregApp, create_app, FakeRouter = _lazy()
    greg = GregApp(settings, router=FakeRouter(*script, **kw))
    return greg, create_app(greg)


@pytest.fixture
async def live(settings):
    """A real server on a real port, so streaming and the ask-first flow are tested for real."""
    started = []

    async def start(*script, **kw):
        greg, app = make_app(settings, *script, **kw)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
        task = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        started.append((server, task))
        return greg, _lazy()[0](f"http://127.0.0.1:{port}", settings.token)

    yield start
    for server, task in started:
        server.should_exit = True
        await task
