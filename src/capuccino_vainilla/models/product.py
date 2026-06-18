"""Modelo de dominio del producto, normalizado desde Odoo.

Separar el modelo de la representación cruda de Odoo permite que los *mappers*
sean funciones puras y fácilmente testeables (sin tocar la red).
"""

from __future__ import annotations

from dataclasses import dataclass, field


def normalize_text(value: object) -> str:
    """Odoo devuelve ``False`` para char/text vacíos; lo normalizamos a ''."""
    return "" if value is False or value is None else str(value)


@dataclass(frozen=True)
class ProductAttribute:
    """Un atributo de la ficha técnica con sus valores (ej. Marca: [Sony, Canon])."""

    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class OdooProduct:
    """Representación normalizada de un ``product.template`` de Odoo."""

    odoo_id: int
    sku: str
    name: str
    price: float
    description: str
    quantity: int
    attributes: tuple[ProductAttribute, ...] = field(default_factory=tuple)
    accessory_template_ids: tuple[int, ...] = field(default_factory=tuple)

    @property
    def in_stock(self) -> bool:
        return self.quantity > 0
