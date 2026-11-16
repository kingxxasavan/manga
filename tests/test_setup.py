import re
import stat

import pytest

from anexis.cli.setup import (
    PRESETS,
    Machine,
    build_toml,
    key_warning,
    read_plan,
    recommend,
    run_keys,
    run_wizard,
    update_env_file,
)
from anexis.config import load_settings

GPU_BOX = Machine(vram_gb=24, ram_gb=64, has_ollama=True, node_major=24, has_claude=True, has_systemd=True)
LAPTOP = Machine(vram_gb=8, ram_gb=16, has_ollama=False, node_major=22, has_claude=False, has_systemd=True)
WEAK = Machine(vram_gb=0, ram_gb=8, has_ollama=False, node_major=0, has_claude=False, has_systemd=False)


class Script:
    """Answers the wizard's questions from a dict keyed by a word in the question.
    Anything not listed gets Enter, which means: take the default or skip."""

    def __init__(self, **answers):
        self.answers = answers
        self.asked = []

    def __call__(self, question, default="", secret=False):
        self.asked.append((question, secret))
        for word, answer in self.answers.items():
            if word.lower().replace("_", " ") in question.lower():
                return answer
        return ""


def wizard(tmp_path, machine=LAPTOP, env=None, ask=None, **kw):
    """The whole setup the way the installer runs it: choices first, then
    (after the downloads would have happened) the keys."""
    home = tmp_path / "anexishome"
    said = []
    ask = ask or Script()
    result = run_wizard(home, env or {}, machine, ask, said.append, **kw)
    if not result.cancelled:
        run_keys(home, env or {}, ask, said.append, yes=kw.get("yes", False))
    return home, result, "\n".join(said)


# ---- presets -----------------------------------------------------------------


@pytest.mark.parametrize("name", list(PRESETS))
def test_every_preset_writes_a_config_anexis_can_load(tmp_path, name):
    (tmp_path / "anexis.toml").write_text(build_toml(PRESETS[name], "Anexis"))
    settings = load_settings(env={"ANEXIS_HOME": str(tmp_path), "NVIDIA_API_KEY": "nvapi-x"}, config_path=tmp_path / "anexis.toml")
    assert settings.problems() == []
    assert all(p.models.get("chat") for p in settings.providers)


def test_cloud_preset_uses_nvidia_only_and_pulls_no_local_models(tmp_path):
    (tmp_path / "anexis.toml").write_text(build_toml(PRESETS["cloud"], "Anexis"))
    settings = load_settings(env={"ANEXIS_HOME": str(tmp_path)}, config_path=tmp_path / "anexis.toml")
    assert [p.name for p in settings.providers] == ["nvidia"]
    assert PRESETS["cloud"].pull == []


def test_max_preset_uses_bigger_models_and_wider_recall_than_light(tmp_path):
    def load(name):
        (tmp_path / "anexis.toml").write_text(build_toml(PRESETS[name], "Anexis"))
        return load_settings(env={"ANEXIS_HOME": str(tmp_path)}, config_path=tmp_path / "anexis.toml")

    big, small = load("max"), load("light")
    assert big.recall_k > small.recall_k and big.max_tools > small.max_tools
    assert big.providers[0].models["chat"] != small.providers[0].models["chat"]


def test_the_assistant_name_lands_in_the_config_even_with_odd_characters(tmp_path):
    (tmp_path / "anexis.toml").write_text(build_toml(PRESETS["balanced"], 'Gr"eg\\ the 2nd'))
    assert load_settings(env={"ANEXIS_HOME": str(tmp_path)}, config_path=tmp_path / "anexis.toml").name == 'Gr"eg\\ the 2nd'


@pytest.mark.parametrize("machine, env, expected", [
    (GPU_BOX, {}, "max"),
    (LAPTOP, {}, "balanced"),
    (WEAK, {"NVIDIA_API_KEY": "nvapi-x"}, "cloud"),
    (WEAK, {}, "light"),
])
def test_the_recommended_preset_fits_the_machine(machine, env, expected):
    assert recommend(machine, env) == expected


# ---- the .env file -----------------------------------------------------------


