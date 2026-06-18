"""Modelos de dominio (DTOs inmutables) compartidos entre capas."""

from __future__ import annotations

from .order import Address, LineItem, WooOrder
from .product import OdooProduct, ProductAttribute

__all__ = ["Address", "LineItem", "WooOrder", "OdooProduct", "ProductAttribute"]
