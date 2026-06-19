"""Loop de larga vida del watcher: timing, aislamiento de fallos, shutdown."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ..logging_config import get_logger


class Scheduler:
    """Ejecuta un ``tick`` periódicamente hasta que ``should_stop`` sea True."""

    def __init__(
        self,
        tick: Callable[[], object],
        interval: int,
        *,
        sleep: Callable[[float], None] = time.sleep,
        should_stop: Callable[[], bool] | None = None,
        logger: logging.Logger | None = None,
    ):
        self._tick = tick
        self._interval = max(1, interval)
        self._sleep = sleep
        self._should_stop = should_stop or (lambda: False)
        self._log = logger or get_logger("watcher.scheduler")

    def run_forever(self) -> None:
        self._log.info("Watcher iniciado (intervalo %ss).", self._interval)
        while not self._should_stop():
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 — un tick fallido nunca tumba el loop
                self._log.error("Tick falló: %s. Se continúa.", exc)
            if self._should_stop():
                break
            self._sleep(self._interval)
        self._log.info("Watcher detenido.")
