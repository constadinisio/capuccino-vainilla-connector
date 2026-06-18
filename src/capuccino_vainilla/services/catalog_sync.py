"""FLUJO 1 — Sincronización de catálogo Odoo -> WooCommerce.

Procesa el catálogo por lotes paginados y en dos fases:
  1. Crea/actualiza cada producto (idempotente por SKU).
  2. Resuelve las ventas cruzadas (cross-sell), cuando todos los productos ya
     existen en Woo y se conocen sus ids.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..clients.protocols import OdooApi, WooApi
from ..exceptions import ConnectorError
from ..logging_config import get_logger
from ..mappers.product_mapper import build_woo_product_payload
from ..models.product import OdooProduct, ProductAttribute, normalize_text
from .attribute_sync import AttributeSyncService

# Campos que leemos del template de producto en Odoo.
ODOO_PRODUCT_FIELDS = [
    "id",
    "name",
    "default_code",          # SKU (clave de mapeo)
    "list_price",            # Precio de venta
    "description_sale",      # Descripción comercial
    "qty_available",         # Stock disponible
    "attribute_line_ids",    # Líneas de atributos (ficha técnica)
    "optional_product_ids",  # Accesorios / ventas cruzadas
]


@dataclass
class SyncReport:
    """Resumen de una corrida de sincronización de catálogo."""

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    cross_sells_linked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "cross_sells_linked": self.cross_sells_linked,
        }


class CatalogSyncService:
    """Servicio del Flujo 1."""

    def __init__(
        self,
        odoo: OdooApi,
        woo: WooApi,
        attribute_service: AttributeSyncService,
        batch_size: int = 50,
        logger: logging.Logger | None = None,
    ):
        self._odoo = odoo
        self._woo = woo
        self._attributes = attribute_service
        self._batch_size = max(1, batch_size)
        self._log = logger or get_logger("catalog")
        self._sku_to_woo_id: dict[str, int] = {}  # caché SKU -> id producto Woo

    # -- Orquestación ------------------------------------------------------

    def run(
        self, *, full: bool = True, since: str | None = None, limit: int | None = None
    ) -> SyncReport:
        """Ejecuta la sincronización del catálogo.

        Args:
            full: si True ignora `since` (sincronización completa).
            since: fecha/hora UTC ('YYYY-MM-DD HH:MM:SS') para sincronización
                incremental por `write_date`.
            limit: tope opcional de productos a procesar (para pruebas).
        """
        domain: list = [("sale_ok", "=", True)]
        if not full and since:
            domain.append(("write_date", ">=", since))
            self._log.info("Sincronización incremental desde %s", since)

        total = self._odoo.search_count("product.template", domain)
        if limit is not None:
            total = min(total, limit)
        report = SyncReport(total=total)
        self._log.info("Inicio de sincronización de catálogo. Productos a procesar: %s", total)

        cross_sell_jobs: list[tuple[int, tuple[int, ...]]] = []
        offset = 0
        while offset < total:
            page_limit = min(self._batch_size, total - offset)
            records = self._odoo.search_read(
                "product.template", domain, ODOO_PRODUCT_FIELDS,
                offset=offset, limit=page_limit, order="id asc",
            )
            if not records:
                break
            self._process_batch(records, report, cross_sell_jobs)
            offset += len(records)

        report.cross_sells_linked = self._sync_cross_sells(cross_sell_jobs)
        self._log.info("Sincronización de catálogo finalizada: %s", report.as_dict())
        return report

    # -- Fase 1: productos -------------------------------------------------

    def _process_batch(
        self,
        records: list[dict],
        report: SyncReport,
        cross_sell_jobs: list[tuple[int, tuple[int, ...]]],
    ) -> None:
        products = self._resolve_products(records)

        # Asegura los atributos globales del lote en una sola pasada.
        batch_attributes: dict[str, set[str]] = {}
        for product in products:
            for attr in product.attributes:
                batch_attributes.setdefault(attr.name, set()).update(attr.values)
        attribute_ids = self._attributes.ensure_attributes(batch_attributes)

        for product in products:
            outcome, woo_id = self._upsert_product(product, attribute_ids)
            setattr(report, outcome, getattr(report, outcome) + 1)
            if woo_id and product.accessory_template_ids:
                cross_sell_jobs.append((woo_id, product.accessory_template_ids))

    def _upsert_product(
        self, product: OdooProduct, attribute_ids: dict[str, int]
    ) -> tuple[str, int | None]:
        """Crea o actualiza un producto. Devuelve (resultado, woo_id)."""
        if not product.sku:
            self._log.warning("Producto Odoo id=%s sin SKU. Se omite.", product.odoo_id)
            return "skipped", None

        try:
            payload = build_woo_product_payload(product, attribute_ids)
            existing_id = self._find_woo_id_by_sku(product.sku)
            if existing_id:
                result = self._woo.put(f"products/{existing_id}", payload)
                action = "updated"
            else:
                result = self._woo.post("products", payload)
                action = "created"

            woo_id = int(result["id"])
            self._sku_to_woo_id[product.sku] = woo_id
            self._log.info(
                "Producto %s | SKU=%s | Woo id=%s | Odoo id=%s",
                action, product.sku, woo_id, product.odoo_id,
            )
            return action, woo_id
        except (ConnectorError, KeyError, TypeError, ValueError) as exc:
            # Skip controlado: un producto roto no detiene el lote.
            self._log.error("Fallo sincronizando SKU=%s: %s", product.sku, exc)
            return "failed", None

    # -- Resolución de productos desde Odoo --------------------------------

    def _resolve_products(self, records: list[dict]) -> list[OdooProduct]:
        """Convierte registros crudos de Odoo en ``OdooProduct`` normalizados.

        Resuelve los atributos (2 lecturas batch: líneas y valores) para todo el
        lote, minimizando los round-trips a Odoo.
        """
        line_ids = [lid for rec in records for lid in (rec.get("attribute_line_ids") or [])]
        line_map = self._read_attribute_lines(line_ids)

        value_ids = [vid for line in line_map.values() for vid in line["value_ids"]]
        value_names = self._read_value_names(value_ids)

        products: list[OdooProduct] = []
        for rec in records:
            attributes = self._build_attributes(
                rec.get("attribute_line_ids") or [], line_map, value_names
            )
            products.append(OdooProduct(
                odoo_id=int(rec["id"]),
                sku=normalize_text(rec.get("default_code")).strip(),
                name=normalize_text(rec.get("name")),
                price=float(rec.get("list_price") or 0.0),
                description=normalize_text(rec.get("description_sale")),
                quantity=int(rec.get("qty_available") or 0),
                attributes=attributes,
                accessory_template_ids=tuple(rec.get("optional_product_ids") or []),
            ))
        return products

    def _read_attribute_lines(self, line_ids: list[int]) -> dict[int, dict]:
        if not line_ids:
            return {}
        lines = self._odoo.read(
            "product.template.attribute.line", line_ids, ["attribute_id", "value_ids"]
        )
        return {
            line["id"]: {
                "attribute_name": line["attribute_id"][1] if line.get("attribute_id") else "",
                "value_ids": line.get("value_ids") or [],
            }
            for line in lines
        }

    def _read_value_names(self, value_ids: list[int]) -> dict[int, str]:
        if not value_ids:
            return {}
        records = self._odoo.read("product.attribute.value", value_ids, ["name"])
        return {rec["id"]: rec["name"] for rec in records}

    @staticmethod
    def _build_attributes(
        product_line_ids: list[int],
        line_map: dict[int, dict],
        value_names: dict[int, str],
    ) -> tuple[ProductAttribute, ...]:
        attributes: list[ProductAttribute] = []
        for line_id in product_line_ids:
            line = line_map.get(line_id)
            if not line or not line["attribute_name"]:
                continue
            values = tuple(value_names[v] for v in line["value_ids"] if v in value_names)
            if values:
                attributes.append(ProductAttribute(name=line["attribute_name"], values=values))
        return tuple(attributes)

    # -- Fase 2: cross-selling ---------------------------------------------

    def _sync_cross_sells(self, jobs: list[tuple[int, tuple[int, ...]]]) -> int:
        if not jobs:
            return 0
        self._log.info("Resolviendo ventas cruzadas para %s productos.", len(jobs))

        # Resuelve los SKUs de los templates accesorios en una sola lectura.
        accessory_ids = {tid for _, tids in jobs for tid in tids}
        sku_by_template = self._read_accessory_skus(list(accessory_ids))

        linked = 0
        for woo_id, template_ids in jobs:
            cross_ids = []
            for tid in template_ids:
                sku = sku_by_template.get(tid)
                woo_accessory = self._find_woo_id_by_sku(sku) if sku else None
                if woo_accessory:
                    cross_ids.append(woo_accessory)
                else:
                    self._log.warning(
                        "Accesorio template_id=%s (sku=%s) no está en Woo. Se omite.", tid, sku
                    )
            if not cross_ids:
                continue
            try:
                self._woo.put(f"products/{woo_id}", {"cross_sell_ids": cross_ids})
                linked += 1
                self._log.info("Cross-sell asignado a Woo id=%s -> %s", woo_id, cross_ids)
            except ConnectorError as exc:
                self._log.error("Fallo asignando cross-sell a Woo id=%s: %s", woo_id, exc)
        return linked

    def _read_accessory_skus(self, template_ids: list[int]) -> dict[int, str]:
        if not template_ids:
            return {}
        records = self._odoo.read("product.template", template_ids, ["default_code"])
        return {
            rec["id"]: normalize_text(rec.get("default_code")).strip()
            for rec in records
            if rec.get("default_code")
        }

    # -- Utilidades --------------------------------------------------------

    def _find_woo_id_by_sku(self, sku: str) -> int | None:
        """Busca un producto en Woo por SKU exacto (clave de idempotencia)."""
        if sku in self._sku_to_woo_id:
            return self._sku_to_woo_id[sku]
        result = self._woo.get("products", params={"sku": sku})
        if isinstance(result, list) and result:
            woo_id = int(result[0]["id"])
            self._sku_to_woo_id[sku] = woo_id
            return woo_id
        return None