def test_keys_are_written_to_a_private_file(tmp_path):
    path = tmp_path / ".env"
    update_env_file(path, {"NVIDIA_API_KEY": "nvapi-abc"})
    assert path.read_text() == "NVIDIA_API_KEY=nvapi-abc\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_updating_one_key_leaves_comments_and_other_keys_alone(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# my keys\nNVIDIA_API_KEY=old\nGITHUB_TOKEN=keepme\n\n# notes\n")
    update_env_file(path, {"NVIDIA_API_KEY": "new", "EXA_API_KEY": "added"})
    assert path.read_text() == "# my keys\nNVIDIA_API_KEY=new\nGITHUB_TOKEN=keepme\n\n# notes\nEXA_API_KEY=added\n"


def test_an_empty_value_removes_the_key(tmp_path):
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=old\nGITHUB_TOKEN=keepme\n")
    update_env_file(path, {"NVIDIA_API_KEY": ""})
    assert path.read_text() == "GITHUB_TOKEN=keepme\n"


def test_a_value_with_spaces_or_symbols_survives_a_round_trip(tmp_path):
    from anexis.config import read_dotenv

    path = tmp_path / ".env"
    update_env_file(path, {"ODD": "a b#c$d'e"})
    assert read_dotenv(path)["ODD"] == "a b#c$d'e"


def test_a_key_that_looks_wrong_gets_a_warning_not_a_refusal():
    assert key_warning("NVIDIA_API_KEY", "nvapi-abcdefgh12345678") == ""
    assert "nvapi-" in key_warning("NVIDIA_API_KEY", "sk-ant-oops")
    assert "space" in key_warning("ANTHROPIC_API_KEY", "sk-ant-abc def")
    assert key_warning("GITHUB_TOKEN", "github_pat_11ABCDEFG0123456789") == ""


# ---- the wizard --------------------------------------------------------------


def test_pressing_enter_on_everything_gives_the_recommended_setup(tmp_path):
    home, result, _ = wizard(tmp_path, machine=LAPTOP)
    assert result.preset == "balanced" and not result.cancelled
    settings = load_settings(env={"ANEXIS_HOME": str(home)}, config_path=home / "anexis.toml")
    assert settings.providers[0].name == "ollama" and settings.name == "Anexis"
    plan = read_plan(home / "setup-plan")
    assert plan["PRESET"] == "balanced" and plan["INSTALL_OLLAMA"] == "1"
    assert plan["PULL_MODELS"].split() == PRESETS["balanced"].pull
    assert plan["INSTALL_VOICE"] == "0" and plan["ENABLE_SERVICE"] == "0"


def test_a_preset_can_be_picked_by_number_or_name(tmp_path):
    names = list(PRESETS)
    _, by_number, _ = wizard(tmp_path / "a", ask=Script(preset=str(names.index("light") + 1)))
    _, by_name, _ = wizard(tmp_path / "b", ask=Script(preset="cloud"))
    assert (by_number.preset, by_name.preset) == ("light", "cloud")


def test_a_pasted_key_is_saved_and_asked_for_with_hidden_input(tmp_path):
    ask = Script(nvidia="nvapi-secretsecret1234")
    home, _, shown = wizard(tmp_path, ask=ask)
    assert "NVIDIA_API_KEY=nvapi-secretsecret1234" in (home / ".env").read_text()
    assert all(secret for question, secret in ask.asked if "key" in question.lower() or "token" in question.lower())
    assert "nvapi-secretsecret1234" not in shown  # the key itself is never printed


def test_a_key_already_in_the_environment_is_filled_in_without_typing(tmp_path):
    home, _, shown = wizard(tmp_path, env={"ANTHROPIC_API_KEY": "sk-ant-fromenv99"})
    assert "ANTHROPIC_API_KEY=sk-ant-fromenv99" in (home / ".env").read_text()
    assert "found" in shown.lower() and "sk-ant-fromenv99" not in shown and "nv99" in shown


def test_skipping_a_key_keeps_the_one_already_saved(tmp_path):
    home = tmp_path / "anexishome"
    home.mkdir()
    (home / ".env").write_text("NVIDIA_API_KEY=nvapi-existing0001\n")
    wizard(tmp_path)
    assert "NVIDIA_API_KEY=nvapi-existing0001" in (home / ".env").read_text()


