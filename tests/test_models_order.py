"""Tests de los modelos de dominio del pedido."""

from __future__ import annotations

import pytest

from capuccino_vainilla.exceptions import MappingError
from capuccino_vainilla.models.order import Address, LineItem, WooOrder


def test_address_from_dict_and_full_name():
    addr = Address.from_dict({"first_name": "Lucía", "last_name": "Gómez", "email": "l@e.com"})
    assert addr.full_name == "Lucía Gómez"
    assert addr.email == "l@e.com"


def test_address_from_none_is_empty():
    addr = Address.from_dict(None)
    assert addr.full_name == ""
    assert addr.email == ""


def test_line_item_unit_price_uses_total():
    item = LineItem.from_dict({"sku": "X", "quantity": 2, "total": "228000.00", "price": "120000"})
    assert item.unit_price == 114000.0  # total/qty refleja descuentos


def test_line_item_unit_price_fallback_to_price_when_no_qty():
    item = LineItem(sku="X", name="x", quantity=0, total=0, price=999.0)
    assert item.unit_price == 999.0


def test_woo_order_from_payload_ok():
    order = WooOrder.from_payload({
        "number": "7421",
        "billing": {"email": "l@e.com"},
        "line_items": [{"sku": "A", "quantity": 1, "total": "10"}],
    })
    assert order.number == "7421"
    assert len(order.line_items) == 1


def test_woo_order_requires_line_items():
    with pytest.raises(MappingError):
        WooOrder.from_payload({"number": "1", "line_items": []})


def test_woo_order_rejects_non_dict():
    with pytest.raises(MappingError):
        WooOrder.from_payload([1, 2, 3])  # type: ignore[arg-type]
