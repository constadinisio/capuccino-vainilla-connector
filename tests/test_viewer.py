"""Tests del visor: servicio (con clientes fake) y API (con TestClient)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from capuccino_vainilla.viewer.app import create_viewer_app
from capuccino_vainilla.viewer.service import ViewerService

from .conftest import make_config


def _service(fake_odoo, fake_woo) -> ViewerService:
    return ViewerService(make_config(), odoo=fake_odoo, woo=fake_woo)


# --------------------------------------------------------------------------- #
#  ViewerService
# --------------------------------------------------------------------------- #

def test_health_reports_both_systems(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": [{"id": 1, "sale_ok": True}]}
    health = _service(fake_odoo, fake_woo).health()
    assert health["odoo"]["ok"] is True
    assert health["woo"]["ok"] is True


def test_list_odoo_products_normalizes(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": [{
        "id": 9, "name": "Cam", "default_code": "CAM-1", "list_price": 100.0,
        "qty_available": 3, "attribute_line_ids": [1, 2], "optional_product_ids": [5],
        "sale_ok": True,
    }]}
    items = _service(fake_odoo, fake_woo).list_odoo_products()
    assert items[0]["sku"] == "CAM-1"
    assert items[0]["n_attributes"] == 2
    assert items[0]["n_accessories"] == 1


def test_list_woo_products_extracts_odoo_meta(fake_odoo, fake_woo):
    fake_woo.preload_product(
        "CAM-1", 200, name="Cam", regular_price="100",
        meta_data=[{"key": "_odoo_product_id", "value": "9"}],
    )
    items = _service(fake_odoo, fake_woo).list_woo_products()
    assert items[0]["odoo_id"] == "9"


def test_list_woo_products_clamps_per_page(fake_odoo, fake_woo):
    """Woo exige per_page en [1, 100]; valores fuera de rango deben acotarse
    en el borde para no provocar un 400 (rest_out_of_bounds)."""
    svc = _service(fake_odoo, fake_woo)
    svc.list_woo_products(per_page=0)
    svc.list_woo_products(per_page=500)
    per_pages = [params["per_page"] for (_, ep, params) in fake_woo.calls if ep == "products"]
    assert per_pages == [1, 100]


def test_run_sync_executes_flow(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": [{
        "id": 1, "name": "X", "default_code": "X-1", "list_price": 10.0,
        "qty_available": 1, "attribute_line_ids": [], "optional_product_ids": [],
        "sale_ok": True, "write_date": "2026-01-01 00:00:00",
    }]}
    report = _service(fake_odoo, fake_woo).run_sync(full=True)
    assert report["created"] == 1


def test_import_woo_order_creates_sale_order(fake_odoo, fake_woo):
    fake_odoo.db = {
        "res.partner": [{"id": 5, "email": "a@e.com"}],
        "product.product": [{"id": 77, "default_code": "X-1"}],
    }
    fake_woo.preload_order(50, {
        "number": "50", "billing": {"email": "a@e.com"},
        "line_items": [{"sku": "X-1", "quantity": 1, "total": "10"}],
    })
    result = _service(fake_odoo, fake_woo).import_woo_order(50)
    assert result["woo_order_id"] == 50
    assert result["sale_order_id"]


# --------------------------------------------------------------------------- #
#  API (FastAPI)
# --------------------------------------------------------------------------- #

def test_index_served(fake_odoo, fake_woo):
    app = create_viewer_app(make_config(), service=_service(fake_odoo, fake_woo))
    resp = TestClient(app).get("/")
    assert resp.status_code == 200
    assert "Capuccino Vainilla" in resp.text


def test_api_health_endpoint(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": []}
    app = create_viewer_app(make_config(), service=_service(fake_odoo, fake_woo))
    data = TestClient(app).get("/api/health").json()
    assert "odoo" in data and "woo" in data


def test_api_sync_endpoint(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": [{
        "id": 1, "name": "X", "default_code": "X-1", "list_price": 10.0,
        "qty_available": 1, "attribute_line_ids": [], "optional_product_ids": [],
        "sale_ok": True, "write_date": "2026-01-01 00:00:00",
    }]}
    app = create_viewer_app(make_config(), service=_service(fake_odoo, fake_woo))
    resp = TestClient(app).post("/api/sync/catalog", json={"full": True})
    body = resp.json()
    assert body["ok"] is True
    assert body["report"]["created"] == 1


def test_api_sync_progress_starts_idle(fake_odoo, fake_woo):
    app = create_viewer_app(make_config(), service=_service(fake_odoo, fake_woo))
    data = TestClient(app).get("/api/sync/progress").json()
    assert data["running"] is False
    assert data["percent"] == 0
    assert "eta_seconds" in data


def test_api_sync_reaches_full_progress(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": [{
        "id": 1, "name": "X", "default_code": "X-1", "list_price": 10.0,
        "qty_available": 1, "attribute_line_ids": [], "optional_product_ids": [],
        "sale_ok": True, "write_date": "2026-01-01 00:00:00",
    }]}
    app = create_viewer_app(make_config(), service=_service(fake_odoo, fake_woo))
    client = TestClient(app)
    client.post("/api/sync/catalog", json={"full": True})
    data = client.get("/api/sync/progress").json()
    assert data["running"] is False
    assert data["percent"] == 100


def test_api_import_order_endpoint(fake_odoo, fake_woo):
    fake_odoo.db = {
        "res.partner": [{"id": 5, "email": "a@e.com"}],
        "product.product": [{"id": 77, "default_code": "X-1"}],
    }
    fake_woo.preload_order(50, {
        "number": "50", "billing": {"email": "a@e.com"},
        "line_items": [{"sku": "X-1", "quantity": 1, "total": "10"}],
    })
    app = create_viewer_app(make_config(), service=_service(fake_odoo, fake_woo))
    resp = TestClient(app).post("/api/woo/orders/50/import")
    assert resp.json()["ok"] is True
