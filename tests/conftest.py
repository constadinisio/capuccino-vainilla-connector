"""Fixtures y dobles de prueba (fakes) compartidos por la suite.

Los fakes implementan los Protocols ``OdooApi`` / ``WooApi`` con almacenamiento
en memoria, de modo que los servicios se testean sin red ni servidores reales.
"""

from __future__ import annotations

from typing import Any

import pytest

from capuccino_vainilla.config import (
    AppConfig,
    OdooConfig,
    RuntimeConfig,
    WatcherConfig,
    WebhookConfig,
    WooConfig,
)

# --------------------------------------------------------------------------- #
#  Fake de Odoo
# --------------------------------------------------------------------------- #

class FakeOdoo:
    """Implementación en memoria de ``OdooApi`` con soporte de dominio básico."""

    def __init__(self, db: dict[str, list[dict]] | None = None):
        self.db: dict[str, list[dict]] = db or {}
        self._next_id: dict[str, int] = {}
        self.created: list[tuple[str, dict]] = []

    @staticmethod
    def _match(rec: dict, domain: list) -> bool:
        for field, op, val in domain:
            current = rec.get(field)
            if op == "=" and current != val:
                return False
            if op == "in" and current not in val:
                return False
            if op == ">=" and not (current is not None and current >= val):
                return False
        return True

    def _project(self, rec: dict, fields: list[str]) -> dict:
        projected = {"id": rec["id"]}
        projected.update({f: rec.get(f) for f in fields})
        return projected

    def search_count(self, model: str, domain: list) -> int:
        return len([r for r in self.db.get(model, []) if self._match(r, domain)])

    def search_read(self, model, domain, fields, offset=0, limit=None, order=None) -> list[dict]:
        rows = [r for r in self.db.get(model, []) if self._match(r, domain)]
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return [self._project(r, fields) for r in rows]

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        index = {r["id"]: r for r in self.db.get(model, [])}
        return [self._project(index[i], fields) for i in ids if i in index]

    def create(self, model: str, values: dict) -> int:
        new_id = self._next_id.get(model, 5000)
        self._next_id[model] = new_id + 1
        record = dict(values)
        record["id"] = new_id
        self.db.setdefault(model, []).append(record)
        self.created.append((model, values))
        return new_id

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        return True


# --------------------------------------------------------------------------- #
#  Fake de WooCommerce
# --------------------------------------------------------------------------- #

class FakeWoo:
    """Implementación en memoria de ``WooApi``."""

    def __init__(self):
        self.products: dict[int, dict] = {}
        self.products_by_sku: dict[str, dict] = {}
        self.attributes: list[dict] = []
        self.terms: dict[int, list[dict]] = {}
        self.orders: dict[int, dict] = {}
        self.calls: list[tuple[str, str, dict]] = []
        self.fail_on_post_products = False
        self._next_pid = 200
        self._next_aid = 10
        self._next_tid = 100

    def preload_product(self, sku: str, woo_id: int, **extra) -> None:
        product = {"id": woo_id, "sku": sku, **extra}
        self.products[woo_id] = product
        self.products_by_sku[sku] = product

    def preload_attribute(self, name: str, attr_id: int) -> None:
        self.attributes.append({"id": attr_id, "name": name})

    def preload_order(self, order_id: int, order: dict) -> None:
        self.orders[order_id] = {"id": order_id, **order}

    def get(self, endpoint: str, params: dict | None = None) -> Any:
        params = params or {}
        self.calls.append(("get", endpoint, params))
        if endpoint == "products":
            if params.get("sku"):
                product = self.products_by_sku.get(params.get("sku"))
                return [product] if product else []
            return list(self.products.values())
        if endpoint == "products/attributes":
            return list(self.attributes)
        if endpoint.startswith("products/attributes/") and endpoint.endswith("/terms"):
            attr_id = int(endpoint.split("/")[2])
            return list(self.terms.get(attr_id, []))
        if endpoint == "orders":
            return list(self.orders.values())
        if endpoint.startswith("orders/"):
            return self.orders.get(int(endpoint.split("/")[1]))
        return []

    def post(self, endpoint: str, data: dict) -> Any:
        self.calls.append(("post", endpoint, data))
        if endpoint == "products":
            if self.fail_on_post_products:
                from capuccino_vainilla.exceptions import WooError
                raise WooError("Fallo simulado al crear producto.")
            pid = self._next_pid
            self._next_pid += 1
            product = {"id": pid, **data}
            self.products[pid] = product
            if data.get("sku"):
                self.products_by_sku[data["sku"]] = product
            return product
        if endpoint == "products/attributes":
            aid = self._next_aid
            self._next_aid += 1
            attr = {"id": aid, "name": data["name"]}
            self.attributes.append(attr)
            return attr
        if endpoint.startswith("products/attributes/") and endpoint.endswith("/terms"):
            attr_id = int(endpoint.split("/")[2])
            tid = self._next_tid
            self._next_tid += 1
            term = {"id": tid, "name": data["name"]}
            self.terms.setdefault(attr_id, []).append(term)
            return term
        return {}

    def put(self, endpoint: str, data: dict) -> Any:
        self.calls.append(("put", endpoint, data))
        pid = int(endpoint.split("/")[1])
        product = self.products.get(pid, {"id": pid})
        product.update(data)
        self.products[pid] = product
        return product


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def fake_odoo() -> FakeOdoo:
    return FakeOdoo()


@pytest.fixture
def fake_woo() -> FakeWoo:
    return FakeWoo()


def make_config(webhook_secret: str = "test-secret") -> AppConfig:
    """Construye una AppConfig completa sin leer el entorno (para tests)."""
    return AppConfig(
        odoo=OdooConfig(url="http://odoo.test", db="db", username="u", password="p"),
        woo=WooConfig(
            url="http://woo.test", consumer_key="ck", consumer_secret="cs",
            api_version="wc/v3", verify_ssl=False, timeout=10,
        ),
        webhook=WebhookConfig(
            secret=webhook_secret, path="/webhooks/woocommerce/orders",
            host="127.0.0.1", port=8000,
        ),
        runtime=RuntimeConfig(
            batch_size=2, max_retries=2, retry_delay=0.0,
            log_level="INFO", log_file="test.log", state_file=".state.json",
        ),
        watcher=WatcherConfig(interval=1, initial_full=True, state_file=".watch.json"),
    )


@pytest.fixture
def app_config() -> AppConfig:
    return make_config()
