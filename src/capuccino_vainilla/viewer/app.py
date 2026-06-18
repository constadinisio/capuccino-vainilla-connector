"""Aplicación FastAPI del visor: sirve el dashboard y expone su API JSON.

Las operaciones contra Odoo/Woo son bloqueantes (XML-RPC / HTTP), por lo que se
ejecutan en un threadpool para no bloquear el event loop.
"""

from __future__ import annotations

from importlib import resources

from fastapi import Body, FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import AppConfig
from ..exceptions import ConnectorError
from .service import ViewerService


def _load_index_html() -> str:
    return (
        resources.files("capuccino_vainilla.viewer")
        .joinpath("static/index.html")
        .read_text(encoding="utf-8")
    )


def _error_response(exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=502, content={"ok": False, "error": str(exc)})


def create_viewer_app(config: AppConfig, service: ViewerService | None = None) -> FastAPI:
    """Crea la app del visor. ``service`` es inyectable para tests."""
    svc = service or ViewerService(config)
    app = FastAPI(title="Capuccino Vainilla — Visor", version="1.0.0")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _load_index_html()

    @app.get("/api/health")
    async def health() -> dict:
        return await run_in_threadpool(svc.health)

    @app.get("/api/odoo/products")
    async def odoo_products(limit: int = 20, offset: int = 0):
        try:
            items = await run_in_threadpool(svc.list_odoo_products, limit, offset)
            return {"ok": True, "items": items}
        except ConnectorError as exc:
            return _error_response(exc)

    @app.get("/api/woo/products")
    async def woo_products(per_page: int = 20, page: int = 1):
        try:
            items = await run_in_threadpool(svc.list_woo_products, per_page, page)
            return {"ok": True, "items": items}
        except ConnectorError as exc:
            return _error_response(exc)

    @app.get("/api/woo/orders")
    async def woo_orders(per_page: int = 10):
        try:
            items = await run_in_threadpool(svc.list_woo_orders, per_page)
            return {"ok": True, "items": items}
        except ConnectorError as exc:
            return _error_response(exc)

    @app.post("/api/sync/catalog")
    async def sync_catalog(payload: dict = Body(default={})):
        full = bool(payload.get("full", False))
        limit = payload.get("limit")
        try:
            report = await run_in_threadpool(svc.run_sync, full, limit)
            return {"ok": True, "report": report}
        except ConnectorError as exc:
            return _error_response(exc)

    @app.post("/api/woo/orders/{order_id}/import")
    async def import_order(order_id: int):
        try:
            result = await run_in_threadpool(svc.import_woo_order, order_id)
            return {"ok": True, "result": result}
        except (ConnectorError, ValueError) as exc:
            return _error_response(exc)

    @app.get("/api/logs")
    async def logs(tail: int = 120):
        lines = await run_in_threadpool(svc.tail_logs, tail)
        return {"ok": True, "lines": lines}

    return app
