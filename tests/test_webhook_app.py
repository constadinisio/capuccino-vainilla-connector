"""Tests del endpoint de webhooks (FastAPI)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from capuccino_vainilla.exceptions import ConfigError, MappingError
from capuccino_vainilla.webhook.app import SIGNATURE_HEADER, create_app
from capuccino_vainilla.webhook.security import compute_signature

from .conftest import make_config

SECRET = "test-secret"
PAYLOAD = {"number": "1", "billing": {"email": "a@e.com"},
           "line_items": [{"sku": "A", "quantity": 1, "total": "10"}]}


def _signed_request(client, path, payload, secret=SECRET):
    body = json.dumps(payload).encode("utf-8")
    headers = {SIGNATURE_HEADER: compute_signature(body, secret),
               "Content-Type": "application/json"}
    return client.post(path, content=body, headers=headers)


def test_requires_webhook_secret():
    with pytest.raises(ConfigError):
        create_app(make_config(webhook_secret=""))


def test_health_endpoint():
    app = create_app(make_config(), order_handler=lambda payload: 1)
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_valid_signed_webhook_creates_order():
    config = make_config()
    app = create_app(config, order_handler=lambda payload: 555)
    client = TestClient(app)

    resp = _signed_request(client, config.webhook.path, PAYLOAD)
    assert resp.status_code == 201
    assert resp.json() == {"status": "created", "sale_order_id": 555}


def test_invalid_signature_is_rejected():
    config = make_config()
    app = create_app(config, order_handler=lambda payload: 555)
    client = TestClient(app)

    body = json.dumps(PAYLOAD).encode("utf-8")
    resp = client.post(config.webhook.path, content=body,
                       headers={SIGNATURE_HEADER: "firma-falsa"})
    assert resp.status_code == 401


def test_mapping_error_returns_422():
    def handler(payload):
        raise MappingError("sin líneas mapeables")

    config = make_config()
    app = create_app(config, order_handler=handler)
    client = TestClient(app)

    resp = _signed_request(client, config.webhook.path, PAYLOAD)
    assert resp.status_code == 422
    assert resp.json()["status"] == "skipped"
