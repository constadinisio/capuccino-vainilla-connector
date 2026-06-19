"""Tests del detector de cambios por huella."""
from __future__ import annotations

from capuccino_vainilla.watcher.change_detector import ChangeDetector


def _tmpl(tid, sku, sale_ok=True, qty=5, price=10.0, wd="2026-01-01 00:00:00"):
    return {
        "id": tid, "default_code": sku, "sale_ok": sale_ok,
        "qty_available": qty, "list_price": price, "write_date": wd,
    }


def test_read_fingerprints_only_sale_ok(fake_odoo):
    fake_odoo.db = {"product.template": [
        _tmpl(1, "A"), _tmpl(2, "B", sale_ok=False),
    ]}
    fps = ChangeDetector(fake_odoo).read_fingerprints()
    assert set(fps.keys()) == {1}
    assert fps[1] == {"sku": "A", "write_date": "2026-01-01 00:00:00", "qty": 5, "price": 10.0}


def test_diff_detects_changed_added_and_disappeared(fake_odoo):
    det = ChangeDetector(fake_odoo)
    snapshot = {
        1: {"sku": "A", "write_date": "2026-01-01 00:00:00", "qty": 5, "price": 10.0},
        2: {"sku": "B", "write_date": "2026-01-01 00:00:00", "qty": 5, "price": 10.0},
    }
    current = {
        # stock cambió
        1: {"sku": "A", "write_date": "2026-01-01 00:00:00", "qty": 0, "price": 10.0},
        # alta
        3: {"sku": "C", "write_date": "2026-06-01 00:00:00", "qty": 1, "price": 9.0},
    }
    changes = det.diff(snapshot, current)
    assert sorted(changes.changed_ids) == [1, 3]
    assert changes.disappeared_ids == [2]
