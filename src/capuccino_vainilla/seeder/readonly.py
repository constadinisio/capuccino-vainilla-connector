"""Wrapper que garantiza, por contrato, que el origen nunca se modifica."""

from __future__ import annotations

from ..clients.protocols import OdooApi
from ..exceptions import ConnectorError


class ReadOnlyViolation(ConnectorError):
    """Se intentó escribir a través de una conexión marcada como solo-lectura."""


class ReadOnlyOdoo:
    """Envuelve un OdooApi exponiendo solo lectura; create/write fallan."""

    def __init__(self, inner: OdooApi):
        self._inner = inner

    def search_count(self, model: str, domain: list) -> int:
        return self._inner.search_count(model, domain)

    def search_read(self, model, domain, fields, offset=0, limit=None, order=None):
        return self._inner.search_read(model, domain, fields, offset, limit, order)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        return self._inner.read(model, ids, fields)

    def create(self, model: str, values: dict) -> int:
        raise ReadOnlyViolation(
            f"Intento de create en conexión de solo-lectura (model={model})."
        )

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        raise ReadOnlyViolation(
            f"Intento de write en conexión de solo-lectura (model={model})."
        )
