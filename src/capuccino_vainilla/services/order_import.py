"""FLUJO 2 — Importación de pedidos WooCommerce -> Odoo.

Recibe el JSON de un pedido (webhook ``order.created``) y:
  1. Busca o crea el cliente en ``res.partner`` (clave: email).
  2. Mapea las líneas por SKU a ``sale.order.line``.
  3. Crea el ``sale.order`` con el precio cobrado en la web.
"""

from __future__ import annotations

import logging

from ..clients.protocols import OdooApi
from ..exceptions import MappingError
from ..logging_config import get_logger
from ..mappers.order_mapper import (
    build_partner_values,
    build_sale_order_line,
    build_sale_order_values,
)
from ..models.order import WooOrder


class OrderImportService:
    """Servicio del Flujo 2."""

    def __init__(self, odoo: OdooApi, logger: logging.Logger | None = None):
        self._odoo = odoo
        self._log = logger or get_logger("orders")

    def import_order(self, payload: dict) -> int:
        """Impacta un pedido de Woo en Odoo y devuelve el id del ``sale.order``.

        Raises:
            MappingError: si el payload es inválido, falta el email o ninguna
                línea pudo mapearse a un producto existente en Odoo.
        """
        order = WooOrder.from_payload(payload)
        self._log.info("Importando pedido Woo #%s a Odoo.", order.number)

        if not order.billing.email:
            raise MappingError(f"Pedido #{order.number} sin email de facturación.")

        partner_id = self._find_or_create_partner(order)
        order_lines = self._build_order_lines(order)
        if not order_lines:
            raise MappingError(
                f"Pedido #{order.number}: ninguna línea pudo mapearse a productos de Odoo."
            )

        values = build_sale_order_values(partner_id, f"WC-{order.number}", order_lines)
        sale_order_id = self._odoo.create("sale.order", values)
        self._log.info(
            "Pedido Woo #%s creado en Odoo como sale.order id=%s.", order.number, sale_order_id
        )
        return sale_order_id

    # -- Cliente -----------------------------------------------------------

    def _find_or_create_partner(self, order: WooOrder) -> int:
        email = order.billing.email
        existing = self._odoo.search_read("res.partner", [("email", "=", email)], ["id"], limit=1)
        if existing:
            partner_id = int(existing[0]["id"])
            self._log.info("Cliente existente en Odoo: %s (id=%s)", email, partner_id)
            return partner_id

        country_id = self._resolve_country_id(order.shipping.country or order.billing.country)
        values = build_partner_values(order.billing, order.shipping, country_id)
        partner_id = self._odoo.create("res.partner", values)
        self._log.info("Cliente creado en Odoo: %s (id=%s)", email, partner_id)
        return partner_id

    def _resolve_country_id(self, country_code: str) -> int | None:
        if not country_code:
            return None
        records = self._odoo.search_read(
            "res.country", [("code", "=", country_code.upper())], ["id"], limit=1
        )
        return int(records[0]["id"]) if records else None

    # -- Líneas ------------------------------------------------------------

    def _build_order_lines(self, order: WooOrder) -> list[list]:
        order_lines: list[list] = []
        for item in order.line_items:
            if not item.sku:
                self._log.warning("Ítem sin SKU en pedido #%s ('%s'). Se omite.",
                                  order.number, item.name)
                continue
            product_id = self._find_product_id_by_sku(item.sku)
            if not product_id:
                self._log.warning("SKU=%s del pedido #%s no existe en Odoo. Se omite la línea.",
                                  item.sku, order.number)
                continue
            order_lines.append(build_sale_order_line(product_id, item.quantity, item.unit_price))
        return order_lines

    def _find_product_id_by_sku(self, sku: str) -> int | None:
        records = self._odoo.search_read(
            "product.product", [("default_code", "=", sku)], ["id"], limit=1
        )
        return int(records[0]["id"]) if records else None
