"""Servicio que garantiza la existencia de atributos globales y sus términos.

Los atributos globales (con sus términos) son los que habilitan los filtros
nativos de WooCommerce. Este servicio es idempotente y cachea para minimizar
llamadas a la API durante una corrida.
"""

from __future__ import annotations

import logging

from ..clients.protocols import WooApi
from ..logging_config import get_logger


class AttributeSyncService:
    """Crea/reutiliza atributos globales de Woo y sus términos."""

    def __init__(self, woo: WooApi, logger: logging.Logger | None = None):
        self._woo = woo
        self._log = logger or get_logger("attributes")
        self._attr_cache: dict[str, int] = {}            # nombre.lower() -> id atributo
        self._terms_cache: dict[int, set[str]] = {}      # id atributo -> términos (lower)
        self._attrs_loaded = False

    def ensure_attributes(self, attributes: dict[str, set[str]]) -> dict[str, int]:
        """Garantiza atributos y términos. Devuelve ``nombre.lower() -> id``.

        Args:
            attributes: mapa ``nombre_atributo -> conjunto de valores``.
        """
        resolved: dict[str, int] = {}
        for name, values in attributes.items():
            attr_id = self._ensure_attribute(name)
            if attr_id is None:
                continue
            resolved[name.strip().lower()] = attr_id
            self._ensure_terms(attr_id, values)
        return resolved

    # -- Internos ----------------------------------------------------------

    def _load_existing_attributes(self) -> None:
        """Carga perezosa (una vez) de los atributos globales ya existentes."""
        if self._attrs_loaded:
            return
        existing = self._woo.get("products/attributes", params={"per_page": 100}) or []
        for attr in existing:
            self._attr_cache[attr["name"].strip().lower()] = attr["id"]
        self._attrs_loaded = True

    def _ensure_attribute(self, name: str) -> int | None:
        key = name.strip().lower()
        if key in self._attr_cache:
            return self._attr_cache[key]

        self._load_existing_attributes()
        if key in self._attr_cache:
            return self._attr_cache[key]

        created = self._woo.post("products/attributes", {"name": name, "has_archives": True})
        if not created or "id" not in created:
            self._log.error("No se pudo crear el atributo global '%s'.", name)
            return None
        self._attr_cache[key] = created["id"]
        self._log.info("Atributo global creado: '%s' (id=%s)", name, created["id"])
        return created["id"]

    def _ensure_terms(self, attr_id: int, values: set[str]) -> None:
        if attr_id not in self._terms_cache:
            terms = self._woo.get(
                f"products/attributes/{attr_id}/terms", params={"per_page": 100}
            ) or []
            self._terms_cache[attr_id] = {t["name"].strip().lower() for t in terms}

        known = self._terms_cache[attr_id]
        for value in values:
            normalized = value.strip().lower()
            if not normalized or normalized in known:
                continue
            created = self._woo.post(f"products/attributes/{attr_id}/terms", {"name": value})
            if created and "id" in created:
                known.add(normalized)
                self._log.debug("Término '%s' creado en atributo id=%s", value, attr_id)
