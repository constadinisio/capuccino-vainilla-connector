"""Orquestación de un ciclo del watcher (un 'tick')."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..logging_config import get_logger
from ..state import SnapshotStore
from .change_detector import ChangeDetector


@dataclass(frozen=True)
class WatchCycle:
    """Resumen de un ciclo: cuántos se sincronizaron y cuántos se dieron de baja."""

    changed: int
    disappeared: int


class WatchService:
    """Compone detector + catálogo + snapshot y ejecuta un ciclo por llamada."""

    def __init__(
        self,
        detector: ChangeDetector,
        catalog,  # CatalogSyncService o compatible: run(*, ids) / unpublish(skus)
        snapshot_store: SnapshotStore,
        *,
        initial_full: bool = True,
        logger: logging.Logger | None = None,
    ):
        self._detector = detector
        self._catalog = catalog
        self._store = snapshot_store
        self._initial_full = initial_full
        self._log = logger or get_logger("watcher")
        self._snapshot = snapshot_store.load()
        self._first_run = not self._snapshot

    def run_once(self) -> WatchCycle:
        current = self._detector.read_fingerprints()

        if self._first_run:
            self._first_run = False
            changed = list(current.keys()) if self._initial_full else []
            if changed:
                self._log.info("Primer ciclo: reconciliando %s productos.", len(changed))
                self._catalog.run(ids=changed)
            self._snapshot = dict(current)
            self._store.save(self._snapshot)
            return WatchCycle(changed=len(changed), disappeared=0)

        changes = self._detector.diff(self._snapshot, current)
        if not changes.changed_ids and not changes.disappeared_ids:
            return WatchCycle(changed=0, disappeared=0)

        self._log.info(
            "Cambios: %s a actualizar, %s a despublicar.",
            len(changes.changed_ids), len(changes.disappeared_ids),
        )
        dirty = False

        if changes.changed_ids:
            report = self._catalog.run(ids=changes.changed_ids)
            if report.failed == 0:
                for i in changes.changed_ids:
                    self._snapshot[i] = current[i]
                dirty = True
            else:
                self._log.warning(
                    "%s productos fallaron; se reintentan el próximo ciclo.", report.failed
                )

        if changes.disappeared_ids:
            skus = [
                self._snapshot[i]["sku"]
                for i in changes.disappeared_ids
                if i in self._snapshot and self._snapshot[i].get("sku")
            ]
            unpublished = self._catalog.unpublish(skus)
            if unpublished == len(skus):
                for i in changes.disappeared_ids:
                    self._snapshot.pop(i, None)
                dirty = True

        if dirty:
            self._store.save(self._snapshot)
        return WatchCycle(changed=len(changes.changed_ids), disappeared=len(changes.disappeared_ids))
