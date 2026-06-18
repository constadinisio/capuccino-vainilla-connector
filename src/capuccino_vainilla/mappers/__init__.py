"""Transformaciones puras entre modelos de Odoo y payloads de WooCommerce."""

from __future__ import annotations

from .order_mapper import (
    build_partner_values,
    build_sale_order_line,
    build_sale_order_values,
)
from .product_mapper import ODOO_ID_META_KEY, build_woo_product_payload

__all__ = [
    "ODOO_ID_META_KEY",
    "build_woo_product_payload",
    "build_partner_values",
    "build_sale_order_line",
    "build_sale_order_values",
]
