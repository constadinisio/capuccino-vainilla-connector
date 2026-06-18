import os

import pytest

from capuccino_vainilla.exceptions import ConfigError
from capuccino_vainilla.seeder.config import SeederConfig, load_seeder_config


@pytest.fixture(autouse=True)
def _clear_odoo_env_vars(monkeypatch):
    """Limpia las variables de entorno Odoo antes de cada test."""
    for key in list(os.environ.keys()):
        if key.startswith("ODOO_"):
            monkeypatch.delenv(key, raising=False)


def _write_env(tmp_path, body: str) -> str:
    path = tmp_path / ".env.seed"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_load_seeder_config_parses_source_and_target(tmp_path):
    env = _write_env(tmp_path, (
        "ODOO_SRC_URL=https://real.odoo.com\n"
        "ODOO_SRC_DB=real_db\n"
        "ODOO_SRC_USERNAME=bot@x.com\n"
        "ODOO_SRC_PASSWORD=key123\n"
        "ODOO_DST_URL=http://localhost:8069\n"
        "ODOO_DST_DB=test_db\n"
        "ODOO_DST_USERNAME=admin\n"
        "ODOO_DST_PASSWORD=admin\n"
    ))
    cfg = load_seeder_config(env)
    assert isinstance(cfg, SeederConfig)
    assert cfg.source.url == "https://real.odoo.com"
    assert cfg.source.db == "real_db"
    assert cfg.target.url == "http://localhost:8069"
    assert cfg.target.username == "admin"


def test_load_seeder_config_missing_var_raises(tmp_path):
    env = _write_env(tmp_path, "ODOO_SRC_URL=https://real.odoo.com\n")
    with pytest.raises(ConfigError):
        load_seeder_config(env)
