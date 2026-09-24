"""Tests de escritura del archivo de lista blanca y su compatibilidad con
``config._load_sku_allowlist`` (el lector que usa `sync-catalog` / `watch`)."""

from __future__ import annotations

from capuccino_vainilla.config import _load_sku_allowlist
from capuccino_vainilla.sku_export.writer import write_allowlist


def test_writes_sorted_unique_skus_with_header_comment(tmp_path):
    output = tmp_path / "sku_allowlist.txt"
    count = write_allowlist(
        frozenset({"CAMAID001", "LENMEI003"}), str(output), source_path="planilla.xlsx"
    )
    assert count == 2

    content = output.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0].startswith("#")
    assert "planilla.xlsx" in lines[0]
    assert "CAMAID001" in lines
    assert "LENMEI003" in lines


def test_output_is_readable_by_load_sku_allowlist(tmp_path):
    output = tmp_path / "sku_allowlist.txt"
    skus = frozenset({"CAMAID001", "LENMEI003", "CONKIL010"})
    write_allowlist(skus, str(output), source_path="planilla.xlsx")

    loaded = _load_sku_allowlist(str(output))
    assert loaded == skus
