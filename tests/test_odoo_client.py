"""Tests del cliente Odoo usando un proxy de objetos inyectado (sin red)."""

from __future__ import annotations

import xmlrpc.client

import pytest

from capuccino_vainilla.clients.odoo_client import OdooClient
from capuccino_vainilla.config import OdooConfig, RuntimeConfig
from capuccino_vainilla.exceptions import OdooError

ODOO = OdooConfig(url="http://odoo.test", db="db", username="u", password="p")
RUNTIME = RuntimeConfig(
    batch_size=10, max_retries=3, retry_delay=0.0,
    log_level="INFO", log_file="t.log", state_file="s.json",
)


class FakeModels:
    """Proxy de objetos falso: el último elemento decide qué devuelve/lanza."""

    def __init__(self, behaviors: dict):
        self.behaviors = behaviors
        self.calls: list = []

    def execute_kw(self, db, uid, password, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        result = self.behaviors[method]
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return result()
        return result


def _client(behaviors):
    return OdooClient(ODOO, RUNTIME, models=FakeModels(behaviors), uid=1)


def test_search_read_passes_kwargs():
    models = FakeModels({"search_read": [{"id": 1, "name": "x"}]})
    client = OdooClient(ODOO, RUNTIME, models=models, uid=1)
    rows = client.search_read("res.partner", [("id", "=", 1)], ["name"], limit=5, order="id asc")
    assert rows == [{"id": 1, "name": "x"}]
    _, _, _, kwargs = models.calls[0]
    assert kwargs["limit"] == 5 and kwargs["order"] == "id asc"


def test_create_returns_id():
    assert _client({"create": 42}).create("res.partner", {"name": "x"}) == 42


def test_create_without_id_raises():
    with pytest.raises(OdooError):
        _client({"create": False}).create("res.partner", {"name": "x"})


def test_fault_becomes_odoo_error():
    fault = xmlrpc.client.Fault(2, "campo requerido")
    with pytest.raises(OdooError, match="rechazó"):
        _client({"create": fault}).create("res.partner", {})


def test_transient_error_is_retried_then_succeeds():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ConnectionError("temporal")
        return 7

    assert _client({"search_count": flaky}).search_count("res.partner", []) == 7
    assert attempts["n"] == 2


def test_transient_error_exhausted_raises_odoo_error():
    with pytest.raises(OdooError):
        _client({"search_count": ConnectionError("caída")}).search_count("res.partner", [])


def test_company_scope_injected_into_context():
    """Con company_id se fuerza allowed_company_ids en cada llamada (excluye GPTV)."""
    scoped = OdooConfig(url="http://odoo.test", db="db", username="u", password="p", company_id=134)
    models = FakeModels({"search_read": []})
    client = OdooClient(scoped, RUNTIME, models=models, uid=1)
    client.search_read("product.template", [], ["id"])
    _, _, _, kwargs = models.calls[0]
    assert kwargs["context"]["allowed_company_ids"] == [134]


def test_no_company_scope_when_unset():
    """Sin company_id no se agrega contexto (comportamiento histórico intacto)."""
    models = FakeModels({"search_read": []})
    client = OdooClient(ODOO, RUNTIME, models=models, uid=1)
    client.search_read("product.template", [], ["id"])
    _, _, _, kwargs = models.calls[0]
    assert "context" not in kwargs
