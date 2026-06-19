"""Tests de carga y validación de configuración."""

from __future__ import annotations

import pytest

from capuccino_vainilla.config import load_config
from capuccino_vainilla.exceptions import ConfigError


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    """Aísla los tests de cualquier .env presente en el árbol del repo."""
    monkeypatch.setattr("capuccino_vainilla.config.load_dotenv", lambda *a, **k: False)


REQUIRED = {
    "ODOO_URL": "https://odoo.test",
    "ODOO_DB": "capuccino",
    "ODOO_USERNAME": "user",
    "ODOO_PASSWORD": "secret",
    "WOO_URL": "https://woo.test",
    "WOO_CONSUMER_KEY": "ck",
    "WOO_CONSUMER_SECRET": "cs",
}


def _set_env(monkeypatch, overrides=None, missing=None):
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    for key, value in (overrides or {}).items():
        monkeypatch.setenv(key, value)
    for key in (missing or []):
        monkeypatch.delenv(key, raising=False)


def test_load_config_ok(monkeypatch):
    _set_env(monkeypatch)
    config = load_config()
    assert config.odoo.db == "capuccino"
    assert config.woo.url == "https://woo.test"  # sin barra final
    assert config.runtime.batch_size == 50  # default


def test_missing_required_raises(monkeypatch):
    _set_env(monkeypatch, missing=["ODOO_PASSWORD"])
    with pytest.raises(ConfigError, match="ODOO_PASSWORD"):
        load_config()


def test_invalid_url_raises(monkeypatch):
    _set_env(monkeypatch, overrides={"WOO_URL": "woo.test"})
    with pytest.raises(ConfigError, match="WOO_URL"):
        load_config()


def test_int_and_bool_parsing(monkeypatch):
    _set_env(monkeypatch, overrides={"BATCH_SIZE": "10", "WOO_VERIFY_SSL": "false"})
    config = load_config()
    assert config.runtime.batch_size == 10
    assert config.woo.verify_ssl is False


def test_invalid_int_raises(monkeypatch):
    _set_env(monkeypatch, overrides={"BATCH_SIZE": "abc"})
    with pytest.raises(ConfigError, match="BATCH_SIZE"):
        load_config()


def test_watcher_config_defaults(monkeypatch):
    from capuccino_vainilla.config import load_config
    for k in ("WATCH_INTERVAL", "WATCH_INITIAL_FULL", "WATCH_STATE_FILE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in {
        "ODOO_URL": "http://o", "ODOO_DB": "d", "ODOO_USERNAME": "u",
        "ODOO_PASSWORD": "p", "WOO_URL": "http://w",
        "WOO_CONSUMER_KEY": "ck", "WOO_CONSUMER_SECRET": "cs",
    }.items():
        monkeypatch.setenv(k, v)

    cfg = load_config()
    assert cfg.watcher.interval == 30
    assert cfg.watcher.initial_full is True
    assert cfg.watcher.state_file == ".watch_snapshot.json"


def test_watcher_config_overrides(monkeypatch):
    from capuccino_vainilla.config import load_config
    for k, v in {
        "ODOO_URL": "http://o", "ODOO_DB": "d", "ODOO_USERNAME": "u",
        "ODOO_PASSWORD": "p", "WOO_URL": "http://w",
        "WOO_CONSUMER_KEY": "ck", "WOO_CONSUMER_SECRET": "cs",
        "WATCH_INTERVAL": "10", "WATCH_INITIAL_FULL": "false",
        "WATCH_STATE_FILE": "/tmp/snap.json",
    }.items():
        monkeypatch.setenv(k, v)

    cfg = load_config()
    assert cfg.watcher.interval == 10
    assert cfg.watcher.initial_full is False
    assert cfg.watcher.state_file == "/tmp/snap.json"


def test_watch_interval_zero_raises(monkeypatch):
    _set_env(monkeypatch, overrides={"WATCH_INTERVAL": "0"})
    with pytest.raises(ConfigError, match="WATCH_INTERVAL"):
        load_config()
