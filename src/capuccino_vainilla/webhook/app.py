"""Aplicación FastAPI que recibe webhooks ``order.created`` de WooCommerce.

Valida la firma HMAC, deserializa el pedido y lo impacta en Odoo a través del
servicio de importación. La operación contra Odoo (bloqueante, XML-RPC) se
ejecuta en un threadpool para no bloquear el event loop.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from ..config import AppConfig
from ..exceptions import ConfigError, ConnectorError, MappingError
from ..logging_config import get_logger
from .security import verify_signature

# Header donde WooCommerce envía la firma del webhook.
SIGNATURE_HEADER = "X-WC-Webhook-Signature"

# Tipo del handler que procesa un pedido y devuelve el id del sale.order.
OrderHandler = Callable[[dict], int]


def _default_order_handler(config: AppConfig, logger: logging.Logger) -> OrderHandler:
    """Construye perezosamente un conector real para procesar los pedidos.

    Se importa el conector dentro de la función para evitar dependencias pesadas
    (y conexiones) cuando se inyecta un handler de prueba.
    """
    connector_holder: dict[str, object] = {}

    def handler(payload: dict) -> int:
        if "connector" not in connector_holder:
            from ..services.connector import OdooWooConnector
            logger.info("Inicializando conector para procesar webhooks.")
            connector_holder["connector"] = OdooWooConnector(config, logger)
        connector = connector_holder["connector"]
        return connector.import_order(payload)  # type: ignore[attr-defined]

    return handler


def create_app(config: AppConfig, order_handler: OrderHandler | None = None) -> FastAPI:
    """Crea la app FastAPI.

    Args:
        config: configuración de la aplicación.
        order_handler: callable que procesa el pedido (inyectable en tests). Si
            es None, se usa un conector real construido a demanda.

    Raises:
        ConfigError: si no hay ``WEBHOOK_SECRET`` configurado.
    """
    secret = config.webhook.secret
    if not secret:
        raise ConfigError(
            "WEBHOOK_SECRET no está configurado: el servidor de webhooks no puede "
            "validar firmas. Definilo en el .env antes de exponer el endpoint."
        )

    log = get_logger("webhook")
    handler = order_handler or _default_order_handler(config, log)
    app = FastAPI(title="Capuccino Vainilla — Webhooks WooCommerce", version="1.0.0")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post(config.webhook.path)
    async def receive_order(request: Request) -> JSONResponse:
        body = await request.body()
        signature = request.headers.get(SIGNATURE_HEADER)

        if not verify_signature(body, signature, secret):
            log.warning("Webhook rechazado: firma HMAC inválida o ausente.")
            return JSONResponse(status_code=401, content={"status": "unauthorized"})

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            log.warning("Webhook rechazado: cuerpo no es JSON válido.")
            return JSONResponse(status_code=400, content={"status": "invalid_json"})

        try:
            sale_order_id = await run_in_threadpool(handler, payload)
        except MappingError as exc:
            # Pedido válido pero no mapeable: se confirma recepción (no reintentar).
            log.warning("Pedido omitido: %s", exc)
            return JSONResponse(status_code=422, content={"status": "skipped", "reason": str(exc)})
        except ConnectorError as exc:
            # Error contra Odoo: 502 para que WooCommerce reintente el envío.
            log.error("Error procesando webhook contra Odoo: %s", exc)
            return JSONResponse(status_code=502, content={"status": "error", "reason": str(exc)})

        return JSONResponse(
            status_code=201, content={"status": "created", "sale_order_id": sale_order_id}
        )

    return app
