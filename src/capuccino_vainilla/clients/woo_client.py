"""Cliente de WooCommerce sobre la librería oficial ``woocommerce``.

Centraliza el parseo de respuestas, la clasificación de errores y los
reintentos. Distingue errores transitorios (5xx, 429, red) — que se reintentan —
de los definitivos (4xx) — que se relanzan de inmediato.
"""

from __future__ import annotations

import logging
from typing import Any

from woocommerce import API

from ..config import RuntimeConfig, WooConfig
from ..exceptions import WooError, WooTransientError
from ..logging_config import get_logger
from ..retry import retry_call


class WooClient:
    """Cliente de alto nivel para la WooCommerce REST API."""

    def __init__(
        self,
        config: WooConfig,
        runtime: RuntimeConfig,
        logger: logging.Logger | None = None,
        *,
        api: Any | None = None,
    ):
        """Crea el cliente. Para tests se puede inyectar un ``api`` falso."""
        self._runtime = runtime
        self._log = logger or get_logger("woo")
        self._api = api or API(
            url=config.url,
            consumer_key=config.consumer_key,
            consumer_secret=config.consumer_secret,
            version=config.api_version,
            verify_ssl=config.verify_ssl,
            timeout=config.timeout,
            query_string_auth=True,  # más robusto detrás de proxies/HTTPS
        )

    # -- Núcleo: ejecuta y clasifica la respuesta --------------------------

    def _do_request(self, verb: str, endpoint: str, **kwargs) -> Any:
        """Realiza una petición. Devuelve JSON; clasifica y relanza errores."""
        try:
            response = getattr(self._api, verb)(endpoint, **kwargs)
        except Exception as exc:  # timeout, error de red, etc. => transitorio
            raise WooTransientError(f"Fallo de red en {verb.upper()} {endpoint}: {exc}") from exc

        status = response.status_code
        if 200 <= status < 300:
            return response.json()

        body = (response.text or "")[:300]
        if status == 429 or 500 <= status < 600:
            raise WooTransientError(f"{verb.upper()} {endpoint} -> {status}: {body}")
        # 4xx (salvo 429): error del cliente, no tiene sentido reintentar.
        raise WooError(f"{verb.upper()} {endpoint} -> {status}: {body}")

    def _request(self, verb: str, endpoint: str, **kwargs) -> Any:
        return retry_call(
            lambda: self._do_request(verb, endpoint, **kwargs),
            description=f"Woo {verb.upper()} {endpoint}",
            max_attempts=self._runtime.max_retries,
            base_delay=self._runtime.retry_delay,
            retry_on=(WooTransientError,),
            logger=self._log,
        )

    # -- Helpers públicos --------------------------------------------------

    def get(self, endpoint: str, params: dict | None = None) -> Any:
        return self._request("get", endpoint, params=params or {})

    def post(self, endpoint: str, data: dict) -> Any:
        return self._request("post", endpoint, data=data)

    def put(self, endpoint: str, data: dict) -> Any:
        return self._request("put", endpoint, data=data)
