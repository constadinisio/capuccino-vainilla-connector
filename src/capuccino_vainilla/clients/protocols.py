"""Protocolos (interfaces) de los clientes de API.

Los servicios dependen de estas abstracciones, no de las implementaciones
concretas. Así se cumple la inversión de dependencias y se pueden inyectar
dobles de prueba (fakes) en los tests sin necesidad de red ni de las librerías
externas (woocommerce / xmlrpc).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OdooApi(Protocol):
    """Operaciones que los servicios requieren de Odoo."""

    def search_count(self, model: str, domain: list) -> int: ...

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str],
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict]: ...

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]: ...

    def create(self, model: str, values: dict) -> int: ...

    def write(self, model: str, ids: list[int], values: dict) -> bool: ...


@runtime_checkable
class WooApi(Protocol):
    """Operaciones que los servicios requieren de WooCommerce."""

    def get(self, endpoint: str, params: dict | None = None) -> Any: ...

    def post(self, endpoint: str, data: dict) -> Any: ...

    def put(self, endpoint: str, data: dict) -> Any: ...
