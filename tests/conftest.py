import asyncio

import pytest
import uvicorn

from anexis.config import Settings
from anexis.memory.store import Memory


def _lazy():
    from anexis.cli.client import AnexisClient
    from anexis.core.app import AnexisApp
    from anexis.server.app import create_app
    from tests.fakes import FakeRouter

    return AnexisClient, AnexisApp, create_app, FakeRouter


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
    settings.seed_owner = False  # tests count memories, so they start empty
    _, AnexisApp, create_app, FakeRouter = _lazy()
    anexis = AnexisApp(settings, router=FakeRouter(*script, **kw))
    return anexis, create_app(anexis)


@pytest.fixture
async def live(settings):
    """A real server on a real port, so streaming and the ask-first flow are tested for real."""
    started = []

    async def start(*script, **kw):
        anexis, app = make_app(settings, *script, **kw)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
        task = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        started.append((server, task))
        return anexis, _lazy()[0](f"http://127.0.0.1:{port}", settings.token)

    yield start
    for server, task in started:
        server.should_exit = True
        await task
