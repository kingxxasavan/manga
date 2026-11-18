from anexis.profile.about import export_profile
from anexis.profile.seed import seed_owner


def test_a_fresh_install_already_knows_what_the_owner_said(memory):
    report = seed_owner(memory)
    assert report["memories"] >= 10 and report["about"] > 0
    texts = " ".join(m.text for m in memory.list(None, 200))
    for said in ("dashes", "Claude Pro", "Canvas", "eDEX", "Windows app"):
        assert said in texts, said
    assert any(m.kind == "lesson" and "dash" in m.text.lower() for m in memory.list("lesson", 50))
    about = export_profile(memory)
    assert "Never any dashes" in about["talk_style"] and about["tools"] and "name" not in about


def test_it_runs_once_and_never_doubles_a_memory(memory):
    seed_owner(memory)
    count = memory.count()
    assert seed_owner(memory)["skipped"] is True
    memory.kv_set("owner_seeded", False)
    assert seed_owner(memory)["memories"] == 0  # same facts, already there
    assert memory.count() == count


def test_answers_the_owner_gave_are_never_replaced(memory):
    from anexis.profile.about import import_profile

    import_profile(memory, {"name": "Sam", "talk_style": "Short and blunt"})
    seed_owner(memory)
    about = export_profile(memory)
    assert about["talk_style"] == "Short and blunt" and about["name"] == "Sam" and about["avoid"]


async def test_the_app_seeds_on_start(settings):
    from anexis.core.app import AnexisApp
    from tests.fakes import FakeRouter

    settings.manifest = settings.home / "none.yaml"
    settings.consolidate_minutes = 0
    app = AnexisApp(settings, router=FakeRouter())
    await app.start()
    try:
        assert app.memory.count() > 10
        assert "talk_style" in export_profile(app.memory)
    finally:
        await app.stop()


async def test_health_reports_about_me_so_the_deck_can_ask(live):
    anexis, client = await live()
    assert (await client.health())["about_me"] == {}
    from anexis.profile.about import import_profile

    import_profile(anexis.memory, {"name": "Sam"})
    assert (await client.health())["about_me"]["name"] == "Sam"
