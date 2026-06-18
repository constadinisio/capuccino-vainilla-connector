"""Tests del mapper de productos (Odoo -> Woo)."""

from __future__ import annotations

from capuccino_vainilla.mappers.product_mapper import (
    ODOO_ID_META_KEY,
    build_woo_product_payload,
)
from capuccino_vainilla.models.product import OdooProduct, ProductAttribute


def _product(**overrides) -> OdooProduct:
    base = dict(
        odoo_id=101, sku="CAM-4K-001", name="Cámara 4K", price=850000.0,
        description="Cámara profesional", quantity=5,
        attributes=(ProductAttribute(name="Marca", values=("Sony", "Canon")),),
        accessory_template_ids=(),
    )
    base.update(overrides)
    return OdooProduct(**base)


def test_basic_fields():
    payload = build_woo_product_payload(_product(), {"marca": 10})
    assert payload["sku"] == "CAM-4K-001"
    assert payload["regular_price"] == "850000.00"
    assert payload["manage_stock"] is True
    assert payload["stock_quantity"] == 5
    assert payload["stock_status"] == "instock"
    assert payload["meta_data"] == [{"key": ODOO_ID_META_KEY, "value": "101"}]


def test_out_of_stock():
    payload = build_woo_product_payload(_product(quantity=0), {})
    assert payload["stock_status"] == "outofstock"


def test_attributes_use_global_id():
    payload = build_woo_product_payload(_product(), {"marca": 10})
    attrs = payload["attributes"]
    assert len(attrs) == 1
    assert attrs[0]["id"] == 10
    assert attrs[0]["options"] == ["Sony", "Canon"]
    assert attrs[0]["visible"] is True


def test_attribute_without_resolved_id_is_skipped():
    payload = build_woo_product_payload(_product(), {})  # mapa vacío
    assert payload["attributes"] == []