def test_a_dash_removes_a_saved_key(tmp_path):
    home = tmp_path / "anexishome"
    home.mkdir()
    (home / ".env").write_text("NVIDIA_API_KEY=nvapi-existing0001\n")
    wizard(tmp_path, ask=Script(nvidia="-"))
    assert "NVIDIA_API_KEY" not in (home / ".env").read_text()


def test_every_option_that_needs_a_key_is_asked_about_on_its_own(tmp_path):
    ask = Script(notion="ntn_abc123456789")
    home, _, shown = wizard(tmp_path, ask=ask)
    asked = [q for q, secret in ask.asked if secret]
    for option in ("Nvidia", "Anthropic", "GitHub", "Notion", "Brave", "Tavily", "Firecrawl", "Exa"):
        assert sum(option in q for q in asked) == 1, option
    assert "NOTION_TOKEN=ntn_abc123456789" in (home / ".env").read_text()
    assert "1 of 8" in shown and "8 of 8" in shown


def test_the_choices_step_never_asks_for_a_key(tmp_path):
    ask = Script()
    home = tmp_path / "anexishome"
    run_wizard(home, {"NVIDIA_API_KEY": "nvapi-fromenv00001"}, LAPTOP, ask, lambda text: None)
    assert not any(secret for _, secret in ask.asked)
    assert (home / "anexis.toml").exists() and (home / "setup-plan").exists()
    assert not (home / ".env").exists()  # keys come later, after the downloads


def test_keys_can_be_asked_later_on_their_own(tmp_path):
    home = tmp_path / "anexishome"
    run_wizard(home, {}, LAPTOP, Script(), lambda text: None)
    said = []
    changed = run_keys(home, {}, Script(nvidia="nvapi-secretsecret1234", exa="exa-key-0123456789"), said.append)
    env = (home / ".env").read_text()
    assert "NVIDIA_API_KEY=nvapi-secretsecret1234" in env and "EXA_API_KEY=exa-key-0123456789" in env
    assert sorted(changed) == ["EXA_API_KEY", "NVIDIA_API_KEY"]


def test_each_key_question_says_what_it_turns_on_and_where_to_get_it(tmp_path):
    _, _, shown = wizard(tmp_path)
    assert "build.nvidia.com" in shown and "console.anthropic.com" in shown and "github.com/settings/tokens" in shown


def test_the_key_step_ends_with_what_is_on_and_what_is_off(tmp_path):
    _, _, shown = wizard(tmp_path, ask=Script(nvidia="nvapi-secretsecret1234"))
    tail = shown[shown.rindex("Keys saved"):]
    assert "on" in tail and "Nvidia" in tail and "off" in tail and "Notion" in tail


def test_running_the_key_step_again_changes_nothing_when_everything_is_skipped(tmp_path):
    home, _, _ = wizard(tmp_path, ask=Script(nvidia="nvapi-secretsecret1234"))
    before = (home / ".env").read_text()
    assert run_keys(home, {}, Script(), lambda text: None) == {}
    assert (home / ".env").read_text() == before


def test_choosing_remote_access_makes_a_token_and_opens_the_server(tmp_path):
    home, _, shown = wizard(tmp_path, ask=Script(other_machines="y"))
    env = (home / ".env").read_text()
    token = re.search(r"ANEXIS_TOKEN=(\S+)", env).group(1)
    assert len(token) >= 32 and "ANEXIS_HOST=0.0.0.0" in env
    assert load_settings(env={"ANEXIS_HOME": str(home)}, config_path=home / "anexis.toml").problems() == []
    assert "ANEXIS_TOKEN" in shown  # told where to find it for the other machine


def test_an_existing_token_is_kept_so_other_machines_stay_connected(tmp_path):
    home = tmp_path / "anexishome"
    home.mkdir()
    (home / ".env").write_text("ANEXIS_TOKEN=already-have-a-good-long-token-value-here\nANEXIS_HOST=0.0.0.0\n")
    wizard(tmp_path, ask=Script(other_machines="y"))
    assert "ANEXIS_TOKEN=already-have-a-good-long-token-value-here" in (home / ".env").read_text()


