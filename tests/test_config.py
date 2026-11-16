from greg.config import load_settings


def test_defaults_put_ollama_first_and_skip_nvidia_without_a_key(tmp_path):
    s = load_settings(env={"GREG_HOME": str(tmp_path)}, config_path=None)
    assert [p.name for p in s.active_providers()] == ["ollama"]


def test_nvidia_becomes_active_once_its_key_is_set(tmp_path):
    s = load_settings(env={"GREG_HOME": str(tmp_path), "NVIDIA_API_KEY": "nvapi-x"}, config_path=None)
    assert [p.name for p in s.active_providers()] == ["ollama", "nvidia"]
    assert s.active_providers()[1].api_key == "nvapi-x"


def test_toml_file_overrides_defaults(tmp_path):
    cfg = tmp_path / "greg.toml"
    cfg.write_text(
        'name = "Max"\n[server]\nport = 9000\n[memory]\nrecall_k = 3\n'
        '[[providers]]\nname = "nvidia"\nbase_url = "https://x/v1"\napi_key_env = "K"\n'
        '[providers.models]\nchat = "m1"\n'
    )
    s = load_settings(env={"GREG_HOME": str(tmp_path), "K": "secret"}, config_path=cfg)
    assert (s.name, s.port, s.recall_k) == ("Max", 9000, 3)
    assert [p.name for p in s.active_providers()] == ["nvidia"]
    assert s.active_providers()[0].models["chat"] == "m1"


def test_dotenv_is_read_but_never_beats_the_real_environment(tmp_path):
    (tmp_path / ".env").write_text('# comment\nNVIDIA_API_KEY="from-file"\nGREG_TOKEN=abc\n')
    s = load_settings(env={"GREG_HOME": str(tmp_path), "GREG_TOKEN": "real"}, config_path=None)
    assert s.token == "real"
    assert s.active_providers()[1].api_key == "from-file"


def test_refuses_to_listen_on_the_network_without_a_token(tmp_path):
    cfg = tmp_path / "greg.toml"
    cfg.write_text('[server]\nhost = "0.0.0.0"\n')
    s = load_settings(env={"GREG_HOME": str(tmp_path)}, config_path=cfg)
    assert "token" in s.problems()[0].lower()
