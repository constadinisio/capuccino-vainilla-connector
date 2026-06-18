"""Tests del cliente WooCommerce usando un `api` inyectado (sin red)."""

from __future__ import annotations

import pytest

from capuccino_vainilla.clients.woo_client import WooClient
from capuccino_vainilla.config import RuntimeConfig, WooConfig
from capuccino_vainilla.exceptions import WooError, WooTransientError

WOO = WooConfig(
    url="http://woo.test", consumer_key="ck", consumer_secret="cs",
    api_version="wc/v3", verify_ssl=False, timeout=10,
)
RUNTIME = RuntimeConfig(
    batch_size=10, max_retries=3, retry_delay=0.0,
    log_level="INFO", log_file="t.log", state_file="s.json",
)


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class FakeApi:
    """Devuelve respuestas predefinidas; cuenta llamadas por verbo."""

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.count = 0

    def _act(self, *args, **kwargs):
        self.count += 1
        if self._raises is not None:
            raise self._raises
        return self._response

    get = _act
    post = _act
    put = _act


def _client(**kwargs):
    return WooClient(WOO, RUNTIME, api=FakeApi(**kwargs))


def test_2xx_returns_json():
    client = WooClient(WOO, RUNTIME, api=FakeApi(response=FakeResponse(200, [{"id": 1}])))
    assert client.get("products", {"sku": "X"}) == [{"id": 1}]


def test_4xx_raises_woo_error_without_retry():
    api = FakeApi(response=FakeResponse(400, text="bad request"))
    client = WooClient(WOO, RUNTIME, api=api)
    with pytest.raises(WooError):
        client.post("products", {})
    assert api.count == 1  # 4xx no se reintenta


def test_5xx_is_transient_and_retried():
    api = FakeApi(response=FakeResponse(503, text="unavailable"))
    client = WooClient(WOO, RUNTIME, api=api)
    with pytest.raises(WooTransientError):
        client.get("products")
    assert api.count == RUNTIME.max_retries  # se reintentó hasta agotar


def test_network_error_is_transient():
    client = _client(raises=ConnectionError("sin red"))
    with pytest.raises(WooTransientError):
        client.put("products/1", {})
