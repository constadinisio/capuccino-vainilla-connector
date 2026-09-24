"""FLUJO 1 — Sincronización de catálogo Odoo -> WooCommerce.

Procesa el catálogo por lotes paginados y en dos fases:
  1. Crea/actualiza cada producto (idempotente por SKU).
  2. Resuelve los productos accesorios (upsells), cuando todos los productos
     ya existen en Woo y se conocen sus ids.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from ..clients.protocols import OdooApi, WooApi
from ..exceptions import ConnectorError
from ..logging_config import get_logger
from ..mappers.product_mapper import build_woo_product_payload
from ..models.product import OdooProduct, ProductAttribute, normalize_text
from .attribute_sync import AttributeSyncService
from .category_tag_sync import CATEGORY_PATH_SEPARATOR, CategoryTagSyncService

# Campos que leemos del template de producto en Odoo.
ODOO_PRODUCT_FIELDS = [
    "id",
    "name",
    "default_code",          # SKU (clave de mapeo)
    "list_price",            # Precio de venta
    "description_sale",      # Descripción comercial
    "qty_available",         # Stock disponible
    "attribute_line_ids",    # Líneas de atributos (ficha técnica)
    "optional_product_ids",  # Accesorios / upsells
    "image_128",              # Miniatura liviana: solo para saber si hay imagen principal
    "product_template_image_ids",  # Líneas de la galería (modelo product.image)
    "public_categ_ids",      # Categorías de tienda (requiere website_sale)
    "product_tag_ids",       # Etiquetas de producto
]


@dataclass
class SyncReport:
    """Resumen de una corrida de sincronización de catálogo."""

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    upsells_linked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "upsells_linked": self.upsells_linked,
        }


class CatalogSyncService:
    """Servicio del Flujo 1."""

    def __init__(
        self,
        odoo: OdooApi,
        woo: WooApi,
        attribute_service: AttributeSyncService,
        category_tag_service: CategoryTagSyncService,
        odoo_base_url: str,
        batch_size: int = 50,
        logger: logging.Logger | None = None,
        sku_allowlist: frozenset[str] | None = None,
    ):
        self._odoo = odoo
        self._woo = woo
        self._attributes = attribute_service
        self._category_tags = category_tag_service
        self._odoo_base_url = odoo_base_url.rstrip("/")
        self._batch_size = max(1, batch_size)
        self._log = logger or get_logger("catalog")
        self._sku_to_woo_id: dict[str, int] = {}  # caché SKU -> id producto Woo
        # None => sin acotar (todo sale_ok=True). Ver RuntimeConfig.sku_allowlist.
        self._sku_allowlist = sku_allowlist

    # -- Orquestación ------------------------------------------------------

    def run(
        self,
        *,
        full: bool = True,
        since: str | None = None,
        limit: int | None = None,
        ids: list[int] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> SyncReport:
        """Ejecuta la sincronización del catálogo.

        Args:
            full: si True ignora `since` (sincronización completa).
            since: fecha/hora UTC para sincronización incremental por `write_date`.
            limit: tope opcional de productos a procesar (para pruebas).
            ids: si se pasa, sincroniza exactamente esos templates (modo watcher).
            on_progress: callback opcional ``(done, total)`` invocado al iniciar y
                tras cada lote, para alimentar indicadores de progreso (visor).
        """
        domain: list = [("sale_ok", "=", True)]
        if self._sku_allowlist is not None:
            domain.append(("default_code", "in", sorted(self._sku_allowlist)))
        if ids is not None:
            domain.append(("id", "in", list(ids)))
        elif not full and since:
            domain.append(("write_date", ">=", since))
            self._log.info("Sincronización incremental desde %s", since)

        total = self._odoo.search_count("product.template", domain)
        if limit is not None:
            total = min(total, limit)
        report = SyncReport(total=total)
        self._log.info("Inicio de sincronización de catálogo. Productos a procesar: %s", total)
        if on_progress is not None:
            on_progress(0, total)

        # Progreso por ítem: el tiempo se va en el I/O de cada producto, así que la
        # barra debe avanzar producto a producto (no por lote, que con un batch
        # grande se quedaría clavada y saltaría al final).
        done = 0

        def _bump() -> None:
            nonlocal done
            done += 1
            if on_progress is not None:
                on_progress(min(done, total), total)

        upsell_jobs: list[tuple[int, tuple[int, ...]]] = []
        offset = 0
        while offset < total:
            page_limit = min(self._batch_size, total - offset)
            records = self._odoo.search_read(
                "product.template", domain, ODOO_PRODUCT_FIELDS,
                offset=offset, limit=page_limit, order="id asc",
            )
            if not records:
                break
            self._process_batch(
                records, report, upsell_jobs,
                on_item=_bump if on_progress is not None else None,
            )
            offset += len(records)
            done = offset  # reconcilia el conteo con los records del lote (incluye descartados)
            if on_progress is not None:
                on_progress(offset, total)

        report.upsells_linked = self._sync_upsells(upsell_jobs)
        self._log.info("Sincronización de catálogo finalizada: %s", report.as_dict())
        return report

    def unpublish(self, skus: list[str]) -> int:
        """Despublica en Woo (status=draft) los productos dados de baja en Odoo.

        Nunca borra: pasar a borrador es reversible. Omite SKUs vacíos o ausentes
        en Woo. Devuelve cuántos se despublicaron efectivamente.
        """
        count = 0
        for sku in skus:
            if not sku:
                continue
            woo_id = self._find_woo_id_by_sku(sku)
            if not woo_id:
                self._log.info("Baja SKU=%s: no está en Woo, nada que despublicar.", sku)
                continue
            try:
                self._woo.put(f"products/{woo_id}", {"status": "draft"})
                count += 1
                self._log.info("Producto despublicado en Woo id=%s (SKU=%s).", woo_id, sku)
            except ConnectorError as exc:
                self._log.error("Fallo despublicando SKU=%s: %s", sku, exc)
        return count

    # -- Fase 1: productos -------------------------------------------------

    def _process_batch(
        self,
        records: list[dict],
        report: SyncReport,
        upsell_jobs: list[tuple[int, tuple[int, ...]]],
        on_item: Callable[[], None] | None = None,
    ) -> None:
        products = self._resolve_products(records)

        # Asegura los atributos globales del lote en una sola pasada.
        batch_attributes: dict[str, set[str]] = {}
        batch_categories: set[str] = set()
        batch_tags: set[str] = set()
        for product in products:
            for attr in product.attributes:
                batch_attributes.setdefault(attr.name, set()).update(attr.values)
            batch_categories.update(product.categories)
            batch_tags.update(product.tags)
        attribute_ids = self._attributes.ensure_attributes(batch_attributes)
        category_ids = self._category_tags.ensure_categories(batch_categories)
        tag_ids = self._category_tags.ensure_tags(batch_tags)

        for product in products:
            outcome, woo_id = self._upsert_product(product, attribute_ids, category_ids, tag_ids)
            setattr(report, outcome, getattr(report, outcome) + 1)
            if woo_id and product.accessory_template_ids:
                upsell_jobs.append((woo_id, product.accessory_template_ids))
            if on_item is not None:
                on_item()

    def _upsert_product(
        self,
        product: OdooProduct,
        attribute_ids: dict[str, int],
        category_ids: dict[str, int],
        tag_ids: dict[str, int],
    ) -> tuple[str, int | None]:
        """Crea o actualiza un producto. Devuelve (resultado, woo_id)."""
        if not product.sku:
            self._log.warning("Producto Odoo id=%s sin SKU. Se omite.", product.odoo_id)
            return "skipped", None

        try:
            payload = build_woo_product_payload(product, attribute_ids, category_ids, tag_ids)
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

        image_ids = [iid for rec in records for iid in (rec.get("product_template_image_ids") or [])]
        gallery_sequence = self._read_gallery_sequence(image_ids)

        categ_ids = [cid for rec in records for cid in (rec.get("public_categ_ids") or [])]
        category_paths = self._read_category_paths(categ_ids)

        tag_ids = [tid for rec in records for tid in (rec.get("product_tag_ids") or [])]
        tag_names = self._read_tag_names(tag_ids)

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
                image_urls=self._build_image_urls(rec, gallery_sequence),
                categories=tuple(
                    category_paths[cid] for cid in (rec.get("public_categ_ids") or [])
                    if cid in category_paths
                ),
                tags=tuple(
                    tag_names[tid] for tid in (rec.get("product_tag_ids") or [])
                    if tid in tag_names
                ),
            ))
        return products

    def _read_category_paths(self, categ_ids: list[int]) -> dict[int, str]:
        """Resuelve el path completo (``"Cámaras/Filtros"``) de cada categoría.

        ``public_categ_ids`` solo trae las categorías asignadas directamente al
        producto; hay que subir por ``parent_id`` (que puede no estar en el lote
        original) hasta la raíz para reconstruir el path completo.
        """
        if not categ_ids:
            return {}
        nodes: dict[int, dict] = {}
        # Ids ya pedidos a Odoo (se hayan resuelto o no), para no reintentar en
        # loop un parent_id que Odoo no devuelve en `read()` (borrado, o de otra
        # compañía sin acceso).
        attempted: set[int] = set()
        pending = set(categ_ids)
        while pending - attempted:
            missing = list(pending - attempted)
            attempted.update(missing)
            records = self._odoo.read("product.public.category", missing, ["name", "parent_id"])
            for rec in records:
                parent = rec.get("parent_id")
                parent_id = parent[0] if isinstance(parent, (list, tuple)) and parent else None
                nodes[rec["id"]] = {"name": normalize_text(rec.get("name")), "parent_id": parent_id}
                if parent_id is not None:
                    pending.add(parent_id)

        def build_path(cid: int) -> str:
            segments: list[str] = []
            seen: set[int] = set()
            current: int | None = cid
            while current is not None and current in nodes and current not in seen:
                seen.add(current)
                segments.append(nodes[current]["name"])
                current = nodes[current]["parent_id"]
            return CATEGORY_PATH_SEPARATOR.join(reversed(segments))

        return {cid: build_path(cid) for cid in categ_ids if cid in nodes}

    def _read_tag_names(self, tag_ids: list[int]) -> dict[int, str]:
        if not tag_ids:
            return {}
        records = self._odoo.read("product.tag", tag_ids, ["name"])
        return {rec["id"]: normalize_text(rec.get("name")) for rec in records}

    def _read_gallery_sequence(self, image_ids: list[int]) -> dict[int, int]:
        if not image_ids:
            return {}
        records = self._odoo.read("product.image", image_ids, ["sequence"])
        return {rec["id"]: int(rec.get("sequence") or 0) for rec in records}

    def _build_image_urls(self, rec: dict, gallery_sequence: dict[int, int]) -> tuple[str, ...]:
        """Imagen principal primero (si existe), luego la galería por `sequence`.

        No se lee el binario de las imágenes: alcanza con el id del template
        (imagen principal) y los ids de `product.image` (galería) para armar
        URLs públicas de Odoo (`/web/image/...`), que Woo descarga solo.
        """
        urls: list[str] = []
        if rec.get("image_128"):
            urls.append(
                f"{self._odoo_base_url}/web/image/product.template/{rec['id']}/image_1920"
            )
        gallery_ids = rec.get("product_template_image_ids") or []
        ordered_ids = sorted(gallery_ids, key=lambda iid: gallery_sequence.get(iid, 0))
        urls.extend(
            f"{self._odoo_base_url}/web/image/product.image/{iid}/image_1920"
            for iid in ordered_ids
        )
        return tuple(urls)

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

    # -- Fase 2: upsells (accesorios recomendados) --------------------------

    def _sync_upsells(self, jobs: list[tuple[int, tuple[int, ...]]]) -> int:
        if not jobs:
            return 0
        self._log.info("Resolviendo upsells para %s productos.", len(jobs))

        # Resuelve los SKUs de los templates accesorios en una sola lectura.
        accessory_ids = {tid for _, tids in jobs for tid in tids}
        sku_by_template = self._read_accessory_skus(list(accessory_ids))

        linked = 0
        for woo_id, template_ids in jobs:
            upsell_ids = []
            for tid in template_ids:
                sku = sku_by_template.get(tid)
                woo_accessory = self._find_woo_id_by_sku(sku) if sku else None
                if woo_accessory:
                    upsell_ids.append(woo_accessory)
                else:
                    self._log.warning(
                        "Accesorio template_id=%s (sku=%s) no está en Woo. Se omite.", tid, sku
                    )
            if not upsell_ids:
                continue
            try:
                self._woo.put(f"products/{woo_id}", {"upsell_ids": upsell_ids})
                linked += 1
                self._log.info("Upsell asignado a Woo id=%s -> %s", woo_id, upsell_ids)
            except ConnectorError as exc:
                self._log.error("Fallo asignando upsell a Woo id=%s: %s", woo_id, exc)
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
