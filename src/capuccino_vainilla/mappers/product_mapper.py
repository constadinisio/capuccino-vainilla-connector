"""Transformación pura: ``OdooProduct`` -> payload de producto de WooCommerce.

No realiza I/O: recibe ya resuelto el mapa ``nombre_atributo -> id_global_woo``
para poder construir el array de atributos globales (necesarios para que los
filtros nativos de la tienda funcionen).
"""

from __future__ import annotations

from ..models.product import OdooProduct

# Meta key donde guardamos el id de Odoo dentro del producto de WooCommerce.
ODOO_ID_META_KEY = "_odoo_product_id"


def _build_attributes(product: OdooProduct, attribute_ids: dict[str, int]) -> list[dict]:
    """Construye el array `attributes` de Woo usando atributos globales por id."""
    attributes: list[dict] = []
    for position, attr in enumerate(product.attributes):
        attr_id = attribute_ids.get(attr.name.strip().lower())
        if attr_id is None or not attr.values:
            continue  # sin id global resuelto o sin valores: se omite
        attributes.append({
            "id": attr_id,
            "name": attr.name,
            "position": position,
            "visible": True,
            "variation": False,
            "options": list(attr.values),
        })
    return attributes


def build_woo_product_payload(
    product: OdooProduct,
    attribute_ids: dict[str, int],
) -> dict:
    """Mapea un producto de Odoo al payload de creación/actualización de Woo.

    Args:
        product: producto normalizado de Odoo.
        attribute_ids: mapa ``nombre_atributo.lower() -> id_atributo_global_woo``.
    """
    return {
        "name": product.name,
        "sku": product.sku,
        "type": "simple",
        "status": "publish",
        "regular_price": f"{product.price:.2f}",
        "description": product.description,
        # Gestión de stock: Woo refleja las cantidades provenientes de Odoo.
        "manage_stock": True,
        "stock_quantity": product.quantity,
        "stock_status": "instock" if product.in_stock else "outofstock",
        "attributes": _build_attributes(product, attribute_ids),
        # Trazabilidad inversa: id de Odoo guardado como meta dato.
        "meta_data": [{"key": ODOO_ID_META_KEY, "value": str(product.odoo_id)}],
    }
