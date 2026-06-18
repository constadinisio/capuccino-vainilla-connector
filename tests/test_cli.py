from capuccino_vainilla.cli import main
from capuccino_vainilla.config import ConfigError


def test_env_file_flag_se_pasa_a_load_config(monkeypatch):
    captured = {}

    def fake_load_config(env_file=None):
        captured["env_file"] = env_file
        raise ConfigError("stop")  # corta el flujo apenas capturamos

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", fake_load_config)
    rc = main(["--env-file", ".env.test", "sync-catalog"])

    assert captured["env_file"] == ".env.test"
    assert rc == 2  # main mapea ConfigError -> 2


def test_sin_env_file_se_usa_none(monkeypatch):
    captured = {}

    def fake_load_config(env_file=None):
        captured["env_file"] = env_file
        raise ConfigError("stop")

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", fake_load_config)
    main(["sync-catalog"])

    assert captured["env_file"] is None
