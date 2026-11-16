import pytest

from greg.config import Settings
from greg.memory.store import Memory


@pytest.fixture
def settings(tmp_path):
    return Settings(home=tmp_path / "home", workspace=tmp_path / "workspace")


@pytest.fixture
def memory(settings):
    m = Memory(settings.db_path)
    yield m
    m.close()
