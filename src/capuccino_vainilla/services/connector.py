"""Fachada de alto nivel que cablea clientes y servicios.

``OdooWooConnector`` es el punto de entrada programático del paquete: construye
los clientes a partir de la configuración y expone los dos flujos de negocio.
"""

from __future__ import annotations

import logging

from ..clients import OdooClient, WooClient
from ..config import AppConfig
from ..logging_config import get_logger
from .attribute_sync import AttributeSyncService
from .catalog_sync import CatalogSyncService, SyncReport
from .order_import import OrderImportService


class OdooWooConnector:
    """Conector bidireccional Odoo ⇄ WooCommerce."""

    def __init__(self, config: AppConfig, logger: logging.Logger | None = None):
        self.config = config
        self._log = logger or get_logger("connector")

        # Clientes de bajo nivel (abren conexión / autentican).
        self.odoo = OdooClient(config.odoo, config.runtime, self._log)
        self.woo = WooClient(config.woo, config.runtime, self._log)

        # Servicios de negocio.
        attribute_service = AttributeSyncService(self.woo, get_logger("attributes"))
        self.catalog = CatalogSyncService(
            self.odoo, self.woo, attribute_service,
            batch_size=config.runtime.batch_size, logger=get_logger("catalog"),
        )
        self.orders = OrderImportService(self.odoo, get_logger("orders"))

    # -- API pública -------------------------------------------------------

    def sync_catalog(
        self, *, full: bool = True, since: str | None = None, limit: int | None = None
    ) -> SyncReport:
        """Flujo 1: sincroniza el catálogo de Odoo hacia WooCommerce."""
        return self.catalog.run(full=full, since=since, limit=limit)

    def import_order(self, payload: dict) -> int:
        """Flujo 2: impacta un pedido de WooCommerce en Odoo."""
        return self.orders.import_order(payload)
