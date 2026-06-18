"""Tests del orquestador de un ciclo del watcher."""
from __future__ import annotations

from capuccino_vainilla.services.catalog_sync import SyncReport
from capuccino_vainilla.state import SnapshotStore
from capuccino_vainilla.watcher.change_detector import ChangeDetector
from capuccino_vainilla.watcher.service import WatchService


class StubCatalog:
    """Catálogo controlable: ``failed`` define cuántos productos fallan."""

    def __init__(self):
        self.failed = 0
        self.run_calls: list[list[int]] = []
        self.unpublish_calls: list[list[str]] = []

    def run(self, *, full=True, since=None, limit=None, ids=None) -> SyncReport:
        self.run_calls.append(list(ids or []))
        return SyncReport(total=len(ids or []), failed=self.failed)

    def unpublish(self, skus) -> int:
        self.unpublish_calls.append(list(skus))
        return len(skus)


def _tmpl(tid, sku, sale_ok=True, qty=5, price=10.0, wd="2026-01-01 00:00:00"):
    return {
        "id": tid, "default_code": sku, "sale_ok": sale_ok,
        "qty_available": qty, "list_price": price, "write_date": wd,
    }


def _service(fake_odoo, catalog, tmp_path, initial_full=True):
    return WatchService(
        ChangeDetector(fake_odoo), catalog,
        SnapshotStore(str(tmp_path / "snap.json")), initial_full=initial_full,
    )


def test_first_cycle_full_reconciles_and_saves_snapshot(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A"), _tmpl(2, "B")]}
    catalog = StubCatalog()
    svc = _service(fake_odoo, catalog, tmp_path)

    cycle = svc.run_once()

    assert cycle.changed == 2
    assert sorted(catalog.run_calls[0]) == [1, 2]
    assert set(SnapshotStore(str(tmp_path / "snap.json")).load().keys()) == {1, 2}


def test_first_cycle_no_full_only_builds_snapshot(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A")]}
    catalog = StubCatalog()
    svc = _service(fake_odoo, catalog, tmp_path, initial_full=False)

    cycle = svc.run_once()

    assert cycle.changed == 0
    assert catalog.run_calls == []  # no sincronizó
    assert set(SnapshotStore(str(tmp_path / "snap.json")).load().keys()) == {1}


def test_incremental_syncs_changes_and_unpublishes(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A"), _tmpl(2, "B"), _tmpl(3, "C")]}
    catalog = StubCatalog()
    svc = _service(fake_odoo, catalog, tmp_path)
    svc.run_once()  # bootstrap

    # editar precio de 1, archivar 3
    rows = fake_odoo.db["product.template"]
    next(r for r in rows if r["id"] == 1)["list_price"] = 99.0
    next(r for r in rows if r["id"] == 3)["sale_ok"] = False

    cycle = svc.run_once()

    assert cycle.changed == 1 and cycle.disappeared == 1
    assert catalog.run_calls[-1] == [1]
    assert catalog.unpublish_calls[-1] == ["C"]


def test_snapshot_not_advanced_when_sync_fails(fake_odoo, tmp_path):
    fake_odoo.db = {"product.template": [_tmpl(1, "A")]}
    catalog = StubCatalog()
    store_path = str(tmp_path / "snap.json")
    svc = WatchService(ChangeDetector(fake_odoo), catalog, SnapshotStore(store_path))
    svc.run_once()  # bootstrap OK

    next(r for r in fake_odoo.db["product.template"] if r["id"] == 1)["list_price"] = 99.0
    catalog.failed = 1
    svc.run_once()
    assert SnapshotStore(store_path).load()[1]["price"] == 10.0  # no avanzó

    catalog.failed = 0
    svc.run_once()  # se reintenta y ahora sí avanza
    assert catalog.run_calls[-1] == [1]
    assert SnapshotStore(store_path).load()[1]["price"] == 99.0
