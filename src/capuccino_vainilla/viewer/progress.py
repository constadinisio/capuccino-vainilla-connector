"""Estado de progreso de la sincronización del catálogo.

Lo comparten el hilo del threadpool que ejecuta el sync (llama
``begin``/``update``/``finish``/``fail``) y el endpoint de *polling* del visor
(lee ``snapshot`` desde el event loop). Es thread-safe vía un lock simple.
"""

from __future__ import annotations

import threading
import time


class SyncProgress:
    """Progreso thread-safe de una corrida de sincronización."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._done = 0
        self._total = 0
        self._started_at = 0.0
        self._finished_at = 0.0
        self._error: str | None = None

    def begin(self) -> None:
        """Marca el inicio de una corrida (total aún desconocido)."""
        with self._lock:
            self._running = True
            self._done = 0
            self._total = 0
            self._started_at = time.time()
            self._finished_at = 0.0
            self._error = None

    def update(self, done: int, total: int) -> None:
        with self._lock:
            self._done = done
            self._total = total

    def finish(self) -> None:
        with self._lock:
            self._running = False
            self._finished_at = time.time()
            if self._total:
                self._done = self._total

    def fail(self, error: str) -> None:
        with self._lock:
            self._running = False
            self._finished_at = time.time()
            self._error = error

    def snapshot(self) -> dict:
        """Foto del estado para el frontend, con ETA estimada por velocidad media."""
        with self._lock:
            ref = time.time() if self._running else (self._finished_at or self._started_at)
            elapsed = max(0.0, ref - self._started_at) if self._started_at else 0.0
            done, total = self._done, self._total
            percent = round(100 * done / total) if total else 0
            eta: float | None = None
            if self._running and done > 0 and total > 0:
                eta = max(0.0, (elapsed / done) * (total - done))
            return {
                "running": self._running,
                "done": done,
                "total": total,
                "percent": percent,
                "elapsed_seconds": round(elapsed, 1),
                "eta_seconds": round(eta, 1) if eta is not None else None,
                "error": self._error,
            }
