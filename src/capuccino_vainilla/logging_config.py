"""Configuración centralizada de logging con rotación de archivos."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

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

    # El log a archivo es deseable, pero nunca debe tumbar el proceso: si el path
    # no es escribible (p. ej. contenedor con FS de solo lectura o sin permisos),
    # se degrada a consola, que en contenedores ya capta el orquestador vía stdout.
    file_handler = _build_file_handler(log_file, max_bytes, backup_count, formatter)
    if file_handler is not None:
        logger.addHandler(file_handler)
    else:
        logger.warning(
            "No se pudo abrir el log de archivo %r; se continúa solo con consola.",
            log_file,
        )

    return logger


def _build_file_handler(
    log_file: str,
    max_bytes: int,
    backup_count: int,
    formatter: logging.Formatter,
) -> RotatingFileHandler | None:
    """Crea el handler de archivo creando el directorio padre si hace falta.

    Devuelve ``None`` si el archivo no se puede abrir (permisos, FS de solo
    lectura, etc.) en vez de propagar la excepción.
    """
    try:
        parent = Path(log_file).expanduser().parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        return handler
    except OSError:
        return None


def get_logger(suffix: str) -> logging.Logger:
    """Devuelve un logger hijo del paquete (p. ej. 'capuccino_vainilla.odoo')."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{suffix}")
