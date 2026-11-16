from pathlib import Path

import pytest

from greg.core.app import GregApp
from greg.core.train import OfflineRouter, load_pack, practice_settings, run_training
from tests.fakes import FakeRouter

REPO = Path(__file__).parent.parent

PACK = {
    "teach": [
        {"say": "dont use any dashes when you talk to me ok", "learns": ["dashes"],
         "offline": [{"op": "add", "kind": "lesson", "text": "Never use dashes when writing to them"}]},
        {"say": "like i said before no dashes ever please", "reinforces": ["dashes"],
         "offline": [{"op": "add", "kind": "lesson", "text": "never use dashes when writing to them."}]},
    ],
    "practice": [
        {"say": "my history essay is due next friday for real", "learns": ["history essay"],
         "offline": [{"op": "add", "kind": "task", "text": "History essay is due next Friday"}]},
        {"say": "actually the history essay got moved its due monday now", "learns": ["history essay monday"],
         "gone": ["next friday"],
         "offline": [{"op": "replace", "match": "History essay", "text": "History essay is due Monday"}]},
    ],
    "probes": [
        {"ask": "write me a paragraph about dogs", "prompt": "dashes"},
        {"ask": "when is the histroy essay due", "recall": "monday", "practice": True},
        {"ask": "calculater 15 percent of 240", "tool": "calculate"},
    ],
}


def greg_for(settings, router):
    settings.manifest = settings.home / "none.yaml"
    settings.consolidate_minutes = 0
    return GregApp(settings, router=router)


async def test_a_practice_run_teaches_checks_and_scores_every_part(settings):
    greg = greg_for(settings, OfflineRouter(PACK))
    report = await run_training(greg, PACK)
    assert report.failures() == []
    assert report.counts() == {"learned": (3, 3), "reinforced": (1, 1), "replaced": (1, 1), "recall": (1, 1), "prompt": (1, 1), "tools": (1, 1)}
    assert report.score() == (8, 8)


async def test_repeating_something_makes_greg_more_sure_without_a_second_copy(settings):
    greg = greg_for(settings, OfflineRouter(PACK))
    await run_training(greg, PACK)
    lessons = [m for m in greg.memory.list("lesson") if "dashes" in m.text.lower()]
    assert len(lessons) == 1 and lessons[0].confidence > 0.85


async def test_keeping_the_results_skips_the_made_up_practice_facts(settings):
    greg = greg_for(settings, OfflineRouter(PACK))
    report = await run_training(greg, PACK, keep=True)
    assert [m.text for m in greg.memory.list()] == ["Never use dashes when writing to them"]
    assert "recall" not in report.counts() and report.counts()["learned"] == (1, 1)


async def test_a_model_that_learns_nothing_is_reported_as_misses_not_a_crash(settings):
    silent = FakeRouter(roles={"chat": ["ok"] * 10, "small": [{"ops": []}] * 10})
    report = await run_training(greg_for(settings, silent), PACK)
    done, total = report.counts()["learned"]
    assert done == 0 and total == 3
    assert any("dashes" in line for line in report.failures())


async def test_alternatives_let_a_real_model_word_things_its_own_way(settings):
    pack = {"teach": [{"say": "i always want the most elite version of what we make",
                       "learns": ["elite|best|top quality"],
                       "offline": [{"op": "add", "kind": "preference", "text": "Always wants the best version"}]}]}
    report = await run_training(greg_for(settings, OfflineRouter(pack)), pack)
    assert report.counts()["learned"] == (1, 1)


def test_a_practice_run_never_touches_the_real_memory(settings, tmp_path):
    practice = practice_settings(settings, tmp_path / "scratch")
    assert practice.home != settings.home and practice.db_path != settings.db_path
    assert practice.providers == settings.providers and practice.learn is True


def test_the_shipped_pack_is_well_formed():
    pack = load_pack(REPO / "training" / "like_me.yaml")
    assert len(pack["teach"]) >= 6 and len(pack["probes"]) >= 10
    for turn in pack["teach"] + pack["practice"]:
        assert turn["say"] and turn["offline"], turn
        assert turn.get("learns") or turn.get("reinforces"), turn
        assert "\u2014" not in turn["say"] and "\u2013" not in turn["say"]  # the owner never types dashes
    for probe in pack["probes"]:
        assert probe["ask"] and (probe.get("recall") or probe.get("tool") or probe.get("prompt")), probe


def test_a_pack_with_a_mistake_is_rejected_with_a_clear_reason(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("teach:\n  - learns: [x]\n")
    with pytest.raises(ValueError, match="say"):
        load_pack(bad)


async def test_the_shipped_pack_passes_offline(settings):
    pack = load_pack(REPO / "training" / "like_me.yaml")
    report = await run_training(greg_for(settings, OfflineRouter(pack)), pack)
    assert report.failures() == []
