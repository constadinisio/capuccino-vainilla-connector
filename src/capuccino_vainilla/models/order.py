"""Modelos de dominio del pedido de WooCommerce (payload del webhook)."""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import MappingError


def _str(value: object, default: str = "") -> str:
    return default if value is None else str(value).strip()


@dataclass(frozen=True)
class Address:
    """Dirección de facturación o envío de WooCommerce."""

    first_name: str = ""
    last_name: str = ""
    company: str = ""
    address_1: str = ""
    address_2: str = ""
    city: str = ""
    postcode: str = ""
    country: str = ""
    email: str = ""
    phone: str = ""

    @classmethod
    def from_dict(cls, data: dict | None) -> Address:
        data = data or {}
        return cls(
            first_name=_str(data.get("first_name")),
            last_name=_str(data.get("last_name")),
            company=_str(data.get("company")),
            address_1=_str(data.get("address_1")),
            address_2=_str(data.get("address_2")),
            city=_str(data.get("city")),
            postcode=_str(data.get("postcode")),
            country=_str(data.get("country")),
            email=_str(data.get("email")),
            phone=_str(data.get("phone")),
        )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class LineItem:
    """Una línea del carrito de WooCommerce."""

    sku: str
    name: str
    quantity: float
    total: float
    price: float

    @classmethod
    def from_dict(cls, data: dict) -> LineItem:
        return cls(
            sku=_str(data.get("sku")),
            name=_str(data.get("name")),
            quantity=float(data.get("quantity") or 1),
            total=float(data.get("total") or 0),
            price=float(data.get("price") or 0),
        )

    @property
    def unit_price(self) -> float:
        """Precio unitario realmente cobrado (total/cantidad).

        Se usa el total de la línea para reflejar descuentos aplicados en la web
        y evitar descuadres con Odoo.
        """
        if self.quantity:
            return round(self.total / self.quantity, 4)
        return self.price


@dataclass(frozen=True)
class WooOrder:
    """Pedido de WooCommerce normalizado."""

    number: str
    billing: Address
    shipping: Address
    line_items: tuple[LineItem, ...]

    @classmethod
    def from_payload(cls, payload: dict) -> WooOrder:
        """Parsea y valida el JSON del webhook ``order.created``.

        Raises:
            MappingError: si el payload no es un objeto o carece de líneas.
        """
        if not isinstance(payload, dict):
            raise MappingError("El payload del pedido debe ser un objeto JSON.")

        raw_items = payload.get("line_items") or []
        if not raw_items:
            raise MappingError("El pedido no contiene líneas (line_items vacío).")

        return cls(
            number=_str(payload.get("number") or payload.get("id"), "s/n"),
            billing=Address.from_dict(payload.get("billing")),
            shipping=Address.from_dict(payload.get("shipping")),
            line_items=tuple(LineItem.from_dict(item) for item in raw_items),
        )
