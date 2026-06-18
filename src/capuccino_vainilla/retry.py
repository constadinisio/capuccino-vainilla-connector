"""Reintentos con backoff exponencial, reutilizable por ambos clientes de API.

Se expone como función (`retry_call`) en vez de decorador para que los
parámetros (intentos, demora) puedan provenir de la configuración por instancia
en tiempo de ejecución, y para poder inyectar un `sleep` falso en los tests.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_DEFAULT_LOGGER = logging.getLogger("capuccino_vainilla.retry")


def retry_call(
    operation: Callable[[], T],
    *,
    description: str,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> T:
    """Ejecuta `operation()` reintentando ante excepciones de `retry_on`.

    El backoff es exponencial: ``base_delay * 2**(intento-1)``. Tras agotar los
    intentos relanza la última excepción, para que el llamador decida qué hacer.

    Args:
        operation: callable sin argumentos a ejecutar.
        description: texto para los logs (qué operación se está intentando).
        max_attempts: cantidad total de intentos (>= 1).
        base_delay: demora base en segundos para el backoff.
        retry_on: tupla de excepciones que disparan reintento.
        sleep: función de espera (inyectable para tests).
        logger: logger a utilizar.
    """
    log = logger or _DEFAULT_LOGGER
    last_exc: Exception | None = None

    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return operation()
        except retry_on as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            log.warning(
                "%s falló (intento %s/%s): %s. Reintentando en %.1fs.",
                description, attempt, max_attempts, exc, delay,
            )
            sleep(delay)

    assert last_exc is not None  # solo se llega aquí tras capturar una excepción
    log.error("%s agotó %s intentos: %s", description, max_attempts, last_exc)
    raise last_exc
