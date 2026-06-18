"""Tests del servicio de atributos globales."""

from __future__ import annotations

from capuccino_vainilla.services.attribute_sync import AttributeSyncService


def test_creates_new_attribute_and_terms(fake_woo):
    service = AttributeSyncService(fake_woo)
    resolved = service.ensure_attributes({"Marca": {"Sony", "Canon"}})

    assert "marca" in resolved
    attr_id = resolved["marca"]
    term_names = {t["name"] for t in fake_woo.terms[attr_id]}
    assert term_names == {"Sony", "Canon"}


def test_reuses_existing_attribute(fake_woo):
    fake_woo.preload_attribute("Marca", 99)
    service = AttributeSyncService(fake_woo)
    resolved = service.ensure_attributes({"Marca": {"Sony"}})
    assert resolved["marca"] == 99
    # No debe crear un atributo nuevo (no hay POST a products/attributes).
    posted_attrs = [c for c in fake_woo.calls if c[0] == "post" and c[1] == "products/attributes"]
    assert posted_attrs == []


def test_caches_terms_across_calls(fake_woo):
    service = AttributeSyncService(fake_woo)
    service.ensure_attributes({"Resolución": {"4K"}})
    service.ensure_attributes({"Resolución": {"4K"}})  # mismo término otra vez
    attr_id = service._attr_cache["resolución"]
    # El término "4K" se creó una sola vez.
    assert len(fake_woo.terms[attr_id]) == 1
