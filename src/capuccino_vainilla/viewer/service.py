"""Servicio que alimenta al visor: lectura de datos y disparo de los flujos.

Reutiliza la misma lógica de producción (clientes y servicios). Los clientes se
pueden inyectar para testear sin red. Las conexiones se crean de forma perezosa,
de modo que el visor arranca aunque Odoo o Woo estén momentáneamente caídos.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..clients import OdooClient, WooClient
from ..clients.protocols import OdooApi, WooApi
from ..config import AppConfig
from ..logging_config import get_logger
from ..services.attribute_sync import AttributeSyncService
from ..services.catalog_sync import CatalogSyncService
from ..services.order_import import OrderImportService

# Campos de producto que mostramos desde Odoo.
_ODOO_FIELDS = [
    "id", "name", "default_code", "list_price", "qty_available",
    "attribute_line_ids", "optional_product_ids",
]


def _odoo_id_from_meta(meta_data: list | None) -> str | None:
    for meta in meta_data or []:
        if meta.get("key") == "_odoo_product_id":
            return meta.get("value")
    return None


class ViewerService:
    """Fachada de lectura/acciones para el dashboard."""

    def __init__(
        self,
        config: AppConfig,
        logger: logging.Logger | None = None,
        *,
        odoo: OdooApi | None = None,
        woo: WooApi | None = None,
    ):
        self._config = config
        self._log = logger or get_logger("viewer")
        self._odoo_client = odoo
        self._woo_client = woo

    # -- Acceso perezoso a clientes ----------------------------------------

    def _odoo(self) -> OdooApi:
        if self._odoo_client is None:
            self._odoo_client = OdooClient(self._config.odoo, self._config.runtime, self._log)
        return self._odoo_client

    def _woo(self) -> WooApi:
        if self._woo_client is None:
            self._woo_client = WooClient(self._config.woo, self._config.runtime, self._log)
        return self._woo_client

    # -- Estado de conexión ------------------------------------------------

    def health(self) -> dict:
        return {"odoo": self._check_odoo(), "woo": self._check_woo()}

    def _check_odoo(self) -> dict:
        info = {"url": self._config.odoo.url, "db": self._config.odoo.db}
        try:
            count = self._odoo().search_count("product.template", [("sale_ok", "=", True)])
            return {**info, "ok": True, "detail": f"{count} productos vendibles"}
        except Exception as exc:  # noqa: BLE001 - el visor reporta cualquier fallo
            self._odoo_client = None  # forzar reconexión en el próximo intento
            return {**info, "ok": False, "detail": str(exc)}

    def _check_woo(self) -> dict:
        info = {"url": self._config.woo.url}
        try:
            self._woo().get("products", {"per_page": 1})
            return {**info, "ok": True, "detail": "API REST accesible"}
        except Exception as exc:  # noqa: BLE001
            self._woo_client = None
            return {**info, "ok": False, "detail": str(exc)}

    # -- Listados ----------------------------------------------------------

    def list_odoo_products(self, limit: int = 20, offset: int = 0) -> list[dict]:
        limit = max(1, min(limit, 100))  # evita limit=0 (sin tope en Odoo) y acota el preview
        offset = max(0, offset)
        rows = self._odoo().search_read(
            "product.template", [("sale_ok", "=", True)], _ODOO_FIELDS,
            offset=offset, limit=limit, order="id desc",
        )
        return [
            {
                "odoo_id": r["id"],
                "sku": r.get("default_code") or "",
                "name": r.get("name") or "",
                "price": r.get("list_price") or 0,
                "qty": r.get("qty_available") or 0,
                "n_attributes": len(r.get("attribute_line_ids") or []),
                "n_accessories": len(r.get("optional_product_ids") or []),
            }
            for r in rows
        ]

    def list_woo_products(self, per_page: int = 20, page: int = 1) -> list[dict]:
        per_page = max(1, min(per_page, 100))  # Woo exige per_page en [1, 100]
        page = max(1, page)
        items = self._woo().get("products", {"per_page": per_page, "page": page}) or []
        return [
            {
                "woo_id": p.get("id"),
                "sku": p.get("sku") or "",
                "name": p.get("name") or "",
                "price": p.get("regular_price") or p.get("price") or "",
                "stock": p.get("stock_quantity"),
                "odoo_id": _odoo_id_from_meta(p.get("meta_data")),
            }
            for p in items
        ]

    def list_woo_orders(self, per_page: int = 10) -> list[dict]:
        per_page = max(1, min(per_page, 100))  # Woo exige per_page en [1, 100]
        items = self._woo().get(
            "orders", {"per_page": per_page, "status": "any", "orderby": "date", "order": "desc"}
        ) or []
        return [
            {
                "id": o.get("id"),
                "number": o.get("number"),
                "status": o.get("status"),
                "total": o.get("total"),
                "currency": o.get("currency"),
                "email": (o.get("billing") or {}).get("email", ""),
                "date_created": o.get("date_created"),
                "items": [
                    {"sku": li.get("sku"), "name": li.get("name"), "quantity": li.get("quantity")}
                    for li in (o.get("line_items") or [])
                ],
            }
            for o in items
        ]

    # -- Acciones (disparan los flujos reales) -----------------------------

    def run_sync(
        self,
        full: bool = True,
        limit: int | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict:
        service = CatalogSyncService(
            self._odoo(), self._woo(), AttributeSyncService(self._woo()),
            self._config.odoo.url,
            batch_size=self._config.runtime.batch_size, logger=self._log,
        )
        report = service.run(full=full, since=None, limit=limit, on_progress=on_progress)
        return report.as_dict()

    def import_woo_order(self, order_id: int) -> dict:
        payload = self._woo().get(f"orders/{order_id}")
        if not payload:
            raise ValueError(f"No se encontró el pedido {order_id} en WooCommerce.")
        sale_order_id = OrderImportService(self._odoo(), self._log).import_order(payload)
        return {"woo_order_id": order_id, "sale_order_id": sale_order_id}

    # -- Logs --------------------------------------------------------------

    def tail_logs(self, lines: int = 100) -> list[str]:
        try:
            with open(self._config.runtime.log_file, encoding="utf-8") as fh:
                return [line.rstrip("\n") for line in fh.readlines()[-lines:]]
        except FileNotFoundError:
            return []
        except OSError as exc:
            return [f"(no se pudo leer el log: {exc})"]
