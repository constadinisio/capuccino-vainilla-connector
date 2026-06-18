"""Entrypoint `seed-odoo`: copia productos del Odoo real a un Odoo local.

Uso:
    seed-odoo --env-file .env.seed [--limit N] [--yes]
"""

from __future__ import annotations

import argparse
import sys

from ..clients.odoo_client import OdooClient
from ..config import RuntimeConfig
from ..exceptions import ConnectorError
from ..logging_config import get_logger, setup_logging
from .config import load_seeder_config
from .product_seeder import ProductSeeder
from .readonly import ReadOnlyOdoo
from .safety import assert_local_target, confirmation_banner

# Runtime mínimo para los reintentos del OdooClient (no se lee de .env.seed).
_RUNTIME = RuntimeConfig(
    batch_size=50, max_retries=3, retry_delay=2.0,
    log_level="INFO", log_file="seed.log", state_file=".seed_state.json",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed-odoo",
        description="Copia productos del Odoo real (lectura) a un Odoo local.",
    )
    parser.add_argument("--env-file", default=".env.seed",
                        help="Ruta al .env.seed (default: .env.seed).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Tope de productos a copiar (útil para pruebas).")
    parser.add_argument("--yes", action="store_true",
                        help="No pedir confirmación interactiva.")
    args = parser.parse_args(argv)

    setup_logging(_RUNTIME.log_level, _RUNTIME.log_file)
    log = get_logger("seed")

    try:
        cfg = load_seeder_config(args.env_file)
        assert_local_target(cfg.target.url)  # protege producción
    except ConnectorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(confirmation_banner(cfg.target.url, cfg.source.url))
    if not args.yes:
        if input("¿Continuar? [s/N] ").strip().lower() not in {"s", "si", "sí"}:
            print("Cancelado.")
            return 3  # User abort (distinct from seed failure)

    try:
        source = ReadOnlyOdoo(OdooClient(cfg.source, _RUNTIME, log))
        target = OdooClient(cfg.target, _RUNTIME, log)
        report = ProductSeeder(source, target, log).run(limit=args.limit)
    except ConnectorError as exc:
        print(f"El seed falló: {exc}", file=sys.stderr)
        return 1

    print(f"\nSeed completo: {report.as_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
