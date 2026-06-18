"""Interfaz de línea de comandos del conector Capuccino Vainilla.

Subcomandos:
    sync-catalog   Sincroniza el catálogo Odoo -> WooCommerce (Flujo 1).
    import-order   Importa un pedido WooCommerce -> Odoo desde un JSON (Flujo 2).
    serve          Levanta el servidor de webhooks (FastAPI + uvicorn).
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import AppConfig, ConfigError, load_config
from .exceptions import ConnectorError
from .logging_config import setup_logging
from .state import SyncState


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capuccino-vainilla",
        description="Conector bidireccional Odoo ⇄ WooCommerce (Pinnacle).",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Ruta a un .env específico (ej. .env.test). Default: busca .env.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync-catalog", help="Sincroniza catálogo Odoo -> WooCommerce")
    p_sync.add_argument("--full", action="store_true",
                        help="Fuerza sincronización completa (ignora el estado incremental).")
    p_sync.add_argument("--since", default=None,
                        help="Sincroniza productos modificados desde 'YYYY-MM-DD HH:MM:SS' (UTC).")
    p_sync.add_argument("--limit", type=int, default=None,
                        help="Tope de productos a procesar (útil para pruebas).")

    p_order = sub.add_parser("import-order", help="Importa pedido WooCommerce -> Odoo")
    p_order.add_argument("--file", required=True, help="Ruta al JSON del pedido.")

    p_serve = sub.add_parser("serve", help="Levanta el servidor de webhooks")
    p_serve.add_argument("--host", default=None, help="Host de escucha (default: WEBHOOK_HOST).")
    p_serve.add_argument("--port", type=int, default=None, help="Puerto (default: WEBHOOK_PORT).")

    p_viewer = sub.add_parser("viewer", help="Levanta el visor web (dashboard) del conector")
    p_viewer.add_argument("--host", default="127.0.0.1", help="Host de escucha.")
    p_viewer.add_argument("--port", type=int, default=8050, help="Puerto (default: 8050).")

    p_watch = sub.add_parser("watch", help="Sincroniza el catálogo en continuo")
    p_watch.add_argument("--interval", type=int, default=None,
                         help="Segundos entre ciclos (default: WATCH_INTERVAL).")
    p_watch.add_argument("--once", action="store_true",
                         help="Corre un solo ciclo y termina (útil para pruebas/cron).")

    return parser


def _cmd_sync_catalog(config: AppConfig, args: argparse.Namespace) -> int:
    from .services.connector import OdooWooConnector

    state = SyncState(config.runtime.state_file)
    since = args.since or (None if args.full else state.get_catalog_last_sync())
    run_started = SyncState.now_utc()

    connector = OdooWooConnector(config)
    report = connector.sync_catalog(full=args.full, since=since, limit=args.limit)

    # Solo avanzamos la marca incremental si no hubo fallos (evita perder cambios).
    if report.failed == 0:
        state.set_catalog_last_sync(run_started)

    print(f"\nResumen de sincronización: {report.as_dict()}")
    return 0 if report.failed == 0 else 1


def _cmd_import_order(config: AppConfig, args: argparse.Namespace) -> int:
    from .services.connector import OdooWooConnector

    try:
        with open(args.file, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"No se pudo leer el JSON '{args.file}': {exc}", file=sys.stderr)
        return 1

    connector = OdooWooConnector(config)
    try:
        sale_order_id = connector.import_order(payload)
    except ConnectorError as exc:
        print(f"No se pudo importar el pedido: {exc}", file=sys.stderr)
        return 1
    print(f"\nPedido importado. sale.order id = {sale_order_id}")
    return 0


def _cmd_serve(config: AppConfig, args: argparse.Namespace) -> int:
    import uvicorn

    from .webhook.app import create_app

    host = args.host or config.webhook.host
    port = args.port or config.webhook.port
    app = create_app(config)
    print(f"Servidor de webhooks escuchando en http://{host}:{port}{config.webhook.path}")
    uvicorn.run(app, host=host, port=port, log_level=config.runtime.log_level.lower())
    return 0


def _cmd_watch(config: AppConfig, args: argparse.Namespace) -> int:
    import signal

    from .services.connector import OdooWooConnector
    from .state import SnapshotStore
    from .watcher.change_detector import ChangeDetector
    from .watcher.scheduler import Scheduler
    from .watcher.service import WatchService

    connector = OdooWooConnector(config)
    detector = ChangeDetector(connector.odoo, batch_size=config.runtime.batch_size)
    store = SnapshotStore(config.watcher.state_file)
    service = WatchService(detector, connector.catalog, store,
                           initial_full=config.watcher.initial_full)

    if args.once:
        service.run_once()
        return 0

    interval = args.interval or config.watcher.interval
    stop = {"flag": False}

    def _handle(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    print(f"Watcher en marcha (cada {interval}s). Ctrl-C para detener.")
    Scheduler(service.run_once, interval, should_stop=lambda: stop["flag"]).run_forever()
    return 0


def _cmd_viewer(config: AppConfig, args: argparse.Namespace) -> int:
    import uvicorn

    from .viewer.app import create_viewer_app

    app = create_viewer_app(config)
    print(f"Visor disponible en http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level=config.runtime.log_level.lower())
    return 0


def _force_utf8_output() -> None:
    """Evita UnicodeEncodeError en consolas no-UTF8 (p. ej. cp1252 en Windows)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = _build_parser().parse_args(argv)

    try:
        config = load_config(env_file=args.env_file)
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2

    setup_logging(config.runtime.log_level, config.runtime.log_file)

    print(
        f"⚙️  Objetivo resuelto → Odoo: {config.odoo.url} (db={config.odoo.db}) | "
        f"WooCommerce: {config.woo.url}",
        file=sys.stderr,
    )

    try:
        if args.command == "sync-catalog":
            return _cmd_sync_catalog(config, args)
        if args.command == "import-order":
            return _cmd_import_order(config, args)
        if args.command == "serve":
            return _cmd_serve(config, args)
        if args.command == "viewer":
            return _cmd_viewer(config, args)
        if args.command == "watch":
            return _cmd_watch(config, args)
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
    except ConnectorError as exc:
        print(f"Error del conector: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
