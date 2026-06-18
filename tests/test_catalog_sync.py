"""Tests del servicio de sincronización de catálogo (Flujo 1)."""

from __future__ import annotations

from capuccino_vainilla.services.attribute_sync import AttributeSyncService
from capuccino_vainilla.services.catalog_sync import CatalogSyncService


def _service(fake_odoo, fake_woo, batch_size=50):
    return CatalogSyncService(
        fake_odoo, fake_woo, AttributeSyncService(fake_woo), batch_size=batch_size
    )


def _template(tid, sku, **extra):
    base = {
        "id": tid, "name": f"Producto {tid}", "default_code": sku,
        "list_price": 1000.0, "description_sale": "desc", "qty_available": 5,
        "attribute_line_ids": [], "optional_product_ids": [],
        "sale_ok": True, "write_date": "2026-01-01 00:00:00",
    }
    base.update(extra)
    return base


def test_creates_new_product_with_attributes(fake_odoo, fake_woo):
    fake_odoo.db = {
        "product.template": [_template(101, "CAM-1", attribute_line_ids=[1])],
        "product.template.attribute.line": [
            {"id": 1, "attribute_id": [10, "Marca"], "value_ids": [100]}
        ],
        "product.attribute.value": [{"id": 100, "name": "Sony"}],
    }
    report = _service(fake_odoo, fake_woo).run(full=True)

    assert report.total == 1
    assert report.created == 1
    assert "CAM-1" in fake_woo.products_by_sku
    created = fake_woo.products_by_sku["CAM-1"]
    assert created["attributes"][0]["options"] == ["Sony"]


def test_updates_existing_product(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": [_template(101, "CAM-1")]}
    fake_woo.preload_product("CAM-1", 200)

    report = _service(fake_odoo, fake_woo).run(full=True)

    assert report.updated == 1
    assert report.created == 0
    assert any(c[0] == "put" and c[1] == "products/200" for c in fake_woo.calls)


def test_skips_product_without_sku(fake_odoo, fake_woo):
    fake_odoo.db = {"product.template": [_template(101, False)]}
    report = _service(fake_odoo, fake_woo).run(full=True)
    assert report.skipped == 1
    assert report.created == 0


def test_failed_product_does_not_stop_batch(fake_odoo, fake_woo):
    fake_odoo.db = {
        "product.template": [_template(101, "CAM-1"), _template(102, "CAM-2")]
    }
    fake_woo.fail_on_post_products = True
    report = _service(fake_odoo, fake_woo).run(full=True)
    assert report.failed == 2  # ambos fallan pero el lote completa


def test_cross_sell_linking(fake_odoo, fake_woo):
    fake_odoo.db = {
        "product.template": [
            _template(101, "CAM-1", optional_product_ids=[102]),
            _template(102, "ACC-1"),
        ]
    }
    report = _service(fake_odoo, fake_woo).run(full=True)

    assert report.created == 2
    assert report.cross_sells_linked == 1
    accessory_woo_id = fake_woo.products_by_sku["ACC-1"]["id"]
    main_woo_id = fake_woo.products_by_sku["CAM-1"]["id"]
    assert fake_woo.products[main_woo_id]["cross_sell_ids"] == [accessory_woo_id]


def test_incremental_filters_by_write_date(fake_odoo, fake_woo):
    fake_odoo.db = {
        "product.template": [
            _template(101, "OLD", write_date="2020-01-01 00:00:00"),
            _template(102, "NEW", write_date="2026-06-01 00:00:00"),
        ]
    }
    report = _service(fake_odoo, fake_woo).run(full=False, since="2026-01-01 00:00:00")
    assert report.total == 1
    assert "NEW" in fake_woo.products_by_sku
    assert "OLD" not in fake_woo.products_by_sku


def test_limit_caps_processing(fake_odoo, fake_woo):
    fake_odoo.db = {
        "product.template": [_template(i, f"SKU-{i}") for i in range(1, 6)]
    }
    report = _service(fake_odoo, fake_woo, batch_size=2).run(full=True, limit=3)
    assert report.total == 3
    assert report.created == 3


def test_run_with_explicit_ids_only_syncs_those(fake_odoo, fake_woo):
    fake_odoo.db = {
        "product.template": [
            _template(101, "AAA"), _template(102, "BBB"), _template(103, "CCC"),
        ]
    }
    report = _service(fake_odoo, fake_woo).run(ids=[102])
    assert report.total == 1
    assert "BBB" in fake_woo.products_by_sku
    assert "AAA" not in fake_woo.products_by_sku
    assert "CCC" not in fake_woo.products_by_sku


def test_unpublish_sets_draft_for_known_skus(fake_odoo, fake_woo):
    fake_woo.preload_product("GONE", 200, status="publish")
    count = _service(fake_odoo, fake_woo).unpublish(["GONE", "MISSING", ""])
    assert count == 1
    assert fake_woo.products[200]["status"] == "draft"
    assert any(
        c[0] == "put" and c[1] == "products/200" and c[2] == {"status": "draft"}
        for c in fake_woo.calls
    )
