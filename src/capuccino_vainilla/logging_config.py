"""Configuración centralizada de logging con rotación de archivos."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Logger raíz del paquete; el resto cuelga de éste por jerarquía de nombres.
ROOT_LOGGER_NAME = "capuccino_vainilla"


def setup_logging(
    level: str = "INFO",
    log_file: str = "sync.log",
    *,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Configura logging a consola y a archivo con rotación.

    Es idempotente: invocarla varias veces no duplica handlers.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:  # ya configurado
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(suffix: str) -> logging.Logger:
    """Devuelve un logger hijo del paquete (p. ej. 'capuccino_vainilla.odoo')."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{suffix}")
