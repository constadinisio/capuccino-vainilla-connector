"""Cliente de Odoo sobre la API XML-RPC nativa.

Encapsula autenticación + ``execute_kw`` agregando reintentos con backoff ante
errores transitorios de red. Tras agotar reintentos, relanza ``OdooError`` para
que la capa de servicio decida (típicamente: omitir el ítem y continuar).
"""

from __future__ import annotations

import logging
import socket
import xmlrpc.client
from typing import Any

from ..config import OdooConfig, RuntimeConfig
from ..exceptions import OdooAuthError, OdooError
from ..logging_config import get_logger
from ..retry import retry_call

# Excepciones consideradas transitorias (se reintentan).
_TRANSIENT = (
    ConnectionError,
    TimeoutError,
    socket.timeout,
    socket.gaierror,
    xmlrpc.client.ProtocolError,
    OSError,
)


class OdooClient:
    """Cliente de alto nivel para Odoo vía XML-RPC."""

    def __init__(
        self,
        config: OdooConfig,
        runtime: RuntimeConfig,
        logger: logging.Logger | None = None,
        *,
        models: Any | None = None,
        uid: int | None = None,
    ):
        """Crea el cliente.

        Para tests se pueden inyectar ``models`` (proxy de objetos) y ``uid``,
        evitando la autenticación real contra un servidor.
        """
        self._config = config
        self._runtime = runtime
        self._log = logger or get_logger("odoo")

        if models is not None and uid is not None:
            self._models = models
            self._uid = uid
        else:
            self._uid, self._models = self._connect()

    # -- Conexión ----------------------------------------------------------

    def _connect(self) -> tuple[int, Any]:
        try:
            common = xmlrpc.client.ServerProxy(f"{self._config.url}/xmlrpc/2/common")
            uid = common.authenticate(
                self._config.db, self._config.username, self._config.password, {}
            )
        except Exception as exc:  # red/DNS/XML-RPC en el handshake inicial
            raise OdooError(f"No se pudo conectar a Odoo en {self._config.url}: {exc}") from exc

        # authenticate() devuelve el uid (int) o False si las credenciales fallan.
        if not isinstance(uid, int) or isinstance(uid, bool) or not uid:
            raise OdooAuthError(
                "Autenticación de Odoo fallida: verificá ODOO_DB, ODOO_USERNAME y "
                "ODOO_PASSWORD (o API Key)."
            )
        models = xmlrpc.client.ServerProxy(f"{self._config.url}/xmlrpc/2/object")
        self._log.info("Conectado a Odoo '%s' como uid=%s", self._config.db, uid)
        return uid, models

    # -- Llamada genérica --------------------------------------------------

    def execute_kw(self, model: str, method: str, args: list, kwargs: dict | None = None) -> Any:
        """Ejecuta ``model.method`` con reintentos; relanza ``OdooError`` si falla."""
        kwargs = kwargs or {}

        def _operation() -> Any:
            return self._models.execute_kw(
                self._config.db, self._uid, self._config.password,
                model, method, args, kwargs,
            )

        try:
            return retry_call(
                _operation,
                description=f"Odoo {model}.{method}",
                max_attempts=self._runtime.max_retries,
                base_delay=self._runtime.retry_delay,
                retry_on=_TRANSIENT,
                logger=self._log,
            )
        except _TRANSIENT as exc:
            raise OdooError(f"Odoo {model}.{method} falló tras reintentos: {exc}") from exc
        except xmlrpc.client.Fault as exc:
            # Error de lógica del servidor (validación, permisos): no se reintenta.
            raise OdooError(f"Odoo rechazó {model}.{method}: {exc.faultString}") from exc

    # -- Atajos de uso frecuente ------------------------------------------

    def search_count(self, model: str, domain: list) -> int:
        return int(self.execute_kw(model, "search_count", [domain]) or 0)

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str],
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"fields": fields, "offset": offset}
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self.execute_kw(model, "search_read", [domain], kwargs) or []

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        if not ids:
            return []
        return self.execute_kw(model, "read", [ids], {"fields": fields}) or []

    def create(self, model: str, values: dict) -> int:
        new_id = self.execute_kw(model, "create", [values])
        if not new_id:
            raise OdooError(f"Odoo no devolvió id al crear un {model}.")
        return int(new_id)

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        return bool(self.execute_kw(model, "write", [ids, values]))
