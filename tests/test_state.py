"""Tests del estado de sincronización incremental."""

from __future__ import annotations

import re

from capuccino_vainilla.state import SyncState


def test_returns_none_when_no_state(tmp_path):
    state = SyncState(str(tmp_path / "state.json"))
    assert state.get_catalog_last_sync() is None


def test_set_and_get_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    state = SyncState(path)
    state.set_catalog_last_sync("2026-06-18 10:00:00")
    # Una nueva instancia debe leer el valor persistido.
    assert SyncState(path).get_catalog_last_sync() == "2026-06-18 10:00:00"


def test_corrupt_file_is_tolerated(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{ esto no es json", encoding="utf-8")
    state = SyncState(str(path))
    assert state.get_catalog_last_sync() is None  # no rompe, asume vacío


def test_now_utc_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", SyncState.now_utc())
