"""Persistencia simple del estado de sincronización (para modo incremental).

Guarda en un archivo JSON la última marca de tiempo sincronizada, de modo que
las corridas siguientes solo procesen los productos modificados desde entonces.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .logging_config import get_logger

_CATALOG_KEY = "catalog_last_sync"


class SyncState:
    """Lee/escribe el estado de sincronización en un archivo JSON."""

    def __init__(self, path: str, logger: logging.Logger | None = None):
        self._path = path
        self._log = logger or get_logger("state")

    @staticmethod
    def now_utc() -> str:
        """Marca de tiempo UTC en el formato que entiende Odoo (write_date)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _read(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            self._log.warning(
                "No se pudo leer el estado '%s': %s. Se asume vacío.", self._path, exc
            )
            return {}

    def get_catalog_last_sync(self) -> str | None:
        return self._read().get(_CATALOG_KEY)

    def set_catalog_last_sync(self, timestamp: str) -> None:
        data = self._read()
        data[_CATALOG_KEY] = timestamp
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            self._log.error("No se pudo guardar el estado '%s': %s", self._path, exc)


class SnapshotStore:
    """Lee/escribe el snapshot de huellas del watcher (id -> huella) en JSON."""

    def __init__(self, path: str, logger: logging.Logger | None = None):
        self._path = path
        self._log = logger or get_logger("watcher.snapshot")

    def load(self) -> dict[int, dict]:
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
            return {int(k): v for k, v in raw.items()}
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self._log.warning(
                "No se pudo leer el snapshot '%s': %s. Se asume vacío.", self._path, exc
            )
            return {}

    def save(self, snapshot: dict[int, dict]) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump({str(k): v for k, v in snapshot.items()}, fh, indent=2)
        except OSError as exc:
            self._log.error("No se pudo guardar el snapshot '%s': %s", self._path, exc)
