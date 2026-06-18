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
