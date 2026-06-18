"""Tests del mapper de pedidos (Woo -> Odoo)."""

from __future__ import annotations

from capuccino_vainilla.mappers.order_mapper import (
    build_partner_values,
    build_sale_order_line,
    build_sale_order_values,
)
from capuccino_vainilla.models.order import Address


def test_build_partner_values_prefers_shipping_address():
    billing = Address(first_name="Lucía", last_name="Gómez", email="l@e.com",
                      address_1="Factura 1", city="CABA", postcode="C1000")
    shipping = Address(address_1="Envío 2", city="La Plata", postcode="B1900")
    values = build_partner_values(billing, shipping, country_id=10)
    assert values["name"] == "Lucía Gómez"
    assert values["email"] == "l@e.com"
    assert values["street"] == "Envío 2"      # prioriza envío
    assert values["city"] == "La Plata"
    assert values["country_id"] == 10
    assert values["customer_rank"] == 1


def test_build_partner_values_without_country():
    billing = Address(first_name="A", email="a@e.com", address_1="Calle 1")
    values = build_partner_values(billing, Address(), country_id=None)
    assert "country_id" not in values
    assert values["street"] == "Calle 1"      # fallback a facturación


def test_build_sale_order_line_command():
    line = build_sale_order_line(product_id=42, quantity=3, unit_price=100.0)
    assert line == [0, 0, {"product_id": 42, "product_uom_qty": 3, "price_unit": 100.0}]


def test_build_sale_order_values():
    line = build_sale_order_line(1, 1, 10.0)
    values = build_sale_order_values(partner_id=7, client_order_ref="WC-99", order_lines=[line])
    assert values["partner_id"] == 7
    assert values["client_order_ref"] == "WC-99"
    assert values["order_line"] == [line]
