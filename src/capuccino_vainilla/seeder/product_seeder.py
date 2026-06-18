"""Copia de productos del Odoo origen al destino, en tres pasadas.

1) atributos  2) productos (con líneas de atributo)  3) ventas cruzadas.
Remapea IDs entre instancias e idempotencia por name/default_code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..clients.protocols import OdooApi
from ..logging_config import get_logger


@dataclass
class AttributeMaps:
    attribute_ids: dict[int, int] = field(default_factory=dict)
    value_ids: dict[int, int] = field(default_factory=dict)


@dataclass
class SeedReport:
    attributes_created: int = 0
    values_created: int = 0
    products_created: int = 0
    products_updated: int = 0
    products_skipped: int = 0
    cross_sells_linked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "attributes_created": self.attributes_created,
            "values_created": self.values_created,
            "products_created": self.products_created,
            "products_updated": self.products_updated,
            "products_skipped": self.products_skipped,
            "cross_sells_linked": self.cross_sells_linked,
        }


class ProductSeeder:
    def __init__(self, source: OdooApi, target: OdooApi,
                 logger: logging.Logger | None = None):
        self._src = source
        self._dst = target
        self._log = logger or get_logger("seeder")
        self.report = SeedReport()

    def _find_or_create(self, model: str, domain: list, values: dict) -> tuple[int, bool]:
        """Devuelve (id_destino, creado?). Idempotente por el dominio dado."""
        existing = self._dst.search_read(model, domain, ["id"], limit=1)
        if existing:
            return int(existing[0]["id"]), False
        return int(self._dst.create(model, values)), True

    def seed_attributes(self) -> AttributeMaps:
        maps = AttributeMaps()

        for attr in self._src.search_read("product.attribute", [], ["name"]):
            dst_id, created = self._find_or_create(
                "product.attribute", [("name", "=", attr["name"])],
                {"name": attr["name"]},
            )
            maps.attribute_ids[int(attr["id"])] = dst_id
            if created:
                self.report.attributes_created += 1

        for val in self._src.search_read(
            "product.attribute.value", [], ["name", "attribute_id"]
        ):
            src_attr_id = val["attribute_id"][0]  # many2one -> [id, name]
            dst_attr_id = maps.attribute_ids[src_attr_id]
            dst_id, created = self._find_or_create(
                "product.attribute.value",
                [("name", "=", val["name"]), ("attribute_id", "=", dst_attr_id)],
                {"name": val["name"], "attribute_id": dst_attr_id},
            )
            maps.value_ids[int(val["id"])] = dst_id
            if created:
                self.report.values_created += 1

        self._log.info("Atributos copiados: %s, valores: %s",
                       self.report.attributes_created, self.report.values_created)
        return maps
