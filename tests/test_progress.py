"""Tests del estado de progreso del visor."""

from __future__ import annotations

from capuccino_vainilla.viewer.progress import SyncProgress


def test_initial_snapshot_is_idle():
    s = SyncProgress().snapshot()
    assert s["running"] is False
    assert s["done"] == 0 and s["total"] == 0
    assert s["percent"] == 0
    assert s["eta_seconds"] is None


def test_progress_lifecycle_reaches_100():
    p = SyncProgress()
    p.begin()
    p.update(0, 10)
    p.update(5, 10)
    mid = p.snapshot()
    assert mid["running"] is True
    assert mid["done"] == 5 and mid["total"] == 10
    assert mid["percent"] == 50

    p.finish()
    end = p.snapshot()
    assert end["running"] is False
    assert end["done"] == 10 and end["percent"] == 100


def test_eta_present_while_running_with_progress():
    p = SyncProgress()
    p.begin()
    p.update(1, 10)
    assert p.snapshot()["eta_seconds"] is not None


def test_fail_records_error_and_stops():
    p = SyncProgress()
    p.begin()
    p.update(2, 10)
    p.fail("explotó Odoo")
    s = p.snapshot()
    assert s["running"] is False
    assert s["error"] == "explotó Odoo"
