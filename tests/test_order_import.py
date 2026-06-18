"""Tests del servicio de importación de pedidos (Flujo 2)."""

from __future__ import annotations

import pytest

from capuccino_vainilla.exceptions import MappingError
from capuccino_vainilla.services.order_import import OrderImportService


def _payload(**extra) -> dict:
    base = {
        "number": "7421",
        "billing": {"first_name": "Lucía", "last_name": "Gómez",
                    "email": "lucia@e.com", "country": "AR"},
        "shipping": {"address_1": "Calle 1", "city": "CABA", "country": "AR"},
        "line_items": [{"sku": "CAM-1", "quantity": 2, "total": "2000.00"}],
    }
    base.update(extra)
    return base


def test_creates_order_for_existing_partner(fake_odoo):
    fake_odoo.db = {
        "res.partner": [{"id": 5, "email": "lucia@e.com"}],
        "product.product": [{"id": 77, "default_code": "CAM-1"}],
    }
    service = OrderImportService(fake_odoo)
    sale_id = service.import_order(_payload())

    assert sale_id  # se creó la orden
    # No se creó un partner nuevo (ya existía).
    assert not any(model == "res.partner" for model, _ in fake_odoo.created)
    # La línea respeta el precio unitario (total/qty = 1000).
    sale = [v for m, v in fake_odoo.created if m == "sale.order"][0]
    assert sale["order_line"][0][2]["price_unit"] == 1000.0


def test_creates_partner_when_missing(fake_odoo):
    fake_odoo.db = {
        "res.partner": [],
        "res.country": [{"id": 10, "code": "AR"}],
        "product.product": [{"id": 77, "default_code": "CAM-1"}],
    }
    service = OrderImportService(fake_odoo)
    service.import_order(_payload())

    partner = [v for m, v in fake_odoo.created if m == "res.partner"][0]
    assert partner["email"] == "lucia@e.com"
    assert partner["country_id"] == 10


def test_missing_email_raises(fake_odoo):
    payload = _payload(billing={"first_name": "X"})
    with pytest.raises(MappingError, match="email"):
        OrderImportService(fake_odoo).import_order(payload)


def test_no_mappable_lines_raises(fake_odoo):
    fake_odoo.db = {
        "res.partner": [{"id": 5, "email": "lucia@e.com"}],
        "product.product": [],  # el SKU no existe en Odoo
    }
    with pytest.raises(MappingError, match="mapearse"):
        OrderImportService(fake_odoo).import_order(_payload())
