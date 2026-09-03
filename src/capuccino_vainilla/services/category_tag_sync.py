"""Servicio que garantiza la existencia de categorías (jerárquicas) y tags de producto.

Igual que ``AttributeSyncService``: idempotente y cacheado para minimizar
llamadas a la API durante una corrida.
"""

from __future__ import annotations

import logging

from ..clients.protocols import WooApi
from ..logging_config import get_logger

CATEGORY_PATH_SEPARATOR = "/"


class CategoryTagSyncService:
    """Crea/reutiliza categorías (con jerarquía) y tags de Woo."""

    def __init__(self, woo: WooApi, logger: logging.Logger | None = None):
        self._woo = woo
        self._log = logger or get_logger("categories")
        # (parent_id, nombre.lower()) -> id categoría
        self._category_cache: dict[tuple[int, str], int] = {}
        self._tag_cache: dict[str, int] = {}  # nombre.lower() -> id tag

    def ensure_categories(self, paths: set[str]) -> dict[str, int]:
        """Garantiza cada path de categoría. Devuelve ``path_completo -> id``."""
        resolved: dict[str, int] = {}
        for path in paths:
            cat_id = self._ensure_path(path)
            if cat_id is not None:
                resolved[path] = cat_id
        return resolved

    def ensure_tags(self, names: set[str]) -> dict[str, int]:
        """Garantiza cada tag. Devuelve ``nombre.lower() -> id``."""
        resolved: dict[str, int] = {}
        for name in names:
            tag_id = self._ensure_tag(name)
            if tag_id is not None:
                resolved[name.strip().lower()] = tag_id
        return resolved

    # -- Internos ----------------------------------------------------------

    def _ensure_path(self, path: str) -> int | None:
        parent_id = 0
        cat_id: int | None = None
        for level_name in path.split(CATEGORY_PATH_SEPARATOR):
            level_name = level_name.strip()
            if not level_name:
                continue
            cat_id = self._ensure_level(level_name, parent_id)
            if cat_id is None:
                return None
            parent_id = cat_id
        return cat_id

    def _ensure_level(self, name: str, parent_id: int) -> int | None:
        key = (parent_id, name.lower())
        if key in self._category_cache:
            return self._category_cache[key]

        existing = self._woo.get(
            "products/categories", params={"parent": parent_id, "search": name}
        ) or []
        for cat in existing:
            if cat["name"].strip().lower() == name.lower():
                self._category_cache[key] = cat["id"]
                return cat["id"]

        created = self._woo.post("products/categories", {"name": name, "parent": parent_id})
        if not created or "id" not in created:
            self._log.error("No se pudo crear la categoría '%s' (parent=%s).", name, parent_id)
            return None
        self._category_cache[key] = created["id"]
        self._log.info("Categoría creada: '%s' (id=%s, parent=%s)", name, created["id"], parent_id)
        return created["id"]

    def _ensure_tag(self, name: str) -> int | None:
        key = name.strip().lower()
        if key in self._tag_cache:
            return self._tag_cache[key]

        existing = self._woo.get("products/tags", params={"search": name}) or []
        for tag in existing:
            if tag["name"].strip().lower() == key:
                self._tag_cache[key] = tag["id"]
                return tag["id"]

        created = self._woo.post("products/tags", {"name": name})
        if not created or "id" not in created:
            self._log.error("No se pudo crear el tag '%s'.", name)
            return None
        self._tag_cache[key] = created["id"]
        self._log.info("Tag creado: '%s' (id=%s)", name, created["id"])
        return created["id"]
