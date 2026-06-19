"""Detección de cambios de catálogo por huella (fingerprint).

En vez de confiar en ``write_date`` (que no cambia por movimientos de stock),
se lee una huella barata de cada producto vendible y se compara contra el
snapshot del ciclo anterior. Así se detectan altas, ediciones y stock.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..clients.protocols import OdooApi
from ..logging_config import get_logger
from ..models.product import normalize_text

# Campos baratos que componen la huella.
FINGERPRINT_FIELDS = ["default_code", "write_date", "qty_available", "list_price"]


@dataclass(frozen=True)
class ChangeSet:
    """Resultado de comparar el snapshot contra el estado actual."""

    changed_ids: list[int]      # altas + ediciones + stock
    disappeared_ids: list[int]  # archivados / borrados / no-vendibles


class ChangeDetector:
    """Lee huellas de Odoo y las compara contra un snapshot."""

    def __init__(self, odoo: OdooApi, batch_size: int = 50, logger: logging.Logger | None = None):
        self._odoo = odoo
        self._batch_size = max(1, batch_size)
        self._log = logger or get_logger("watcher.detector")

    def read_fingerprints(self) -> dict[int, dict]:
        """Devuelve ``{id: {"sku","write_date","qty","price"}}`` de los `sale_ok`."""
        domain = [("sale_ok", "=", True)]
        total = self._odoo.search_count("product.template", domain)
        result: dict[int, dict] = {}
        offset = 0
        while offset < total:
            page = self._odoo.search_read(
                "product.template", domain, FINGERPRINT_FIELDS,
                offset=offset, limit=self._batch_size, order="id asc",
            )
            if not page:
                break
            for rec in page:
                result[int(rec["id"])] = {
                    "sku": normalize_text(rec.get("default_code")).strip(),
                    "write_date": rec.get("write_date"),
                    "qty": int(rec.get("qty_available") or 0),
                    "price": float(rec.get("list_price") or 0.0),
                }
            offset += len(page)
        return result

    def diff(self, snapshot: dict[int, dict], current: dict[int, dict]) -> ChangeSet:
        """Compara huellas: devuelve ids cambiados y desaparecidos."""
        changed = [i for i, fp in current.items() if snapshot.get(i) != fp]
        disappeared = [i for i in snapshot if i not in current]
        return ChangeSet(changed_ids=changed, disappeared_ids=disappeared)
