"""Clientes de bajo nivel para las APIs de Odoo y WooCommerce."""

from __future__ import annotations

from .odoo_client import OdooClient
from .woo_client import WooClient

__all__ = ["OdooClient", "WooClient"]
