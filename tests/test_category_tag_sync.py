"""Tests del servicio de categorías y etiquetas de producto."""

from __future__ import annotations

from capuccino_vainilla.services.category_tag_sync import CategoryTagSyncService


def test_creates_new_top_level_category(fake_woo):
    service = CategoryTagSyncService(fake_woo)
    resolved = service.ensure_categories({"Cámaras"})
    assert "Cámaras" in resolved
    created = fake_woo.categories[0]
    assert created["name"] == "Cámaras"
    assert created["parent"] == 0


def test_creates_nested_category_hierarchy(fake_woo):
    service = CategoryTagSyncService(fake_woo)
    resolved = service.ensure_categories({"Cámaras/Filtros"})

    filtros_id = resolved["Cámaras/Filtros"]
    camaras = next(c for c in fake_woo.categories if c["name"] == "Cámaras")
    filtros = next(c for c in fake_woo.categories if c["id"] == filtros_id)
    assert camaras["parent"] == 0
    assert filtros["parent"] == camaras["id"]


def test_reuses_existing_category_by_path(fake_woo):
    fake_woo.preload_category("Cámaras", 50, parent=0)
    fake_woo.preload_category("Filtros", 51, parent=50)
    service = CategoryTagSyncService(fake_woo)

    resolved = service.ensure_categories({"Cámaras/Filtros"})

    assert resolved["Cámaras/Filtros"] == 51
    assert [c for c in fake_woo.calls if c[0] == "post" and c[1] == "products/categories"] == []


def test_same_child_name_under_different_parents_stays_distinct(fake_woo):
    service = CategoryTagSyncService(fake_woo)
    resolved = service.ensure_categories({"Cámaras/Filtros", "Luces/Filtros"})
    assert resolved["Cámaras/Filtros"] != resolved["Luces/Filtros"]


def test_creates_new_tag(fake_woo):
    service = CategoryTagSyncService(fake_woo)
    resolved = service.ensure_tags({"Oferta"})
    assert "oferta" in resolved
    assert fake_woo.tags[0]["name"] == "Oferta"


def test_reuses_existing_tag_case_insensitive(fake_woo):
    fake_woo.preload_tag("Oferta", 99)
    service = CategoryTagSyncService(fake_woo)
    resolved = service.ensure_tags({"oferta"})
    assert resolved["oferta"] == 99
    assert [c for c in fake_woo.calls if c[0] == "post" and c[1] == "products/tags"] == []
