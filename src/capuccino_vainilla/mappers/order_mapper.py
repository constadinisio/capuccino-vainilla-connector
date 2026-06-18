"""Transformaciones puras: pedido de WooCommerce -> estructuras de Odoo."""

from __future__ import annotations

from ..models.order import Address


def build_partner_values(
    billing: Address,
    shipping: Address,
    country_id: int | None = None,
) -> dict:
    """Construye los valores para crear un ``res.partner`` en Odoo.

    Prioriza la dirección de envío para los datos postales; usa facturación
    como respaldo.
    """
    values: dict = {
        "name": billing.full_name or billing.email,
        "email": billing.email,
        "phone": billing.phone,
        "street": shipping.address_1 or billing.address_1,
        "street2": shipping.address_2 or billing.address_2,
        "city": shipping.city or billing.city,
        "zip": shipping.postcode or billing.postcode,
        "company_name": billing.company,
        "customer_rank": 1,  # marca el contacto como cliente
    }
    if country_id:
        values["country_id"] = country_id
    return values


def build_sale_order_line(product_id: int, quantity: float, unit_price: float) -> list:
    """Devuelve el comando one2many de Odoo (0, 0, {...}) para crear una línea."""
    return [0, 0, {
        "product_id": product_id,
        "product_uom_qty": quantity,
        "price_unit": unit_price,
    }]


def build_sale_order_values(
    partner_id: int,
    client_order_ref: str,
    order_lines: list[list],
) -> dict:
    """Construye los valores para crear un ``sale.order`` en Odoo."""
    return {
        "partner_id": partner_id,
        "client_order_ref": client_order_ref,  # referencia cruzada con la web
        "order_line": order_lines,
    }