def test_voice_service_and_name_choices_reach_the_config_and_the_plan(tmp_path):
    home, _, _ = wizard(tmp_path, ask=Script(voice="y", background="y", call_it="Max"))
    plan = read_plan(home / "setup-plan")
    assert plan["INSTALL_VOICE"] == "1" and plan["ENABLE_SERVICE"] == "1"
    assert load_settings(env={"ANEXIS_HOME": str(home)}, config_path=home / "anexis.toml").name == "Max"


def test_install_steps_can_each_be_skipped(tmp_path):
    home, _, _ = wizard(tmp_path, ask=Script(install_ollama="n", claude_code="n", tool_servers="n", node="n"))
    plan = read_plan(home / "setup-plan")
    assert (plan["INSTALL_OLLAMA"], plan["PULL_MODELS"], plan["INSTALL_CLAUDE"], plan["SYNC_TOOLS"], plan["INSTALL_NODE"]) == ("0", "", "0", "0", "0")


def test_what_is_already_installed_is_not_offered_again(tmp_path):
    ask = Script()
    home, _, _ = wizard(tmp_path, machine=GPU_BOX, ask=ask)
    plan = read_plan(home / "setup-plan")
    assert plan["INSTALL_OLLAMA"] == "0" and plan["INSTALL_NODE"] == "0" and plan["INSTALL_CLAUDE"] == "0"
    assert plan["PULL_MODELS"]  # models are still pulled into the Ollama that is there
    assert not any("install ollama" in q.lower() for q, _ in ask.asked)


def test_the_background_service_is_not_offered_without_systemd(tmp_path):
    ask = Script()
    wizard(tmp_path, machine=WEAK, ask=ask)
    assert not any("background" in q.lower() for q, _ in ask.asked)


def test_an_old_config_is_backed_up_before_it_is_replaced(tmp_path):
    home = tmp_path / "anexishome"
    home.mkdir()
    (home / "anexis.toml").write_text('name = "Old"\n')
    wizard(tmp_path)
    backups = list(home.glob("anexis.toml.bak*"))
    assert len(backups) == 1 and backups[0].read_text() == 'name = "Old"\n'


def test_saying_no_at_the_end_changes_nothing(tmp_path):
    home, result, _ = wizard(tmp_path, ask=Script(nvidia="nvapi-secretsecret1234", looks_right="n"))
    assert result.cancelled
    assert not (home / "anexis.toml").exists() and not (home / ".env").exists() and not (home / "setup-plan").exists()


def test_yes_mode_asks_nothing_and_takes_keys_from_the_environment(tmp_path):
    def nobody(question, default="", secret=False):
        raise AssertionError(f"asked in yes mode: {question}")

    home, result, _ = wizard(tmp_path, machine=WEAK, env={"NVIDIA_API_KEY": "nvapi-fromenv00001"}, ask=nobody, yes=True)
    assert result.preset == "cloud"
    assert "NVIDIA_API_KEY=nvapi-fromenv00001" in (home / ".env").read_text()


def test_a_preset_given_up_front_is_used_without_asking(tmp_path):
    ask = Script()
    _, result, _ = wizard(tmp_path, ask=ask, preset="max")
    assert result.preset == "max" and not any("preset" in q.lower() for q, _ in ask.asked)


def test_an_unknown_preset_is_refused(tmp_path):
    with pytest.raises(ValueError, match="balanced"):
        wizard(tmp_path, preset="turbo")


def test_the_plan_only_ever_holds_plain_safe_values(tmp_path):
    home, _, _ = wizard(tmp_path, ask=Script(call_it='x"; rm -rf ~; echo "', voice="y"))
    for line in (home / "setup-plan").read_text().splitlines():
        assert re.fullmatch(r"[A-Z_]+=[A-Za-z0-9_.:/ -]*", line), line


def test_cloud_without_a_key_warns_that_anexis_cannot_talk_yet(tmp_path):
    _, _, shown = wizard(tmp_path, ask=Script(preset="cloud"))
    assert "nvidia" in shown.lower() and "cannot" in shown.lower()
