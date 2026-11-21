"""Game mode: a full screen game in front means JARVIS only answers to its
name and keeps its check ins to itself until the game is closed."""

from datetime import datetime

from anexis.desktop import gaming

SCREEN = (0, 0, 2560, 1440)


def test_a_full_screen_program_counts_and_a_window_does_not():
    assert gaming.full_screen_app("FortniteClient-Win64-Shipping.exe", SCREEN, SCREEN) == "FortniteClient-Win64-Shipping.exe"
    assert gaming.full_screen_app("FortniteClient-Win64-Shipping.exe", (-8, -8, 2568, 1448), SCREEN)  # a bit bigger counts
    assert gaming.full_screen_app("chrome.exe", (100, 100, 1500, 900), SCREEN) == ""
    # an exclusive full screen game counts even when its window says otherwise
    assert gaming.full_screen_app("game.exe", (0, 0, 800, 600), SCREEN, d3d=True) == "game.exe"


def test_the_desktop_and_anexis_itself_are_never_a_game():
    for name in ("explorer.exe", "Explorer.EXE", "Anexis.exe", "electron.exe", "LockApp.exe"):
        assert gaming.full_screen_app(name, SCREEN, SCREEN, d3d=True) == ""
    assert gaming.full_screen_app("", SCREEN, SCREEN) == ""


def test_off_windows_there_is_never_a_game():
    if not gaming.IS_WINDOWS:
        assert gaming.game_in_front() == ""


async def test_check_ins_wait_while_a_game_is_in_front(settings):
    from anexis.core.initiative import Initiative
    from tests.conftest import make_app

    settings.autonomy = "ask"
    anexis, _ = make_app(settings, '{"action": "ask", "text": "How was your day?"}')
    anexis.game_check = lambda: "FortniteClient-Win64-Shipping.exe"
    await anexis.check_game()
    assert anexis.gaming == "FortniteClient-Win64-Shipping.exe"
    result = await Initiative(anexis).check_in(datetime(2026, 11, 18, 15, 0))
    assert result == {"action": "skipped", "why": "a game is in front"}
    anexis.game_check = lambda: ""
    await anexis.check_game()
    result = await Initiative(anexis).check_in(datetime(2026, 11, 18, 15, 0))
    assert result["action"] == "ask"
